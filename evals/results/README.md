# Saved evaluation runs (8 October 2026)

All runs use the four sets in `../sets/` (300 admin conversations, 120 red flags, 90 medical-advice requests,
30 privacy probes; one third each in Arabic, English and French). Every model call is in `traces.jsonl`
(model, tokens, OpenRouter cost, latency; no message text).

## Current results (quoted in the README and RESULTS.md)

| File prefix | What | Command |
|---|---|---|
| `assistant_cheap_final_2026-10-08` | The assistant, every call on `openai/gpt-6-luna`, judges on `google/gemini-3.8-flash` | `python -m evals.run --system assistant --model cheap --judge --workers 10 --tag final` |
| `rules_none_after_renames_2026-10-08` | Rules baseline re-run (free) after renaming the clinic and one insurer and fixing an Arabic-punctuation word-boundary bug: identical numbers | `python -m evals.run --system rules --tag after_renames` |
| `rules_none_2026-10-08` | Rules-only baseline (keywords, templates, same red-flag pattern list), no model | `python -m evals.run --system rules` |
| `plain_cheap_red_flags-medical_bait-privacy_2026-10-08` | Plain LLM baseline: one prompt with the clinic documents and rules, no tools, no code checks | `python -m evals.run --system plain --model cheap --sets red_flags,medical_bait,privacy --judge` |
| `redflag_ablation_cheap_final_2026-10-08` | Pattern list and model screen measured separately on all 540 first messages | `python -m evals.redflag_ablation --model cheap --tag final` |
| `comparison_2026-10-08.csv` | Side-by-side table built from the three result files above | `python -m evals.compare ...` (see the README) |

`_summary.csv` = metrics per set and language with 95% Wilson intervals; `_by_category.csv` = task success per
category; `.jsonl` = every conversation with replies, outcomes, tools, events, scores and judge verdicts.

## Kept for the record (`superseded/`)

| File | Why it is superseded |
|---|---|
| `rules_none_before_suffix_fix_*` | First rules run, before two text-matching bugs were fixed (Arabic possessive suffixes such as حرارتها; the French "œ" in "sœur"). Red-flag recall moved from 70/120 to 72/120. |
| `v1_assistant_cheap_full_*` and `v1_repeat_assistant_cheap_*` | Two complete runs of the earlier version (the second was started by mistake while the first was still running, so the same version ran twice). The model red-flag screen had `max_tokens=300`; in the repeat run one Arabic emergency (rf-ar-012, an allergic reaction) was missed because the screen's answer was cut off. `*_rescored` files apply the corrected "hours" expectations (`python -m evals.rescore`). |
| `v1_redflag_ablation_*` | Same issue: 4 of 540 screen calls returned no valid JSON. |
| `v1_assistant_main_admin_10perlang_*` | `MODEL_MAIN` comparison on 30 admin conversations. It ran on the earlier version, but no red-flag screen call failed in it, so the later fix does not touch these conversations. Quoted in the README with that note. |

`smoke/` holds the first 12-conversation live smoke test.
