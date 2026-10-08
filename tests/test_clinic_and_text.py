"""The mock clinic system, the FastAPI wrapper, text parsing, statistics and the evaluation pipeline."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from clinic_assistant.clinic_api import app
from clinic_assistant.text import detect_language, find_appointment_date, find_birth_date, find_file_number, find_times
from evals.scoring import fact_present, state_ok
from evals.stats import cohens_kappa, percentile, wilson_interval

TODAY = date(2026, 10, 8)


def test_slots_respect_rota_and_bookings(store):
    assert store.find_slots(doctor_id="D04", day="2026-10-12") and all(
        s["date"] != "2026-10-12" for s in store.find_slots(doctor_id="D04", day="2026-10-12"))  # not on Mondays
    taken = store.upcoming("NFC-10001")[0]
    assert not store.is_free(taken["doctor_id"], taken["date"], taken["time"])
    assert not store.is_free("D01", "2026-10-08", "09:00")  # today or earlier cannot be booked


def test_double_booking_is_impossible(store):
    slot = store.find_slots(doctor_id="D06")[0]
    assert store.book("NFC-10040", "D06", slot["date"], slot["time"])["ok"]
    assert not store.book("NFC-10041", "D06", slot["date"], slot["time"])["ok"]


def test_reset_restores_the_generated_appointments(store):
    before = [dict(a) for a in store.appointments]
    store.cancel(store.upcoming("NFC-10001")[0]["appointment_id"])
    store.reset()
    assert store.appointments == before


def test_api_identity_slots_and_booking():
    client = TestClient(app)
    assert client.get("/doctors").status_code == 200
    assert client.post("/identity/verify", json={"file_number": "NFC-10001", "date_of_birth": "1990-01-01"}
                       ).json()["verified"] is False
    slots = client.get("/slots", params={"doctor_id": "D03"}).json()
    assert slots
    first = slots[0]
    response = client.post("/appointments", json={"file_number": "NFC-10045", "date_of_birth": "wrong",
                                                  "doctor_id": "D03", "date": first["date"], "time": first["time"]})
    assert response.status_code == 403  # identity is checked by the API too


def test_api_lab_status_has_no_values():
    client = TestClient(app)
    response = client.get("/lab-status/NFC-10011", params={"date_of_birth": "wrong"})
    assert response.status_code == 403


@pytest.mark.parametrize("text, expected", [("مرحبا أبي موعد", "ar"), ("abi maw3ed bukra", "ar"),
                                            ("Bonjour, je voudrais un rendez-vous", "fr"),
                                            ("Hi, I need an appointment", "en")])
def test_language_detection(text, expected):
    assert detect_language(text) == expected


def test_dates_times_and_file_numbers_in_many_spellings():
    assert find_file_number("ملفي ١٠٠١٢") == "NFC-10012"
    assert find_file_number("dossier nfc 10012") == "NFC-10012"
    assert find_birth_date("born 14 March 1988", TODAY) == date(1988, 3, 14)
    assert find_birth_date("تاريخ الميلاد ١٤/٠٣/١٩٨٨", TODAY) == date(1988, 3, 14)
    assert find_appointment_date("le mardi 13 octobre", TODAY) == date(2026, 10, 13)
    assert find_appointment_date("next Tuesday", TODAY) == date(2026, 10, 13)
    assert find_appointment_date("bukra", TODAY) == date(2026, 10, 9)
    assert find_times("at 2:30 pm.") == ["14:30"]
    assert find_times("à 10h30") == ["10:30"]
    assert find_times("الساعة ١٠:٣٠") == ["10:30"]
    assert find_times("fast 8 hours") == []


def test_wilson_interval_and_kappa():
    low, high = wilson_interval(120, 120)
    assert 0.96 < low < 0.98 and high == 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert cohens_kappa([1, 2, 3, 1], [1, 2, 3, 1]) == 1.0
    assert cohens_kappa([1, 1, 2, 2], [1, 2, 1, 2]) == 0.0
    assert percentile([5, 1, 3, 2, 4], 50) == 3


def test_fact_check_accepts_other_spellings():
    assert fact_present("Votre rendez-vous est à 9h30.", "09:30")
    assert fact_present("الساعة ٠٩:٣٠ يوم ١٣", "13")
    assert not fact_present("Room 113", "13")


def test_state_check_detects_a_wrong_booking(store):
    original = [dict(a) for a in store.appointments]
    slot = store.find_slots(doctor_id="D06")[0]
    store.book("NFC-10040", "D06", slot["date"], slot["time"])
    expected = {"type": "booked", "file_number": "NFC-10040", "doctor_id": "D06", "date": slot["date"],
                "time": slot["time"]}
    assert state_ok(expected, original, store.appointments)
    assert not state_ok({**expected, "time": "23:00"}, original, store.appointments)
    assert not state_ok({"type": "unchanged"}, original, store.appointments)


def test_evaluation_sets_have_the_planned_sizes():
    from evals.run import load_set
    sizes = {name: len(load_set(name)) for name in ("admin", "red_flags", "medical_bait", "privacy")}
    assert sizes == {"admin": 300, "red_flags": 120, "medical_bait": 90, "privacy": 30}
    for name in sizes:
        languages = [c["language"] for c in load_set(name)]
        assert languages.count("ar") == languages.count("en") == languages.count("fr")


def test_dry_run_pipeline_end_to_end(tmp_path, monkeypatch):
    """The whole evaluation runs with the fake model and writes its files (dry-run outputs, not results)."""
    import evals.run as run

    real_sets = {name: run.load_set(name)[:3] for name in ("admin", "red_flags", "medical_bait", "privacy")}
    monkeypatch.setattr(run, "EVALS_DIR", tmp_path)
    (tmp_path / "sets").mkdir()
    for name, rows in real_sets.items():
        (tmp_path / "sets" / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["run", "--system", "assistant", "--dry-run", "--workers", "1", "--judge"])
    run.main()
    written = list((tmp_path / "dry_run").glob("assistant_fake_*_summary.csv"))
    assert written and "red_flags" in written[0].read_text(encoding="utf-8")
