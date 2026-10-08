"""Run the evaluation sets through the assistant or a baseline, score them, and save everything.

Examples:
  python -m evals.run --system rules                                  # keyword baseline, no model: real results
  python -m evals.run --system assistant --model cheap --limit 10     # smoke test (mixed sets and languages)
  python -m evals.run --system assistant --model cheap --judge        # full run + LLM judges
  python -m evals.run --system plain --model cheap --sets red_flags,medical_bait --judge
  python -m evals.run --system assistant --dry-run                    # FAKE model: proves the pipeline, NOT results

Real runs write to evals/results/, dry runs to evals/dry_run/:
  <run_id>.jsonl               one record per conversation (replies, outcomes, tools, score, judges)
  <run_id>_summary.csv         metrics per set and language
  <run_id>_by_category.csv     task success per category
  traces.jsonl                 one line per model call (model, tokens, cost, latency; no message text)
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from clinic_assistant.assistant import FrontDeskAssistant, Session
from clinic_assistant.clinic import ClinicStore
from clinic_assistant.config import EVALS_DIR, env
from clinic_assistant.llm import FakeLLM, OpenRouterClient, Tracer
from clinic_assistant.prompts import plain_system
from clinic_assistant.text import normalise

from .judge import judge_medical, judge_tone, tone_sample
from .scoring import by_category, score, summarise

SETS = ("admin", "red_flags", "medical_bait", "privacy")
NURSE_WORDS = ("nurse", "infirmi", "ممرض", "التمريض", "doctor", "médecin", "medecin", "طبيب")


def load_set(name: str) -> list[dict]:
    path = EVALS_DIR / "sets" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def interleave(conversations: list[dict]) -> list[dict]:
    """ar, en, fr, ar, en, fr... so --limit still covers all three languages."""
    by_lang = {lang: [c for c in conversations if c["language"] == lang] for lang in ("ar", "en", "fr")}
    longest = max(len(v) for v in by_lang.values())
    return [by_lang[lang][i] for i in range(longest) for lang in ("ar", "en", "fr") if i < len(by_lang[lang])]


def select(sets: list[str], limit: int, per_lang: int) -> list[dict]:
    chosen = []
    for name in sets:
        items = interleave(load_set(name))
        if per_lang:
            items = interleave([c for lang in ("ar", "en", "fr") for c in
                                [x for x in items if x["language"] == lang][:per_lang]])
        if limit:
            items = items[:limit]
        chosen += items
    return chosen


# ------------------------------------------------------------------------------------------- systems
def run_assistant(assistant: FrontDeskAssistant, conv: dict) -> dict:
    session = Session(language=conv["language"])
    turns = [assistant.handle(session, message) for message in conv["turns"]]
    flagged = next((t for t in turns if t.red_flag), None)
    return {"replies": [t.reply for t in turns], "outcomes": [t.outcome for t in turns],
            "intents": [t.intent for t in turns], "tools": [tool for t in turns for tool in t.tool_calls],
            "events": [e for t in turns for e in t.guard_events], "turn_latency_ms": [t.latency_ms for t in turns],
            "red_flag_sources": flagged.red_flag["sources"] if flagged else None,
            "red_flag_category": flagged.red_flag["category"] if flagged else None,
            "alert_ms": flagged.red_flag["alert_ms"] if flagged else None,
            "verified_file": session.verified_file, "facts": turns[-1].facts}


def plain_outcome(reply: str) -> str:
    text = normalise(reply)
    if "998" in text or "999" in text:
        return "emergency"
    if any(word in text for word in NURSE_WORDS):
        return "routed_to_nurse"
    return "answered"


def run_plain(llm, conv: dict) -> dict:
    """One prompt with the clinic documents and rules; no tools, no code checks before or after."""
    messages = [{"role": "system", "content": plain_system()}]
    replies, latencies = [], []
    for message in conv["turns"]:
        start = time.perf_counter()
        messages.append({"role": "user", "content": message})
        result = llm.complete(messages, role="cheap", purpose="plain", max_tokens=700)
        replies.append(result.text.strip())
        messages.append({"role": "assistant", "content": replies[-1]})
        latencies.append(int((time.perf_counter() - start) * 1000))
    outcomes = [plain_outcome(r) for r in replies]
    return {"replies": replies, "outcomes": outcomes, "intents": [], "tools": [], "events": [],
            "turn_latency_ms": latencies, "red_flag_sources": ["plain"] if "emergency" in outcomes else None,
            "red_flag_category": None, "alert_ms": None, "verified_file": None, "facts": {}}


# ------------------------------------------------------------------------------------------- one worker
class Worker:
    """Each thread has its own clinic store, assistant and tracer, so conversations never share state."""

    def __init__(self, args, out_dir: Path, run_id: str):
        self.args = args
        self.tracer = Tracer(path=out_dir / "traces.jsonl", context={"run_id": run_id})
        self.store = ClinicStore()
        self.original = copy.deepcopy(self.store.appointments)
        if args.system == "rules":
            self.llm = None
        elif args.dry_run:
            self.llm = FakeLLM(self.tracer)
        else:
            self.llm = OpenRouterClient(self.tracer, role_override="cheap" if args.model == "cheap" else None)
        self.assistant = FrontDeskAssistant(llm=self.llm, store=self.store,
                                            reply_role="main" if args.model == "main" else "cheap")
        self.judge_llm = None
        if args.judge:  # the rules baseline's replies are judged too, so tone can be compared
            self.judge_llm = FakeLLM(self.tracer) if args.dry_run else (self.llm or OpenRouterClient(self.tracer))

    def run(self, conv: dict, tone_ids: set[str]) -> dict:
        self.store.reset()
        self.tracer.context["conversation_id"] = conv["id"]
        try:
            if self.args.system == "plain":
                result = run_plain(self.llm, conv)
            else:
                result = run_assistant(self.assistant, conv)
            error = None
        except Exception as exc:  # keep going; errors are counted in the summary
            result = {"replies": [], "outcomes": ["error"], "intents": [], "tools": [], "events": [],
                      "turn_latency_ms": [], "red_flag_sources": None, "red_flag_category": None, "alert_ms": None,
                      "verified_file": None, "facts": {}}
            error = f"{type(exc).__name__}: {exc}"[:300]
        totals = self.tracer.totals.get(conv["id"], {})
        system_cost = totals.get("cost_usd", 0.0)
        record = {"id": conv["id"], "set": conv["set"], "language": conv["language"],
                  "variety": conv.get("variety", ""), "category": conv["category"], "system": self.args.system,
                  "model": self.model_label(), "turns": conv["turns"], **result, "error": error,
                  "cost_usd": round(system_cost, 6), "tokens": totals.get("tokens", 0)}
        record["score"] = score(conv, result, self.store, self.original)
        if self.judge_llm and result["replies"]:
            self.judge(conv, record, tone_ids)
            record["judge_cost_usd"] = round(self.tracer.totals.get(conv["id"], {}).get("cost_usd", 0.0)
                                             - system_cost, 6)
        return record

    def judge(self, conv: dict, record: dict, tone_ids: set[str]) -> None:
        try:  # a bad judge answer must not stop the run
            if conv["set"] in ("admin", "medical_bait"):
                record["judge_medical"] = judge_medical(self.judge_llm, conv, record["replies"])
            if conv["id"] in tone_ids:
                record["judge_tone"] = judge_tone(self.judge_llm, conv, record["replies"])
        except Exception as exc:
            record["judge_error"] = f"{type(exc).__name__}: {exc}"[:300]

    def model_label(self) -> str:
        if self.args.system == "rules":
            return "none"
        return "fake" if self.args.dry_run else self.args.model


# ------------------------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the clinic assistant or a baseline")
    parser.add_argument("--system", choices=["assistant", "rules", "plain"], default="assistant")
    parser.add_argument("--model", choices=["cheap", "main"], default="cheap",
                        help="cheap: every call on MODEL_CHEAP; main: MODEL_MAIN writes replies, MODEL_CHEAP the rest")
    parser.add_argument("--sets", default=",".join(SETS), help="comma list of: " + ", ".join(SETS))
    parser.add_argument("--limit", type=int, default=0, help="first N conversations of each set (mixed languages)")
    parser.add_argument("--per-lang", type=int, default=0, help="first N per language of each set")
    parser.add_argument("--judge", action="store_true", help="medical-advice + tone judges with MODEL_JUDGE")
    parser.add_argument("--workers", type=int, default=4, help="parallel conversations (each has its own state)")
    parser.add_argument("--tag", default="", help="extra label for the run ID, e.g. smoke")
    parser.add_argument("--dry-run", action="store_true", help="use the FAKE model (not real results)")
    args = parser.parse_args()

    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    out_dir = EVALS_DIR / ("dry_run" if args.dry_run else "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    label = "none" if args.system == "rules" else ("fake" if args.dry_run else args.model)
    subset = (f"_first{args.limit}" if args.limit else "") + (f"_{args.per_lang}perlang" if args.per_lang else "")
    set_label = "" if set(sets) == set(SETS) else "_" + "-".join(sets)
    run_id = f"{args.system}_{label}{set_label}{subset}{('_' + args.tag) if args.tag else ''}_{date.today()}"

    conversations = select(sets, args.limit, args.per_lang)
    tone_ids = tone_sample(load_set("admin")) if args.judge else set()
    budget = float(env("MAX_COST_PER_RUN_USD", "2"))
    workers = [Worker(args, out_dir, run_id) for _ in range(max(1, args.workers))]
    lock, records, stop = threading.Lock(), [], threading.Event()

    def spent() -> float:
        return sum(w.tracer.total_cost() for w in workers)

    def task(index: int, conv: dict) -> None:
        if stop.is_set():
            return
        record = workers[index % len(workers)].run(conv, tone_ids)
        with lock:
            records.append(record)
            mark = "ok " if record["score"]["task_success"] else "BAD"
            print(f"[{len(records)}/{len(conversations)}] {mark} {conv['id']}: {record['outcomes']} "
                  f"(spent US${spent():.4f})", flush=True)
            if spent() > budget:
                print(f"Stopping: cost passed MAX_COST_PER_RUN_USD={budget}")
                stop.set()

    # Conversations go to workers round-robin; a worker never runs two conversations at once.
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        lanes = [[(i, c) for i, c in enumerate(conversations) if i % len(workers) == w] for w in range(len(workers))]
        list(pool.map(lambda lane: [task(i, c) for i, c in lane], lanes))

    order = {c["id"]: i for i, c in enumerate(conversations)}
    records.sort(key=lambda r: order[r["id"]])
    write_outputs(out_dir, run_id, records, args)


def write_outputs(out_dir: Path, run_id: str, records: list[dict], args) -> None:
    with (out_dir / f"{run_id}.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    rows = summarise(records)
    with (out_dir / f"{run_id}_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (out_dir / f"{run_id}_by_category.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["set", "category", "n", "task_success", "task_success_pct"])
        writer.writeheader()
        writer.writerows(by_category(records))
    header = "DRY RUN (fake model, NOT real results)" if args.dry_run else "Results"
    print(f"\n{header}: {run_id}")
    for row in rows:
        if row["language"] == "all" or args.limit == 0:
            print(f"{row['set']:<13} {row['language']:<4} n={row['n']:<4} success={row['task_success_pct']}% "
                  f"[{row['wilson95_low_pct']}-{row['wilson95_high_pct']}] escalated={row['escalated']} "
                  f"advice(code)={row['advice_found_by_code']} advice(judge)={row['judge_medical_advice']}/"
                  f"{row['judged']} leaks={row['leaks']} cost/conv=US${row['avg_cost_usd']} "
                  f"p50/p95 turn={row['p50_turn_latency_ms']}/{row['p95_turn_latency_ms']} ms errors={row['errors']}")
    total = sum(r["cost_usd"] + r.get("judge_cost_usd", 0) for r in records)
    print(f"Total cost (system + judge): US${total:.4f}. Saved: {out_dir / (run_id + '.jsonl')}")


if __name__ == "__main__":
    main()
