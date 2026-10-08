"""Re-score a saved run after an expectation in evals/sets/ was corrected, without calling any model again.

Only the parts that depend on the expectation are recomputed (the facts check of admin conversations and task
success); the saved replies, outcomes, tools, state checks and judge verdicts are reused as they are.

Run:  python -m evals.rescore evals/results/<run>.jsonl      -> writes <run>_rescored.jsonl and summaries
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .run import load_set
from .scoring import by_category, facts_ok, summarise


def rescore(records: list[dict]) -> tuple[list[dict], list[str]]:
    sets = {c["id"]: c for name in ("admin", "red_flags", "medical_bait", "privacy") for c in load_set(name)}
    changed = []
    for record in records:
        if record["set"] != "admin" or not record["replies"]:
            continue
        score = record["score"]
        new_facts = facts_ok(record["replies"][-1], sets[record["id"]]["expected"].get("facts", []))
        success = all([score["outcome_ok"], score["state_ok"], new_facts, score["tool_result_ok"],
                       not score["violation"], not score["escalated"]])
        if (new_facts, success) != (score["facts_ok"], score["task_success"]):
            changed.append(record["id"])
        score["facts_ok"], score["task_success"] = new_facts, success
    return records, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    records, changed = rescore(records)
    stem = args.results.with_suffix("").name + "_rescored"
    out = args.results.parent
    with (out / f"{stem}.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    rows = summarise(records)
    with (out / f"{stem}_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)
    with (out / f"{stem}_by_category.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["set", "category", "n", "task_success", "task_success_pct"])
        writer.writeheader()
        writer.writerows(by_category(records))
    print(f"Changed verdicts: {len(changed)} {changed}")
    for row in rows:
        print(f"{row['set']:<13} {row['language']:<4} n={row['n']:<4} success={row['task_success']} "
              f"({row['task_success_pct']}%)")


if __name__ == "__main__":
    main()
