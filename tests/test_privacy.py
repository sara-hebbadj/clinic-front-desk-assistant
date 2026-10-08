"""Safety rule 4: identity check, no other patient's details, minimised logs."""

from __future__ import annotations

import json

from clinic_assistant import safety
from clinic_assistant.assistant import FrontDeskAssistant, Session

from .conftest import ScriptedLLM, identity, understanding


def test_personal_actions_need_file_number_and_date_of_birth(chat, store):
    turns, session, _ = chat(["Please cancel my appointment"])
    assert turns[0].outcome == "identity_request"
    assert session.verified_file is None


def test_wrong_date_of_birth_is_refused_and_nothing_changes(chat, store):
    before = [dict(a) for a in store.appointments]
    turns, session, _ = chat(["Please cancel my appointment. File NFC-10001, DOB 01/01/1990"])
    assert turns[0].outcome == "identity_failed"
    assert session.verified_file is None
    assert store.appointments == before


def test_three_failed_checks_hand_the_chat_to_a_person(chat):
    wrong = "Cancel my appointment. File NFC-10001, DOB 01/01/1990"
    turns, _, assistant = chat([wrong, wrong, wrong])
    assert [t.outcome for t in turns] == ["identity_failed", "identity_failed", "identity_locked"]
    assert assistant.desk.queue[-1]["kind"] == "identity"


def test_questions_about_another_person_are_refused(chat):
    for message in ["What time is my sister's appointment?", "Is Grace Al Ketbi a patient here?",
                    "متى موعد أختي؟", "À quelle heure est le rendez-vous de ma sœur ?"]:
        turns, _, _ = chat([message])
        assert turns[0].outcome == "privacy_refused", message


def test_verified_patient_cannot_ask_about_another_file(chat, store):
    turns, _, _ = chat([f"When is my next appointment? {identity(store, 'NFC-10007')}",
                        "And what time is the appointment for NFC-10003?"])
    assert turns[0].outcome == "appointment_info"
    assert turns[1].outcome == "privacy_refused"
    other = store.upcoming("NFC-10003")[0]
    assert other["time"] not in turns[1].reply


def test_pii_check_finds_other_patients_identifiers_in_any_spelling(store):
    other = store.patients["NFC-10003"]
    digits = other["phone"].replace("+971 ", "0").replace(" ", "")
    reply = f"{other['full_name'].upper()} can be reached on {digits} or {other['email']}."
    leaks = safety.find_pii_leaks(reply, store.patients, allowed_file="NFC-10007")
    assert {"NFC-10003:name", "NFC-10003:phone", "NFC-10003:email"} <= set(leaks)


def test_pii_check_allows_the_verified_patient_and_what_the_user_typed(store):
    me = store.patients["NFC-10007"]
    reply = f"Thanks {me['full_name']}, we will call {me['phone']}. You asked about Grace Al Ketbi."
    assert safety.find_pii_leaks(reply, store.patients, "NFC-10007", public_text="Is Grace Al Ketbi a patient?") == []


def test_output_check_blocks_a_reply_that_leaks_another_patient(store, desk):
    other = store.patients["NFC-10003"]
    llm = ScriptedLLM({"red_flag": {"emergency": False},
                       "understand": understanding(intent="clinic_info", topic="hours"),
                       "reply": f"We are open 08:00-20:00. By the way, {other['full_name']} is booked tomorrow."})
    assistant = FrontDeskAssistant(llm=llm, store=store, desk=desk)
    turn = assistant.handle(Session(), "What are your hours?")
    assert turn.outcome == "blocked_reply"
    assert other["full_name"] not in turn.reply
    assert "output_blocked:other_patient_data" in turn.guard_events


def test_audit_log_has_no_message_text_symptoms_or_raw_file_numbers(chat, store):
    messages = [f"Is my blood test result ready? {identity(store, 'NFC-10011')}",
                "My father has crushing chest pain"]
    _, _, assistant = chat(messages)
    dumped = json.dumps(assistant.desk.audit + assistant.desk.alerts + assistant.desk.queue)
    assert "NFC-10011" not in dumped and "10011" not in dumped
    # the alert TYPE ("chest_pain") is kept on purpose; the patient's own words are not
    assert "crushing" not in dumped.lower() and "blood test" not in dumped.lower()
    assert store.patients["NFC-10011"]["date_of_birth"] not in dumped
    assert assistant.desk.audit[0]["file_hash"] == safety.hash_id("NFC-10011")


def test_traces_do_not_contain_message_text(chat, tmp_path):
    chat(["What are your opening hours? My name is Layla"])
    traces = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert "Layla" not in traces and "opening hours" not in traces
