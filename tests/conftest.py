"""Shared test fixtures. Tests never use the network or a real model."""

from __future__ import annotations

import json
import socket

import pytest

from clinic_assistant.assistant import FrontDeskAssistant, Session
from clinic_assistant.clinic import ClinicStore
from clinic_assistant.llm import FakeLLM, LLMResult, Tracer
from clinic_assistant.staff import StaffDesk


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Fail loudly if any test opens a network connection; keep runtime files in tmp."""
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("CLINIC_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("TRACES_PATH", str(tmp_path / "traces.jsonl"))


@pytest.fixture
def store():
    return ClinicStore()


@pytest.fixture
def desk():
    return StaffDesk()


@pytest.fixture
def make_assistant(store, desk, tmp_path):
    """An assistant with the offline FakeLLM (default), the rules baseline (llm=None) or a scripted fake."""
    def factory(llm="fake"):
        if llm == "fake":
            llm = FakeLLM(Tracer(path=tmp_path / "traces.jsonl"))
        return FrontDeskAssistant(llm=llm, store=store, desk=desk)
    return factory


@pytest.fixture
def chat(make_assistant):
    """Send messages in one session and return the turns: chat(["hi", "..."]) -> [Turn, Turn]."""
    def run(messages, llm="fake", language="en"):
        assistant = make_assistant(llm)
        session = Session(language=language)
        return [assistant.handle(session, m) for m in messages], session, assistant
    return run


def identity(store, file_number: str) -> str:
    return f"My file number is {file_number} and my date of birth is {store.patients[file_number]['date_of_birth']}"


class ScriptedLLM:
    """A fake model that returns fixed text per purpose, e.g. to simulate a model that gives medical advice."""

    def __init__(self, replies: dict):
        self.replies = replies
        self.offline = True
        self.calls = []

    def complete(self, messages, role="cheap", purpose="", json_mode=False, max_tokens=500, temperature=0.0):
        self.calls.append(purpose)
        value = self.replies.get(purpose)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(messages)
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        return LLMResult(text=value or "", model="scripted")


def understanding(**overrides) -> dict:
    base = {"intent": "other", "topic": None, "file_number": None, "date_of_birth": None, "doctor_id": None,
            "specialty": None, "date": None, "time": None, "part_of_day": None, "choice": None, "insurer": None,
            "callback_team": "reception", "clinical_question": False, "other_person": False, "wants_human": False,
            "confidence": 0.9}
    return {**base, **overrides}
