"""Settings, file paths and clinic constants in one place.

Keys are read from `Portfolio Projects/.env` (two folders above this repo) when it exists,
otherwise from normal environment variables. Keys are never printed.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
EVALS_DIR = REPO_ROOT / "evals"

# Shared .env first, then a local one. override=False: real environment variables (e.g. Space secrets) win.
load_dotenv(REPO_ROOT.parent.parent / ".env", override=False)
load_dotenv(REPO_ROOT / ".env", override=False)

CLINIC_NAME = "Sahara Demo Family Clinic (fictional)"
CLINIC_PHONE = "+971 4 000 0000"  # fake number
# The synthetic data's "today", so slots and "next Tuesday" are stable in tests and evaluations.
CLINIC_TODAY = date(2026, 10, 8)  # a Thursday

# UAE emergency numbers, checked on u.ae ("Handling emergencies") on 8 October 2026.
AMBULANCE = "998"
POLICE = "999"

MAX_IDENTITY_ATTEMPTS = 3  # failed file-number/date-of-birth checks before a person takes over
LOW_CONFIDENCE = 0.5  # intent confidence below this -> ask again; twice in a row -> a person takes over


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def model_id(role: str) -> str:
    """role is 'main', 'cheap' or 'judge' -> the model ID from MODEL_MAIN / MODEL_CHEAP / MODEL_JUDGE."""
    return env(f"MODEL_{role.upper()}")


def runtime_dir() -> Path:
    """Folder for mutable demo state (alerts, handover queue, audit log). Not committed."""
    path = Path(env("CLINIC_RUNTIME_DIR") or (REPO_ROOT / "runtime"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def demo_message_limit() -> int:
    return int(env("DEMO_MESSAGE_LIMIT", "20"))
