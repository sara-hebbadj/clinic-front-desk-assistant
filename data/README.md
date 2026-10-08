# Data

Everything in this folder is **synthetic** and was written or generated for this portfolio project. There are
no real patients, no real health records and no medical question-and-answer datasets.

| File | What it is | How it was made |
|---|---|---|
| `doctors.csv` | 6 fictional doctors, specialty, languages, weekly rota | Hand-written in `generate.py` |
| `patients.csv` | 60 fictional patients: file number `NFC-1xxxx`, name, date of birth, phone `+971 50 000 xxxx`, `@example.com` email, preferred language, insurer | `generate.py`, seed 42 |
| `appointments.csv` | 36 upcoming appointments (one each for patients NFC-10001 to NFC-10036) and about 30% of other slots "held" (busy, nobody named), 9 to 31 October 2026 | `generate.py`, seed 42 |
| `lab_orders.csv` | 30 lab orders with status `ready` or `processing` only. **No result values exist anywhere**, so the assistant cannot leak or interpret one | `generate.py`, seed 42 |
| `insurers.csv` | 7 fictional insurers (5 accepted, 2 not) and which services need pre-approval | Hand-written in `generate.py` |
| `clinic_docs_en.md`, `clinic_docs_ar.md`, `clinic_docs_fr.md` | The clinic's own front-desk information in 11 sections (hours, location, what to bring, preparation, insurance, pre-approval checklist, billing, booking policy, lab results, contact, privacy) | Hand-written; the Arabic and French versions are machine-written translations that still need a native speaker's review |

Regenerate the CSV files with `python data/generate.py` (seed 42; the "today" of the data is Thursday
8 October 2026, see `config.CLINIC_TODAY`).

- The clinic "Sahara Demo Family Clinic" (Arabic: عيادة صحارى التجريبية للعائلة; French: Clinique familiale de démonstration Sahara), its address (Unit 4, Building 7, 21A Street, Al Wasl, Dubai), its phone number
  (+971 4 000 0000), the doctors and the insurers are invented. Any resemblance to a real clinic, person or
  insurer is not intended. "Demo" is part of the name on purpose. The insurer "Lotus Mutual Insurance (demo)" (Arabic: لوتس للتأمين التبادلي، تجريبي;
  French: Assurance mutuelle Lotus, démo) is also fictional.
- The clinic and one insurer were renamed after the 8 October 2026 evaluation; the
  saved runs in `evals/results/` and the transcripts in `evals/hand_grading_sheet.csv` show the earlier name.
- The preparation instructions (for example "do not eat for 8 hours before a fasting blood test") are typical
  front-desk wording written for the demo. A real clinic would use its own clinically approved text.
- The evaluation sets in `evals/sets/` are also synthetic, written by a coding agent (see `evals/make_sets.py`).

Licence: MIT, like the code.
