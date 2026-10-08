"""Generate the synthetic data for the fictional "Sahara Demo Family Clinic" (seed 42).

Run:  python data/generate.py            (writes the CSV files next to this script)
      python data/generate.py --out DIR

Everything is invented: patients, doctors, insurers and appointments. Emails use @example.com and
phones +971 50 000 xxxx. There are NO medical values anywhere: lab orders only say whether a result is
ready, never what it is (the assistant cannot leak what it does not have).
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
TODAY = date(2026, 10, 8)  # must match config.CLINIC_TODAY
LAST_DAY = date(2026, 10, 31)
SLOT_MINUTES = 30

# Fictional doctors. weekday numbers: 0 = Monday ... 6 = Sunday (closed).
DOCTORS = [
    {"doctor_id": "D01", "name": "Dr. Amal Haddad", "name_ar": "د. أمل حداد", "specialty": "family_medicine",
     "languages": "ar;en", "schedule": {0: ("08:00", "14:00"), 1: ("08:00", "14:00"), 2: ("08:00", "14:00"), 3: ("08:00", "14:00"), 4: ("08:00", "12:00")}},
    {"doctor_id": "D02", "name": "Dr. Omar Al Suwaidi", "name_ar": "د. عمر السويدي", "specialty": "family_medicine",
     "languages": "ar;en", "schedule": {0: ("14:00", "20:00"), 1: ("14:00", "20:00"), 2: ("14:00", "20:00"), 3: ("14:00", "20:00"), 5: ("09:00", "13:00")}},
    {"doctor_id": "D03", "name": "Dr. Karim Mansour", "name_ar": "د. كريم منصور", "specialty": "paediatrics",
     "languages": "ar;en;fr", "schedule": {0: ("09:00", "17:00"), 1: ("09:00", "17:00"), 3: ("09:00", "17:00"), 5: ("09:00", "13:00")}},
    {"doctor_id": "D04", "name": "Dr. Leila Benali", "name_ar": "د. ليلى بن علي", "specialty": "dermatology",
     "languages": "fr;ar;en", "schedule": {1: ("10:00", "18:00"), 2: ("10:00", "18:00"), 4: ("08:00", "12:00")}},
    {"doctor_id": "D05", "name": "Dr. Sophie Martin", "name_ar": "د. صوفي مارتان", "specialty": "obstetrics_gynaecology",
     "languages": "fr;en", "schedule": {0: ("08:00", "15:00"), 2: ("08:00", "15:00"), 3: ("08:00", "15:00")}},
    {"doctor_id": "D06", "name": "Dr. Priya Nair", "name_ar": "د. بريا ناير", "specialty": "ent",
     "languages": "en", "schedule": {1: ("12:00", "20:00"), 3: ("12:00", "20:00"), 5: ("13:00", "17:00")}},
]

FIRST_NAMES = ["Fatima", "Mariam", "Aisha", "Noura", "Hessa", "Layla", "Yasmin", "Salma", "Rania", "Huda",
               "Ahmed", "Khalid", "Saeed", "Rashid", "Yousef", "Omar", "Hamad", "Tariq", "Faisal", "Ali",
               "Camille", "Chloé", "Inès", "Amélie", "Léa", "Julien", "Mehdi", "Nicolas", "Karim", "Antoine",
               "Emily", "Sarah", "Hannah", "Olivia", "Grace", "James", "Daniel", "Ryan", "Ravi", "Arjun"]
LAST_NAMES = ["Al Mansoori", "Al Hashimi", "Al Ketbi", "Al Nuaimi", "Haddad", "Khoury", "Saleh", "Rahman",
              "El Idrissi", "Benjelloun", "Bouzid", "Lefèvre", "Moreau", "Dubois", "Girard", "Mercier",
              "Taylor", "Walker", "Hughes", "Bennett", "Fernandes", "Menon", "Iyer", "Qureshi"]
INSURERS = [  # fictional insurers
    {"insurer": "Gulf Shield Health", "accepted": "yes", "pre_approval_for": "ultrasound;dermatology procedures;specialist referral"},
    {"insurer": "Oasis Care", "accepted": "yes", "pre_approval_for": "ultrasound;specialist referral"},
    {"insurer": "Falcon Cover", "accepted": "yes", "pre_approval_for": "ultrasound"},
    {"insurer": "Palm Assure", "accepted": "yes", "pre_approval_for": "ultrasound;dermatology procedures"},
    {"insurer": "Lotus Mutual Insurance (demo)", "accepted": "yes", "pre_approval_for": "specialist referral"},
    {"insurer": "Coral Life", "accepted": "no", "pre_approval_for": ""},
    {"insurer": "Horizon Plus", "accepted": "no", "pre_approval_for": ""},
]
LAB_TESTS = ["Full blood count", "HbA1c", "Lipid profile", "Vitamin D", "Thyroid (TSH)", "Ferritin"]


def time_slots(start: str, end: str) -> list[str]:
    h, m = map(int, start.split(":"))
    end_h, end_m = map(int, end.split(":"))
    slots = []
    while (h, m) < (end_h, end_m):
        slots.append(f"{h:02d}:{m:02d}")
        m += SLOT_MINUTES
        h, m = h + m // 60, m % 60
    return slots


def all_slots() -> list[tuple[str, str, str]]:
    """(doctor_id, date, time) for every working slot from tomorrow to LAST_DAY."""
    slots = []
    day = TODAY + timedelta(days=1)
    while day <= LAST_DAY:
        for doctor in DOCTORS:
            hours = doctor["schedule"].get(day.weekday())
            if hours:
                slots += [(doctor["doctor_id"], day.isoformat(), t) for t in time_slots(*hours)]
        day += timedelta(days=1)
    return slots


def make_patients(rng: random.Random, count: int = 60) -> list[dict]:
    patients, used = [], set()
    for number in range(1, count + 1):
        while True:
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            if (first, last) not in used:
                used.add((first, last))
                break
        born = date(1950, 1, 1) + timedelta(days=rng.randint(0, 365 * 70))
        email_name = f"{first}.{last}".lower().replace(" ", "").replace("é", "e").replace("è", "e")
        patients.append({
            "file_number": f"NFC-{10000 + number}",
            "full_name": f"{first} {last}",
            "date_of_birth": born.isoformat(),
            "phone": f"+971 50 000 {1000 + number * 37 % 9000:04d}",
            "email": f"{email_name}@example.com",
            "language": rng.choice(["ar", "ar", "en", "en", "fr"]),
            "insurer": rng.choice([i["insurer"] for i in INSURERS[:5]] + ["self-pay"]),
        })
    return patients


def make_appointments(rng: random.Random, patients: list[dict]) -> list[dict]:
    """The first 36 patients have one upcoming appointment each; about 30% of other slots are held."""
    slots = all_slots()
    rng.shuffle(slots)
    appointments = []
    for index, patient in enumerate(patients[:36]):
        doctor_id, day, time = slots[index]
        appointments.append({"appointment_id": f"A-{5001 + index}", "file_number": patient["file_number"],
                             "doctor_id": doctor_id, "date": day, "time": time, "status": "booked"})
    for index, (doctor_id, day, time) in enumerate(slots[36:]):
        if rng.random() < 0.30:  # held by other patients or walk-ins: busy, but nobody is named
            appointments.append({"appointment_id": f"H-{7001 + index}", "file_number": "",
                                 "doctor_id": doctor_id, "date": day, "time": time, "status": "held"})
    return sorted(appointments, key=lambda a: (a["date"], a["time"], a["doctor_id"]))


def make_lab_orders(rng: random.Random, patients: list[dict]) -> list[dict]:
    orders = []
    for index, patient in enumerate(patients[10:40]):
        ordered = TODAY - timedelta(days=rng.randint(0, 6))
        ready = rng.random() < 0.6
        orders.append({"lab_order_id": f"L-{3001 + index}", "file_number": patient["file_number"],
                       "test_name": rng.choice(LAB_TESTS), "ordered_date": ordered.isoformat(),
                       "status": "ready" if ready else "processing",
                       "expected_ready_date": (ordered + timedelta(days=3)).isoformat()})
    return orders


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    rng = random.Random(SEED)
    patients = make_patients(rng)
    doctors = [{**{k: v for k, v in d.items() if k != "schedule"},
                "schedule": ";".join(f"{day}={start}-{end}" for day, (start, end) in d["schedule"].items())}
               for d in DOCTORS]
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "doctors.csv", doctors)
    write_csv(args.out / "patients.csv", patients)
    write_csv(args.out / "appointments.csv", make_appointments(rng, patients))
    write_csv(args.out / "lab_orders.csv", make_lab_orders(rng, patients))
    write_csv(args.out / "insurers.csv", INSURERS)
    print(f"Wrote 5 CSV files to {args.out}")


if __name__ == "__main__":
    main()
