# Notes for coding agents working on this repo

Project P14 of Sara Hebbadj's portfolio: an **admin-only** WhatsApp-style front-desk assistant for the
fictional "Sahara Demo Family Clinic" in Dubai (Arabic, English, French). Sara must be able to explain every line, so
keep functions short and names plain.

## Layout

- `src/clinic_assistant/assistant.py`: the pipeline, one `handle()` call per message. Read its docstring first.
- `safety.py`: red-flag phrases, clinical-question phrases, the output checks (medical advice, other patients'
  data) and file-number hashing. **Never move these rules into a prompt.**
- `templates.py`: fixed safety replies (urgent, refusal, privacy, identity) in AR/EN/FR. A model never writes
  these. Any change needs clinical sign-off in a real deployment.
- `clinic.py` (in-memory mock booking system), `clinic_api.py` (the same system behind FastAPI).
- `knowledge.py`: clinic documents split by `## topic: Title` headings in `data/clinic_docs_*.md`.
- `keyword_brain.py`: keyword understanding = rules baseline, offline demo and test stand-in.
- `llm.py`: the only place that calls a model (`OpenRouterClient`, `FakeLLM`, `Tracer`).
- `staff.py`: alerts, handover queue, audit log. **No message text, no raw file numbers in any record.**
- `evals/`: `make_sets.py` (writes the 4 sets), `run.py`, `scoring.py`, `judge.py`, `redflag_ablation.py`, `stats.py`.

## Rules

- Tests never touch the network (a fixture blocks sockets) and never need keys. Use `FakeLLM` or
  `tests/conftest.py::ScriptedLLM`.
- Do not edit `evals/sets/*.jsonl` by hand; change `evals/make_sets.py` and re-run it. Changing a set or the
  red-flag / clinical phrase lists after a run invalidates earlier results: re-run and say so in RESULTS.md.
- Do not add phrases to `safety.py` just because an evaluation item failed: that is tuning on the test set.
  Add new test messages first (new items, written before the change), then change the list.
- Real results go in `evals/results/`, fake ones in `evals/dry_run/`. Never copy a dry-run number anywhere.
- Every safety rule has a test: red flags (`test_red_flags.py`), no medical advice (`test_medical_advice.py`),
  privacy and minimised logs (`test_privacy.py`), AI disclosure (`test_admin_flows.py`).
- Keys come from `Portfolio Projects/.env` or environment variables. Never print or commit them.
- Synthetic data only. No real patients, no medical Q&A datasets. Not for clinical use.
- Ask Sara before creating a GitHub repo, pushing, or deploying a Space.

## Checks before you finish

```bash
pytest -q
ruff check .
python -m evals.run --system assistant --dry-run --limit 3   # pipeline still works end to end
```
