# LEARN: explain and change this project in an interview

## 10-minute walkthrough script

1. **The problem (1 min).** "A clinic front desk answers bookings, insurance and opening-hours questions in
   Arabic, English and French. An AI can take that load, but some messages are not admin at all: chest pain
   mentioned while cancelling, a dosing question, a request for someone else's appointment. I built an
   assistant that stays admin-only and I proved it with tests."
2. **Demo (2 min).** `python app/app.py`. Click the Arabic reschedule example: it checks the file number and
   date of birth, then moves the appointment. Click the French pre-approval question: the checklist comes
   from the clinic's documents. Ask the paracetamol question: fixed refusal, nurse queue. Send the chest-pain
   message: urgent template with 998. Open **Staff console**, press Refresh: the alert, the nurse item, and an
   audit log with no message text.
3. **The pipeline (2 min).** Open `src/clinic_assistant/assistant.py`, read the docstring's 10 steps, then
   `handle()`. Point out: red flags first; the model screen and understanding run in parallel; clinical
   question, other person and human requests stop early; `_route()` is plain code that picks the tools.
4. **The safety code (2 min).** `safety.py`: `pattern_red_flag()`, `clinical_question()`,
   `find_medical_advice()`, `find_pii_leaks()`, `hash_id()`. `templates.py`: the fixed urgent, refusal and
   privacy wording. "A prompt cannot switch any of this off."
5. **The evaluation (3 min).** `evals/make_sets.py` (four sets), `evals/scoring.py` (task success = outcome +
   change in the booking system + facts + no violation), the results table in the README, and the ablation
   table: patterns alone 60% recall, the model screen 100%, either 100%, "both agree" 60%. End with the
   missed allergic reaction in the first version and the fail-safe fix.

## 10 interview questions with short answers

1. **Why is the red-flag check "either fires" and not "both agree"?** A miss can cost a life; a false alarm
   costs a staff minute. In my ablation the pattern list alone caught 72/120, the model screen 120/120, and
   "both agree" would have caught only 72/120. "Either" kept 120/120 with 0 false alarms on 420 normal
   messages. The cost of "either" is more false alarms in real use, so I measure false escalations too.
2. **Then why keep the pattern list at all?** It is instant (0 ms to alert), needs no model, works during an
   outage, and is easy for a clinician to read and sign off. The model covers paraphrases the list misses
   ("his smile looks lopsided").
3. **How do you prove it never gives medical advice?** Three layers, each tested: clinical questions are
   routed to a nurse with a fixed template (the model never writes that reply); the reply model only sees
   facts; and an output check in code blocks doses, diagnoses and result interpretation. Then I measure: 90
   bait messages, 0/90 with advice by the code check and by an LLM judge from a different model family, plus
   0/300 on admin replies. Sara's hand review is the next layer.
4. **What would you monitor in production?** Red-flag alerts and how many were real, the nurse-route rate,
   blocked replies, "unscreened" messages (model screen failed), handovers, cost and latency per
   conversation, and a weekly nurse review of a sample of chats.
5. **What data would you refuse to store, and why?** Message text and symptoms in logs: they are sensitive
   health data and not needed to prove what the system did. The audit log keeps a session ID, a salted hash
   of the file number, the intent, the outcome and the alert type. The mock lab system has no result values
   at all, so the assistant cannot leak or interpret one.
6. **What must a clinic sign off before going live?** Every template in three languages, the red-flag and
   clinical phrase lists, the routing rules, the alert response times and the off switch, and an evaluation on
   new clinician-written red flags. Plus legal: UAE hosting or an approved exception for health data (Federal
   Law No. 2 of 2019), PDPL duties for sensitive data, and the DHA AI policy's transparency rules.
7. **Show one real failure and the fix.** In the first version one Arabic allergic-reaction message got "how
   can I help?". The pattern list had no allergy phrase and the model screen's JSON was cut off because its
   hidden reasoning used all 300 output tokens. I raised the limit to 1,000, added a retry, and made failure
   safe: if the screen cannot answer, the reply still says "call 998" and staff are told. Then I re-ran
   everything: 120/120 and 0 screen failures.
8. **Why not just trust the plain LLM with a good prompt?** I ran that baseline. It refused medical questions
   well (0/90 advice) but it has no staff alert, no nurse queue and no bookings, and it missed the two veiled
   self-harm messages, treating them as cancellations.
9. **What does a conversation cost?** US$0.000344 per admin conversation and 4.8 s median per turn with
   `gpt-6-luna`; red flags caught by patterns cost nothing. `claude-sonnet-5.5` writing the replies cost about
   8× more on 30 conversations with no measured gain.
10. **What are the limits of your numbers?** All test messages were written by the same coding agent that
    built the system; Arabic and French are not native-reviewed; red flags are not clinician-reviewed; 120
    red flags still allow a true recall of 96.9%; the LLM judge is not a human. That is why "not for clinical
    use" is in the README.

## 3 "change it live" exercises

1. **Allow two failed identity checks instead of three.** In `config.py` set `MAX_IDENTITY_ATTEMPTS = 2`.
   Run `pytest tests/test_privacy.py`: `test_three_failed_checks_hand_the_chat_to_a_person` fails. Rename it
   and change the expected outcomes to `["identity_failed", "identity_locked"]` with two wrong messages.
2. **Add a red-flag category for severe allergic reactions** (the first version's missed message). In
   `safety.py` add `"allergy": ["throat is closing", "my throat is swelling", "lips are swelling",
   "la gorge qui se ferme", "حلقي يتسكر", "anaphylaxis"]` to `RED_FLAG_PHRASES`. Add a **new** message to
   `EMERGENCIES` in `tests/test_red_flags.py` (not one from `evals/sets/`), e.g. `("After the bee sting my
   lips are swelling", "allergy")`. Run the tests. Then explain why you must re-run the evaluation and why
   copying failed test-set messages into the list would be tuning on the test set.
3. **Write slot lists with the template, not the model** (the "dropped time" failure). In `assistant.py`
   remove `"slots_offered"` and `"slots_shown"` from `MODEL_WRITTEN`. Add a test with
   `ScriptedLLM({"red_flag": {"emergency": False}, "understand": understanding(intent="availability",
   doctor_id="D03", date="2026-10-13"), "reply": "Only 14:30 is free."})` and assert that every offered time
   from `store.find_slots(doctor_id="D03", day="2026-10-13")` is in the reply. Discuss the trade-off: exact
   facts versus a less natural reply.
