"""The mock clinic system: doctors, free slots, appointments, identity check, lab-result status, insurers.

`ClinicStore` keeps appointments in memory (loaded from data/*.csv) so the evaluation can reset it before
every conversation. `clinic_api.py` puts the same store behind a small FastAPI app.

Privacy by design: the store has no medical values at all. Lab orders only say "ready" or "processing".
"""

from __future__ import annotations

import copy
import csv
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from .config import CLINIC_TODAY, DATA_DIR
from .text import normalise

SPECIALTY_NAMES = {
    "family_medicine": {"en": "Family medicine", "ar": "طب الأسرة", "fr": "Médecine générale"},
    "paediatrics": {"en": "Paediatrics", "ar": "طب الأطفال", "fr": "Pédiatrie"},
    "dermatology": {"en": "Dermatology", "ar": "الأمراض الجلدية", "fr": "Dermatologie"},
    "obstetrics_gynaecology": {"en": "Obstetrics and gynaecology", "ar": "النساء والولادة", "fr": "Gynécologie-obstétrique"},
    "ent": {"en": "ENT (ear, nose and throat)", "ar": "الأنف والأذن والحنجرة", "fr": "ORL"},
}
SPECIALTY_WORDS = {
    "family_medicine": ["family", "general practi", "gp", "généraliste", "generaliste", "médecine générale",
                        "طب الأسرة", "طب الاسرة", "طبيب عام", "دكتور عام", "طبيب أسرة"],
    "paediatrics": ["paediatric", "pediatric", "children's doctor", "child doctor", "pédiatr", "pediatr", "أطفال",
                    "اطفال", "atfal"],
    "dermatology": ["dermatolog", "skin doctor", "dermato", "جلدية", "الجلد", "جلد", "jildiya"],
    "obstetrics_gynaecology": ["gynae", "gyne", "gyna", "obstetric", "gynéco", "gyneco", "نسائية", "نساء",
                               "ولادة", "nisa"],
    "ent": ["ent", "ear nose", "ear, nose", "orl", "أنف", "انف", "أذن", "اذن", "حنجرة"],
}
INSURER_WORDS = {
    "Gulf Shield Health": ["gulf shield", "جلف شيلد", "غلف شيلد", "قلف شيلد"],
    "Oasis Care": ["oasis", "أواسيس", "اواسيس", "واحة"],
    "Falcon Cover": ["falcon", "فالكون", "الصقر"],
    "Palm Assure": ["palm assure", "palm", "بالم"],
    # renamed from "Sahara Mutual" after the evaluation: "صحارى" is now part of the clinic's Arabic name
    "Lotus Mutual Insurance (demo)": ["lotus", "لوتس"],
    "Coral Life": ["coral", "كورال"],
    "Horizon Plus": ["horizon", "هورايزن", "هورايزون"],
}


def part_of_day(time: str) -> str:
    hour = int(time[:2])
    return "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_schedule(text: str) -> dict[int, tuple[str, str]]:
    """'0=08:00-14:00;1=08:00-14:00' -> {0: ('08:00', '14:00'), 1: (...)}"""
    schedule = {}
    for part in text.split(";"):
        day, hours = part.split("=")
        start, end = hours.split("-")
        schedule[int(day)] = (start, end)
    return schedule


@lru_cache(maxsize=4)
def load_doctors(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    """{doctor_id: row} with the weekly schedule parsed. Doctors are public information."""
    doctors = {}
    for row in read_csv(data_dir / "doctors.csv"):
        row["schedule"] = parse_schedule(row["schedule"])
        doctors[row["doctor_id"]] = row
    return doctors


@dataclass
class ClinicStore:
    data_dir: Path = DATA_DIR
    today: date = CLINIC_TODAY
    doctors: dict = field(init=False)
    patients: dict = field(init=False)
    insurers: dict = field(init=False)
    lab_orders: list = field(init=False)
    appointments: list = field(init=False)

    def __post_init__(self) -> None:
        self.doctors = load_doctors(self.data_dir)
        self.patients = {row["file_number"]: row for row in read_csv(self.data_dir / "patients.csv")}
        self.insurers = {row["insurer"]: row for row in read_csv(self.data_dir / "insurers.csv")}
        self.lab_orders = read_csv(self.data_dir / "lab_orders.csv")
        self._original = read_csv(self.data_dir / "appointments.csv")
        self.reset()

    def reset(self) -> None:
        """Back to the generated appointments (used before every evaluation conversation)."""
        self.appointments = copy.deepcopy(self._original)
        self._next_id = 9001

    # ---- identity ----
    def verify_identity(self, file_number: str | None, date_of_birth: str | None) -> bool:
        patient = self.patients.get(file_number or "")
        return bool(patient and date_of_birth and patient["date_of_birth"] == date_of_birth)

    # ---- slots and appointments ----
    def _working_slots(self, doctor_id: str, day: date) -> list[str]:
        hours = self.doctors[doctor_id]["schedule"].get(day.weekday())
        if not hours:
            return []
        start_h, start_m = map(int, hours[0].split(":"))
        end_h, end_m = map(int, hours[1].split(":"))
        slots, minutes = [], start_h * 60 + start_m
        while minutes < end_h * 60 + end_m:
            slots.append(f"{minutes // 60:02d}:{minutes % 60:02d}")
            minutes += 30
        return slots

    def _taken(self, doctor_id: str, day: str) -> set[str]:
        return {a["time"] for a in self.appointments
                if a["doctor_id"] == doctor_id and a["date"] == day and a["status"] in ("booked", "held")}

    def is_free(self, doctor_id: str, day: str, time: str) -> bool:
        if doctor_id not in self.doctors:
            return False
        when = date.fromisoformat(day)
        if when <= self.today:
            return False
        return time in self._working_slots(doctor_id, when) and time not in self._taken(doctor_id, day)

    def find_slots(self, doctor_id: str | None = None, specialty: str | None = None, day: str | None = None,
                   part: str | None = None, limit: int = 3, days_ahead: int = 7) -> list[dict]:
        """Free slots for one doctor (or every doctor of a specialty), from `day` (default tomorrow) onwards."""
        doctor_ids = [doctor_id] if doctor_id in self.doctors else \
            [d for d, row in self.doctors.items() if row["specialty"] == specialty]
        start = date.fromisoformat(day) if day else self.today + timedelta(days=1)
        start = max(start, self.today + timedelta(days=1))
        found = []
        for offset in range(days_ahead + 1):
            when = start + timedelta(days=offset)
            for time in sorted({t for d in doctor_ids for t in self._working_slots(d, when)}):
                for d in doctor_ids:
                    if (part and part_of_day(time) != part) or not self.is_free(d, when.isoformat(), time):
                        continue
                    found.append(self.slot_facts(d, when.isoformat(), time))
                    if len(found) >= limit:
                        return found
        return found

    def slot_facts(self, doctor_id: str, day: str, time: str) -> dict:
        doctor = self.doctors[doctor_id]
        return {"doctor_id": doctor_id, "doctor": doctor["name"], "doctor_ar": doctor["name_ar"],
                "specialty": doctor["specialty"], "date": day,
                "weekday": date.fromisoformat(day).strftime("%A"), "time": time}

    def upcoming(self, file_number: str) -> list[dict]:
        return [a for a in self.appointments if a["file_number"] == file_number and a["status"] == "booked"
                and a["date"] > self.today.isoformat()]

    def book(self, file_number: str, doctor_id: str, day: str, time: str) -> dict:
        if file_number not in self.patients:
            return {"ok": False, "error": "unknown patient"}
        if not self.is_free(doctor_id, day, time):
            return {"ok": False, "error": "slot not free"}
        appointment = {"appointment_id": f"A-{self._next_id}", "file_number": file_number,
                       "doctor_id": doctor_id, "date": day, "time": time, "status": "booked"}
        self._next_id += 1
        self.appointments.append(appointment)
        return {"ok": True, **appointment}

    def reschedule(self, appointment_id: str, day: str, time: str) -> dict:
        appointment = self._find(appointment_id)
        if not appointment:
            return {"ok": False, "error": "unknown appointment"}
        if not self.is_free(appointment["doctor_id"], day, time):
            return {"ok": False, "error": "slot not free"}
        appointment.update(date=day, time=time)
        return {"ok": True, **appointment}

    def cancel(self, appointment_id: str) -> dict:
        appointment = self._find(appointment_id)
        if not appointment:
            return {"ok": False, "error": "unknown appointment"}
        appointment["status"] = "cancelled"
        return {"ok": True, **appointment}

    def _find(self, appointment_id: str) -> dict | None:
        return next((a for a in self.appointments if a["appointment_id"] == appointment_id
                     and a["status"] == "booked"), None)

    # ---- lab status (never values) and insurance ----
    def lab_status(self, file_number: str) -> list[dict]:
        return [{"test": o["test_name"], "status": o["status"], "expected_ready_date": o["expected_ready_date"]}
                for o in self.lab_orders if o["file_number"] == file_number]

    def check_insurance(self, name: str | None) -> dict:
        canonical = resolve_insurer(name or "")
        if not canonical:
            return {"insurer": name or "", "known": False, "accepted": None, "pre_approval_for": []}
        row = self.insurers[canonical]
        return {"insurer": canonical, "known": True, "accepted": row["accepted"] == "yes",
                "pre_approval_for": [p for p in row["pre_approval_for"].split(";") if p]}


# ---- Resolving names written by patients (or returned by the model) to IDs ----
def _contains(text: str, word: str) -> bool:
    """Match at the start of a word; short words (e.g. 'ent', 'gp') must match the whole word."""
    end = r"(?!\w)" if len(word) <= 4 else ""
    return re.search(rf"(?<!\w){re.escape(normalise(word))}{end}", text) is not None


TITLE = r"(?:dr\.?|doctor|docteur|doctora|dakhtar|دكتور|دكتورة|الدكتور|الدكتورة|د\.?)\s*"


def resolve_doctor(text: str, doctors: dict) -> str | None:
    """A doctor ID from 'Dr Mansour', 'Dr. Karim', 'د. ليلى', 'Benali', or an ID like 'D03'.

    A surname alone is enough; a first name only counts after a title ("Dr Karim"), because patients
    may share a first name with a doctor.
    """
    lowered = normalise(text)
    for doctor_id in doctors:
        if re.search(rf"\b{doctor_id.lower()}\b", lowered):
            return doctor_id
    for doctor_id, row in doctors.items():
        first, *rest = normalise(row["name"]).replace("dr.", "").split()
        first_ar, *rest_ar = normalise(row["name_ar"]).replace("د.", "").split()
        surnames = [" ".join(w for w in rest if w != "al"), " ".join(rest_ar)]
        if any(name and _contains(lowered, name) for name in surnames):
            return doctor_id
        if re.search(rf"{TITLE}(?:{re.escape(first)}|{re.escape(first_ar)})", lowered):
            return doctor_id
    return None


def resolve_specialty(text: str) -> str | None:
    lowered = normalise(text)
    for specialty, keywords in SPECIALTY_WORDS.items():
        if any(_contains(lowered, w) for w in keywords):
            return specialty
    return None


def resolve_insurer(text: str) -> str | None:
    lowered = normalise(text)
    for insurer, keywords in INSURER_WORDS.items():
        if normalise(insurer) == lowered.strip() or any(_contains(lowered, w) for w in keywords):
            return insurer
    return None
