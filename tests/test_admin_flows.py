"""Admin flows with the offline FakeLLM: booking, rescheduling, cancelling, information, disclosure."""

from __future__ import annotations

import pytest

from clinic_assistant import keyword_brain
from clinic_assistant.assistant import clean_understanding
from clinic_assistant.clinic import resolve_insurer

from .conftest import ScriptedLLM, identity, understanding


@pytest.mark.parametrize("message, marker", [("Hi", "AI assistant"), ("مرحبا", "ذكاء اصطناعي"),
                                             ("Bonjour", "assistant IA")])
def test_first_reply_says_it_is_an_ai_and_how_to_reach_a_person(chat, message, marker):
    turns, _, _ = chat([message, "What are your opening hours?"])
    assert marker in turns[0].reply and "+971 4 000 0000" in turns[0].reply
    assert marker not in turns[1].reply  # only once


def test_book_an_exact_free_slot(chat, store):
    slot = store.find_slots(doctor_id="D03", day="2026-10-13")[0]
    turns, _, _ = chat([f"I'd like to book Dr Mansour on 13/10 at {slot['time']}. {identity(store, 'NFC-10050')}"])
    assert turns[0].outcome == "booked"
    assert turns[0].tool_calls == ["verify_identity", "book_slot"]
    booked = store.upcoming("NFC-10050")
    assert booked and booked[-1]["time"] == slot["time"] and booked[-1]["doctor_id"] == "D03"


def test_offer_slots_then_book_the_chosen_one(chat, store):
    offered = store.find_slots(doctor_id="D04", day="2026-10-14", part="morning")
    turns, _, _ = chat([f"I need an appointment with Dr Benali on 14/10 in the morning. {identity(store, 'NFC-10051')}",
                        "The second one please."])
    assert [t.outcome for t in turns] == ["slots_offered", "booked"]
    assert store.upcoming("NFC-10051")[-1]["time"] == offered[1]["time"]


def test_identity_can_come_in_a_later_message(chat, store):
    slot = store.find_slots(doctor_id="D01", day="2026-10-15")[0]
    turns, _, _ = chat([f"Can I book Dr Haddad on 15/10 at {slot['time']}?", identity(store, "NFC-10052")])
    assert [t.outcome for t in turns] == ["identity_request", "booked"]


def test_reschedule_keeps_the_same_doctor(chat, store):
    appointment = store.upcoming("NFC-10002")[0]
    new = store.find_slots(doctor_id=appointment["doctor_id"], day="2026-10-20")[0]
    turns, _, _ = chat([f"Please reschedule my appointment to {new['date']} at {new['time']}. "
                        f"{identity(store, 'NFC-10002')}"])
    assert turns[0].outcome == "rescheduled"
    moved = store.upcoming("NFC-10002")[0]
    assert (moved["date"], moved["time"], moved["doctor_id"]) == (new["date"], new["time"], appointment["doctor_id"])


def test_cancel(chat, store):
    turns, _, _ = chat([f"Please cancel my appointment. {identity(store, 'NFC-10005')}"])
    assert turns[0].outcome == "cancelled"
    assert store.upcoming("NFC-10005") == []


def test_cancel_without_an_appointment(chat, store):
    turns, _, _ = chat([f"Please cancel my appointment. {identity(store, 'NFC-10055')}"])
    assert turns[0].outcome == "no_appointment"


def test_availability_needs_no_identity_and_changes_nothing(chat, store):
    before = [dict(a) for a in store.appointments]
    turns, _, _ = chat(["Is Dr Nair available on 15/10?"])
    assert turns[0].outcome == "slots_shown"
    assert store.appointments == before


@pytest.mark.parametrize("message, topic", [("What are your opening hours?", "hours"),
                                            ("Where is the clinic? Is there parking?", "location"),
                                            ("Do I need to fast before my blood test?", "preparation"),
                                            ("وش أوراق الموافقة المسبقة؟", "preapproval_documents")])
def test_clinic_information_comes_from_the_clinic_documents(chat, message, topic):
    turns, _, _ = chat([message])
    assert turns[0].outcome == f"info:{topic}"
    assert turns[0].tool_calls == ["policy_lookup"]


def test_insurance_check_uses_the_insurer_list(chat):
    accepted, _, _ = chat(["Do you accept Gulf Shield Health?"])
    refused, _, _ = chat(["Do you accept Coral Life insurance?"])
    assert accepted[0].facts["insurance"]["accepted"] is True
    assert refused[0].facts["insurance"]["accepted"] is False


@pytest.mark.parametrize("message", ["مرحبا عيادة صحارى", "هل عيادة صحارى التجريبية للعائلة مفتوحة يوم السبت؟",
                                     "Hi Sahara Demo Family Clinic"])
def test_clinic_name_is_not_read_as_an_insurer(chat, message):
    """Regression: the clinic's Arabic name contains صحارى, which used to be a keyword for a fictional insurer
    ("Sahara Mutual", renamed "Lotus Mutual Insurance (demo)")."""
    assert resolve_insurer(message) is None
    understood = keyword_brain.understand(message)
    assert understood["insurer"] is None and understood["intent"] != "insurance_check"
    turns, _, _ = chat([message])
    assert turns[0].outcome != "insurance_answered"


def test_renamed_insurer_is_still_recognised(chat):
    messages = ["Do you accept Lotus Mutual?", "هل تقبلون تأمين لوتس؟", "Acceptez-vous l'Assurance mutuelle Lotus ?"]
    for message in messages:
        turns, _, _ = chat([message])
        assert turns[0].facts["insurance"]["insurer"] == "Lotus Mutual Insurance (demo)", message
        assert turns[0].facts["insurance"]["accepted"] is True


def test_lab_status_says_ready_or_not_only(chat, store):
    turns, _, _ = chat([f"Is my result ready? {identity(store, 'NFC-10011')}"])
    assert turns[0].outcome == "lab_status"
    assert turns[0].facts["tests"][0]["status"] in ("ready", "processing")


def test_asking_for_a_person_goes_to_the_handover_queue(chat):
    turns, _, assistant = chat(["I want to talk to a real person"])
    assert turns[0].outcome == "handover"
    assert assistant.desk.queue[-1]["kind"] == "reception"


def test_two_unclear_messages_in_a_row_go_to_a_person(chat):
    turns, _, _ = chat(["blue banana", "purple elephant"])
    assert [t.outcome for t in turns] == ["clarify", "handover"]


def test_model_outage_falls_back_to_keywords_and_templates(chat, store):
    llm = ScriptedLLM({"red_flag": RuntimeError("down"), "understand": RuntimeError("down"),
                       "reply": RuntimeError("down")})
    turns, _, _ = chat([f"Please cancel my appointment. {identity(store, 'NFC-10005')}"], llm=llm)
    assert turns[0].outcome == "cancelled"
    assert any(e.startswith("understand_fallback") for e in turns[0].guard_events)
    assert any(e.startswith("reply_model_failed") for e in turns[0].guard_events)


def test_model_cannot_invent_a_doctor_or_a_bad_date(store):
    cleaned = clean_understanding({"intent": "book", "doctor_id": "D99", "date": "next week", "time": "25:99",
                                   "file_number": "10012", "confidence": 0.9}, store)
    assert cleaned["doctor_id"] is None and cleaned["date"] is None and cleaned["time"] is None
    assert cleaned["file_number"] == "NFC-10012"


def test_low_confidence_becomes_a_clarifying_question(chat):
    llm = ScriptedLLM({"red_flag": {"emergency": False},
                       "understand": understanding(intent="cancel", confidence=0.2)})
    turns, _, _ = chat(["mmm"], llm=llm)
    assert turns[0].outcome == "clarify"
