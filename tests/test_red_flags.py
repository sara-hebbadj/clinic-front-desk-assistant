"""Safety rule 2: red flags win. Either the pattern list or the model screen is enough."""

from __future__ import annotations

import pytest

from clinic_assistant import safety
from clinic_assistant.config import AMBULANCE

from .conftest import ScriptedLLM, understanding

EMERGENCIES = [
    ("My father has crushing chest pain right now", "chest_pain"),
    ("I can't breathe properly", "breathing"),
    ("My dad's face is drooping and his speech is slurred", "stroke"),
    ("I cut my hand and the bleeding won't stop", "heavy_bleeding"),
    ("I don't want to live anymore", "self_harm"),
    ("Je suis enceinte et j'ai des saignements", "pregnancy_bleeding"),
    ("بنتي حرارتها عالية ونعسانة وايد", "child_fever_drowsy"),
    ("أبوي يعوره صدره", "chest_pain"),
    ("ما أقدر أتنفس", "breathing"),
    ("ana 7amel w fi nazeef", "pregnancy_bleeding"),
    ("Mon père a une douleur à la poitrine", "chest_pain"),
    ("ابني جاته تشنجات", "unresponsive_or_seizure"),
    ("عندي نزيف وأنا حامل؟", "pregnancy_bleeding"),  # regression: "؟" right after a short Arabic word
]
NOT_EMERGENCIES = [
    "I am pregnant and need to book a blood test",  # "blood" alone is not bleeding
    "My son has a fever, can I book with Dr Mansour tomorrow?",  # fever without drowsiness
    "The patient portal is not responding",
    "Do you give the polio vaccine?",
    "What are your opening hours on Saturday?",
    "أبي موعد عند دكتور جلدية",
]


@pytest.mark.parametrize("message, category", EMERGENCIES)
def test_pattern_list_catches_emergencies_in_three_languages(message, category):
    assert safety.pattern_red_flag(message) == category


@pytest.mark.parametrize("message", NOT_EMERGENCIES)
def test_pattern_list_ignores_ordinary_admin_messages(message):
    assert safety.pattern_red_flag(message) is None


def test_emergency_stops_the_admin_flow_shows_998_and_alerts_staff(chat, store):
    turns, session, assistant = chat(["I need to cancel my appointment, my husband has chest pain right now"])
    turn = turns[0]
    assert turn.outcome == "emergency"
    assert AMBULANCE in turn.reply and "998" in turn.reply
    assert turn.tool_calls == []  # nothing was cancelled
    assert len(assistant.desk.alerts) == 1 and assistant.desk.alerts[0]["category"] == "chest_pain"
    assert session.emergency


def test_model_screen_alone_is_enough_when_patterns_miss(chat):
    """Recall-first: 'either fires'. A message with no pattern keyword is escalated if the model says so."""
    message = "My uncle suddenly can't get his words out and his smile looks lopsided"
    assert safety.pattern_red_flag(message) is None
    llm = ScriptedLLM({"red_flag": {"emergency": True, "category": "stroke"},
                       "understand": understanding(intent="other")})
    turns, _, assistant = chat([message], llm=llm)
    assert turns[0].outcome == "emergency"
    assert turns[0].red_flag["sources"] == ["llm"]
    assert assistant.desk.alerts[0]["sources"] == ["llm"]


def test_pattern_wins_even_if_the_model_says_no(chat):
    llm = ScriptedLLM({"red_flag": {"emergency": False, "category": "none"}, "understand": understanding()})
    turns, _, _ = chat(["My baby has a fever and is very drowsy"], llm=llm)
    assert turns[0].outcome == "emergency"
    assert turns[0].red_flag["sources"] == ["pattern"]
    assert "red_flag" not in llm.calls  # the instant pattern check fired: no model call was needed


def test_model_outage_does_not_stop_pattern_red_flags(chat):
    llm = ScriptedLLM({"red_flag": RuntimeError("down"), "understand": RuntimeError("down")})
    turns, _, _ = chat(["I can't breathe"], llm=llm)
    assert turns[0].outcome == "emergency"


def test_unscreened_message_still_shows_998_and_goes_to_staff(chat):
    """Found in the red-flag ablation run: the model screen sometimes returned no valid JSON (its hidden
    reasoning used all 300 output tokens). Now it is tried twice, and if both fail the reply carries the 998
    line and the chat goes to the staff queue instead of passing silently."""
    llm = ScriptedLLM({"red_flag": "sorry, I was cut off", "understand": understanding(intent="clinic_info",
                                                                                           topic="hours")})
    turns, _, assistant = chat(["My left side went numb suddenly and I can't see well"], llm=llm)
    assert llm.calls.count("red_flag") == 2
    assert "998" in turns[0].reply and turns[0].outcome == "info:hours"
    assert "red_flag_screen_failed" in turns[0].guard_events
    assert assistant.desk.queue[-1]["kind"] == "unscreened"


def test_after_an_emergency_every_message_repeats_the_urgent_advice(chat):
    turns, _, assistant = chat(["I'm bleeding heavily", "ok can I still book for next week?"])
    assert turns[1].outcome == "emergency_followup"
    assert "998" in turns[1].reply
    assert assistant.desk.queue[-1]["kind"] == "emergency_followup"


def test_self_harm_gets_its_own_caring_template_with_998_and_999(chat):
    turns, _, _ = chat(["I want to end my life"])
    assert "998" in turns[0].reply and "999" in turns[0].reply


def test_urgent_advice_comes_before_the_ai_notice(chat):
    turns, _, _ = chat(["chest pain right now"])
    assert turns[0].reply.index("998") < turns[0].reply.index("AI assistant")
