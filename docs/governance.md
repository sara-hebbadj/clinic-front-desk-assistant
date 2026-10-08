# Governance pack: Sahara Demo Family Clinic front-desk assistant (fictional)

Version 0.1, 8 October 2026. Format reused from the AI governance pack in this portfolio (P8), cut to two pages.

> **General information, not legal advice.** This describes a portfolio prototype on synthetic data. It is
> **not for clinical use**. Ask a UAE-qualified lawyer and the clinic's medical director before any real use.

## 1. System card

| | |
|---|---|
| **What it is** | A WhatsApp-style AI assistant for the front desk of a fictional Dubai clinic. Arabic (incl. Gulf dialect, Arabizi), English, French. |
| **Allowed uses** | Booking, rescheduling, cancelling; doctor availability; opening hours and directions; what to bring; the clinic's own written preparation instructions; accepted insurers and the pre-approval checklist; billing questions; whether a lab result is **ready**; call-back requests. |
| **Not allowed (by design and by test)** | Diagnosis; medicines or doses; explaining symptoms or results; reassurance about symptoms; triage decisions; any information about another patient. |
| **Users** | Patients (chat); reception, nurses and billing staff (staff console: alerts, handover queue, audit log). |
| **Models** | `openai/gpt-6-luna` via OpenRouter for the red-flag screen, understanding and admin replies. Fixed templates for every safety reply. |
| **Data** | Synthetic only (60 patients, seed 42). Lab orders hold a status, never a value. |
| **Evidence (8 Oct 2026, final version)** | Red-flag recall 120/120 (95% CI 96.9–100); 0/90 medical advice on bait (code and LLM judge); 0/30 privacy leaks; 295/300 admin task success; 0/300 false escalations. Full table and caveats in the [README](../README.md#results). |
| **Status** | Prototype. **No-go for real patients** until the conditions in section 4 are met. |

## 2. Risk register (top 8)

| # | Risk | Control in the system | Test evidence |
|---|---|---|---|
| R1 | A possible emergency is treated as an admin message | Pattern list **or** model screen (either fires); urgent template with 998; staff alert; emergency chat stays in urgent mode; if the screen fails twice, the reply still carries 998 and staff are told | `tests/test_red_flags.py` (12 messages, model-only, pattern-wins, outage, unscreened); live 120/120; ablation: patterns alone 72/120, model alone 120/120 |
| R2 | The assistant gives medical advice | Clinical-question check (model flag or patterns) → fixed refusal + nurse queue; output check blocks doses, diagnoses, result interpretation, treatment tips; model sees only facts | `tests/test_medical_advice.py`; live 0/90 bait and 0/300 admin replies with advice (code + judge) |
| R3 | Another patient's data is disclosed | Identity check in code (file number + date of birth), repeated in the API; requests about others refused; output check for names, phones, emails, file numbers, dates of birth in any spelling | `tests/test_privacy.py`; live 0/30 leaks |
| R4 | Over-refusal or over-routing frustrates patients | Measured, not hidden: wrong refusals and handovers count as failures | Live: 5/300 admin failures, all refusals or handovers (README "What failed") |
| R5 | Sensitive data in logs | Audit log has session ID, salted file-number hash, intent, outcome, tools, alert type; traces hold tokens and cost only | `test_audit_log_has_no_message_text...`, `test_traces_do_not_contain_message_text` |
| R6 | Model outage or bad JSON | Pattern list needs no model; keyword fallback for understanding; template fallback for replies; screen retried, then fail-safe 998 line | `test_model_outage_*`, `test_unscreened_message_still_shows_998_and_goes_to_staff` |
| R7 | Language gap (Arabic dialects, Arabizi) | Patterns in Gulf Arabic and Arabizi; per-language metrics | Live admin AR 99 / EN 96 / FR 100; pattern recall AR 20/40 vs FR 27/40 (the model screen closes the gap). Native review pending |
| R8 | People trust a demo as a clinical tool | "Not for clinical use" in the app, README and this card; AI disclosure in the first reply | `test_first_reply_says_it_is_an_ai...` (3 languages) |

## 3. Rules notes (UAE, general information)

Checked on 8 October 2026 against the IBA article "How is AI in healthcare being regulated in the UAE?"
(Mukherjee and Alase, 11 May 2026) and the UAE government portal u.ae ("Handling emergencies").

- **Emergency numbers (u.ae):** 999 police, 998 ambulance, 997 civil defence. The assistant uses 998 (and 999
  in the self-harm template).
- **DHA Policy for Use of AI in Healthcare (Dubai, 2021):** principles of ethics, accountability,
  transparency, safety and security, and privacy; users should get clear explanations of the AI's role.
  Here: AI disclosure in the first reply, a documented scope, a staff console and an audit trail.
- **Federal Law No. 2 of 2019 (ICT in health fields):** health data must be kept confidential and available
  only to authorised parties, and generally stored and processed in the UAE (exceptions under Ministerial
  Decision No. 51 of 2021). Here: synthetic data only. A real clinic would need UAE hosting (or an approved
  exception) for any model that sees patient messages, and its health-information-exchange and cybersecurity
  obligations (e.g. NABIDH in Dubai).
- **PDPL (Federal Decree-Law No. 45 of 2021):** health data is sensitive personal data and needs stricter
  protection; the PDPL does not apply where a specific health-data law does, so both must be checked.
  Here: data minimisation (no symptoms in logs, hashed file numbers), purpose limited to admin.
- **Medical-device rules:** an assistant that gave clinical advice could become software as a medical device
  (MOHAP oversight). Keeping it admin-only, and proving that, is part of staying out of that category.

## 4. Human oversight design

| Item | Design (for a real clinic; the demo shows the console only) |
|---|---|
| Who receives red-flag alerts | The duty nurse on shift (pager or phone push) and the reception supervisor; the console shows the alert type, never the message text |
| Response time targets | Red-flag alert: acknowledged within 2 minutes in opening hours; outside hours the patient has already been told to call 998. Nurse call-back: same working day. Reception handover: 1 working hour |
| What staff can do | Open the chat, call the patient, close the alert with a note; review any "blocked reply" or "unscreened" item |
| Off switch | One configuration flag turns the assistant into "fixed message + phone number" mode; it must also switch off automatically if the model screen keeps failing (the unscreened count is watched) |
| Monitoring | Weekly: red-flag alerts (true and false), nurse-route rate, blocked replies, unscreened messages, handover rate, cost per conversation; a sample of chats reviewed by a nurse |
| Clinical sign-off before go-live | Every template (3 languages), the red-flag and clinical phrase lists, the routing rules, and an evaluation on new, clinician-written red flags and real (consented, anonymised) message styles |
| Change control | Any change to `safety.py`, `templates.py` or a prompt re-runs the full evaluation; a red-flag miss blocks release |
