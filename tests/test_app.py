"""The Gradio app starts without a key (demo mode) and its handlers work offline."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load_app(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    if "app" in sys.modules:
        del sys.modules["app"]
    return importlib.import_module("app")


def test_app_runs_in_demo_mode_without_a_key(monkeypatch):
    app = load_app(monkeypatch)
    assert app.OFFLINE
    assert "Demo mode" in app.BANNER and "998" in app.BANNER


def test_chat_and_staff_console_handlers(monkeypatch):
    app = load_app(monkeypatch)
    _, history, session, count, trace = app.send("My father has crushing chest pain", [], None, 0)
    assert count == 1 and "998" in history[-1]["content"]
    alerts, queue, audit = app.refresh()
    assert alerts and alerts[0][2] == "chest_pain"
    assert audit and "crushing" not in str(audit)


def test_message_limit(monkeypatch):
    app = load_app(monkeypatch)
    _, history, _, count, _ = app.send("hello", [], None, app.LIMIT)
    assert count == app.LIMIT and "limit" in history[-1]["content"]
