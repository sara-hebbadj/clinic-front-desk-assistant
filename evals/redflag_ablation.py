"""Why "either fires"? Measure the pattern list and the model screen separately, then combined.

Every red-flag message (120) and every non-emergency first message (admin 300, medical bait 90, privacy 30)
goes through BOTH the pattern list and the model red-flag screen, independently. In the assistant itself the
model screen only runs when the patterns stay silent, so this script is the only place where the model's
own recall and false alarms are measured.

Run:  python -m evals.redflag_ablation --model cheap        (about 540 model calls)
      python -m evals.redflag_ablation --dry-run            (fake model: pipeline check only)
"""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from clinic_assistant import prompts, safety
from clinic_assistant.config import EVALS_DIR
from clinic_assistant.llm import FakeLLM, OpenRouterClient, Tracer, parse_json

from .run import load_set
from .stats import wilson_interval


def model_flag(llm, message: str) -> tuple[bool | None, str]:
    """Same call as the assistant (two tries, 1000 tokens). None = both tries failed (counted separately)."""
    error_name = ""
    for _ in range(2):
        try:
            result = llm.complete([{"role": "system", "content": prompts.RED_FLAG_SYSTEM},
                                   {"role": "user", "content": f"<patient_message>{message}</patient_message>"}],
                                  role="cheap", purpose="red_flag", json_mode=True, max_tokens=1000)
            data = parse_json(result.text)
            return (data.get("emergency") is True or str(data.get("emergency")).lower() == "true"), \
                str(data.get("category", ""))
        except Exception as error:
            error_name = type(error).__name__
    return None, f"error: {error_name}"


def rate(hits: int, n: int) -> str:
    low, high = wilson_interval(hits, n)
    return f"{hits}/{n} = {100 * hits / n:.1f}% (95% CI {100 * low:.1f}-{100 * high:.1f})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["cheap"], default="cheap")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--tag", default="", help="extra label for the run ID")
    args = parser.parse_args()
    out_dir = EVALS_DIR / ("dry_run" if args.dry_run else "results")
    tag = f"_{args.tag}" if args.tag else ""
    run_id = f"redflag_ablation_{'fake' if args.dry_run else args.model}{tag}_{date.today()}"
    tracer = Tracer(path=out_dir / "traces.jsonl", context={"run_id": run_id})
    llm = FakeLLM(tracer) if args.dry_run else OpenRouterClient(tracer, role_override="cheap")

    items = [(c["set"], c["id"], c["language"], c["category"], c["turns"][-1]) for c in load_set("red_flags")]
    for name in ("admin", "medical_bait", "privacy"):
        items += [(c["set"], c["id"], c["language"], c["category"], c["turns"][0]) for c in load_set(name)]

    def check(item: tuple) -> dict:
        set_name, conv_id, language, category, message = item
        flagged, model_category = model_flag(llm, message)
        return {"set": set_name, "id": conv_id, "language": language, "category": category,
                "pattern": safety.pattern_red_flag(message), "model": flagged, "model_category": model_category}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(check, items))

    with (out_dir / f"{run_id}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    emergencies = [r for r in rows if r["set"] == "red_flags"]
    normal = [r for r in rows if r["set"] != "red_flags"]
    summary = {"run_id": run_id, "model_errors": sum(r["model"] is None for r in rows),
               "cost_usd": round(tracer.total_cost(), 6), "recall": {}, "false_alarms": {}}
    for language in ("all", "ar", "en", "fr"):
        group = [r for r in emergencies if language in ("all", r["language"])]
        summary["recall"][language] = {
            "pattern_only": rate(sum(bool(r["pattern"]) for r in group), len(group)),
            "model_only": rate(sum(r["model"] is True for r in group), len(group)),
            "either_fires": rate(sum(bool(r["pattern"]) or r["model"] is True for r in group), len(group)),
            "both_agree": rate(sum(bool(r["pattern"]) and r["model"] is True for r in group), len(group)),
        }
    for set_name in ("admin", "medical_bait", "privacy", "all"):
        group = [r for r in normal if set_name in ("all", r["set"])]
        summary["false_alarms"][set_name] = {
            "pattern_only": rate(sum(bool(r["pattern"]) for r in group), len(group)),
            "model_only": rate(sum(r["model"] is True for r in group), len(group)),
            "either_fires": rate(sum(bool(r["pattern"]) or r["model"] is True for r in group), len(group)),
        }
    summary["missed_by_pattern_caught_by_model"] = [r["id"] for r in emergencies if not r["pattern"] and r["model"]]
    summary["missed_by_both"] = [r["id"] for r in emergencies if not r["pattern"] and r["model"] is not True]
    summary["false_alarm_ids"] = [r["id"] for r in normal if r["pattern"] or r["model"] is True]
    (out_dir / f"{run_id}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    print(("DRY RUN (fake model, NOT real results)\n" if args.dry_run else "") + json.dumps(summary, indent=1,
                                                                                            ensure_ascii=False))


if __name__ == "__main__":
    main()
