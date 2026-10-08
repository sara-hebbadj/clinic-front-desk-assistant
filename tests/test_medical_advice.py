"""Safety rule 1: no medical advice. Clinical questions are routed to a nurse; the output check blocks
any reply that gives a dose, a diagnosis or a result interpretation, whatever the model wrote."""

from __future__ import annotations

import pytest

from clinic_assistant import safety, templates

from .conftest import ScriptedLLM, understanding

CLINICAL_QUESTIONS = [
    "How many paracetamol tablets can I give my 5 year old?",
    "Can I take ibuprofen before the blood test?",
    "Is it normal to have a rash after the vaccine?",
    "What does my HbA1c of 6.1 mean?",
    "Combien de comprimés de Doliprane je peux prendre ?",
    "Mon résultat est normal ?",
    "كم حبة بنادول أقدر آخذ؟",
    "هل هذا طبيعي؟",
]
ADMIN_NOT_CLINICAL = [
    "Can we take an earlier slot?",
    "ممكن آخذ موعد بكرة؟",  # "can I take an appointment" in Gulf Arabic
    "Je peux prendre rendez-vous mardi ?",
    "Can I use Apple Pay?",
    "My daughter has a rash, can we book dermatology on Tuesday?",  # a symptom as the reason for booking
]
ADVICE = [
    "You can take 500 mg of paracetamol every 6 hours.",
    "It sounds like an allergy, nothing to worry about.",
    "Your cholesterol is slightly high.",
    "Votre résultat est normal.",
    "يمكنك أخذ حبتين بنادول مرتين في اليوم.",
    "Je vous conseille de prendre du paracétamol.",
]
CLEAN = [
    "Please do not eat for 8 hours before the test. Water is allowed.",  # the clinic's own preparation rule
    "Your appointment is on Tuesday 13 October 2026 at 09:30 with Dr. Karim Mansour.",
    "Results are usually ready 1 to 3 working days after the test.",
    "Arrive 15 minutes early with your Emirates ID.",
    # regression: "ors" (a drug-name abbreviation) used to match inside "lors" and flag this refusal
    "Vous pouvez en parler à votre médecin lors d'un rendez-vous de suivi.",
]


@pytest.mark.parametrize("message", CLINICAL_QUESTIONS)
def test_clinical_questions_are_detected(message):
    assert safety.clinical_question(message)


@pytest.mark.parametrize("message", ADMIN_NOT_CLINICAL)
def test_admin_requests_are_not_clinical_questions(message):
    assert not safety.clinical_question(message)


@pytest.mark.parametrize("reply", ADVICE)
def test_output_check_finds_medical_advice(reply):
    assert safety.find_medical_advice(reply)


@pytest.mark.parametrize("reply", CLEAN)
def test_output_check_passes_admin_replies(reply):
    assert safety.find_medical_advice(reply) == []


@pytest.mark.parametrize("language", ["ar", "en", "fr"])
def test_every_fixed_template_passes_the_output_check(language):
    """Our own safety wording must never trip the medical-advice check (it would be blocked)."""
    for key, value in templates.T[language].items():
        assert safety.find_medical_advice(value) == [], key


def test_clinical_question_is_refused_and_routed_to_the_nurse(chat):
    turns, _, assistant = chat(["How many paracetamol can I give my son?"])
    assert turns[0].outcome == "routed_to_nurse"
    assert "nurse" in turns[0].reply
    assert assistant.desk.queue[-1]["kind"] == "nurse"


def test_model_flag_alone_routes_to_the_nurse(chat):
    llm = ScriptedLLM({"red_flag": {"emergency": False}, "understand": understanding(clinical_question=True)})
    turns, _, _ = chat(["My knee clicks when I walk, what could be the reason behind that?"], llm=llm)
    assert turns[0].outcome == "routed_to_nurse"


def test_output_check_blocks_a_model_reply_that_gives_medical_advice(chat):
    """Even if the understanding step misses a clinical question and the reply model gives advice, the
    output check swaps the reply for a safe template and puts it in the staff review queue."""
    llm = ScriptedLLM({
        "red_flag": {"emergency": False},
        "understand": understanding(intent="clinic_info", topic="preparation"),
        "reply": "Fast for 8 hours. You can also take 1 tablet of paracetamol every 6 hours if needed.",
    })
    turns, _, assistant = chat(["How do I prepare for my blood test?"], llm=llm)
    assert turns[0].outcome == "blocked_reply"
    assert "paracetamol" not in turns[0].reply
    assert any(e.startswith("output_blocked:medical_advice") for e in turns[0].guard_events)
    assert assistant.desk.queue[-1]["kind"] == "review"


def test_lab_status_never_contains_values_because_the_store_has_none(store):
    for order in store.lab_orders:
        assert set(order) == {"lab_order_id", "file_number", "test_name", "ordered_date", "status",
                              "expected_ready_date"}
