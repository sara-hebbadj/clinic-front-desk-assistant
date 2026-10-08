"""Keyword "understanding" with no model: the rules-only baseline, the offline demo and the test stand-in.

`understand()` returns the same JSON fields as the model's understanding step, so the assistant pipeline,
the tools and the guards are identical; only the brain changes. This makes the baseline comparison fair.
"""

from __future__ import annotations

import re

from . import safety
from .clinic import load_doctors, resolve_doctor, resolve_insurer, resolve_specialty
from .config import CLINIC_TODAY
from .text import find_appointment_date, find_birth_date, find_file_number, find_times, normalise

# Order matters: the first intent whose words appear wins (cancel before reschedule before book).
INTENT_WORDS = [
    ("human", ["staff", "human", "real person", "a person", "talk to someone", "speak to someone", "receptionist",
               "موظف", "انسان", "شخص حقيقي", "une personne", "un humain", "parler a quelqu'un", "conseiller",
               "mwazaf", "muwazaf"]),
    ("callback", ["call me back", "callback", "call-back", "call back", "rappeler", "me rappelle", "un rappel",
                  "اتصلوا علي", "اتصلوا فيني", "يتصل علي", "تتصلون علي", "كلموني", "ittislo 3alay", "kalmoni"]),
    ("cancel", ["cancel", "annul", "الغاء", "الغي", "اكنسل", "كنسل", "الغوا", "cancel", "elgha", "algi"]),
    ("reschedule", ["reschedule", "move my appointment", "change my appointment", "change the time", "postpone",
                    "move it to", "different time", "deplacer", "decaler", "changer mon rendez", "changer le rendez",
                    "reporter", "تغيير الموعد", "تغيير موعد", "اغير الموعد", "اغير موعد", "غير موعدي", "تاجيل",
                    "اجل الموعد", "اقدم الموعد", "انقل الموعد", "انقل موعد", "aghayer", "a8ayer", "agayer", "ta3deel"]),
    ("my_appointment", ["when is my appointment", "when is my next appointment", "my next appointment",
                        "is my appointment confirmed", "prochain rendez-vous", "quand est mon rendez-vous",
                        "متى موعدي", "موعدي القادم", "موعدي متى", "mata maw3edi"]),
    ("lab_status", ["result", "resultat", "نتيجة", "نتيجه", "نتائج", "التحليل جاهز", "natija", "nateeja"]),
    ("insurance_check", ["insurance", "insurer", "assurance", "assureur", "تامين", "ta2meen", "tameen"]),
    ("book", ["book", "appointment", "rendez-vous", "rendez vous", "rdv", "reserver", "consultation", "حجز", "احجز",
              "موعد", "abi maw3ed", "maw3ed", "maw3id", "a7jez", "ahjez"]),
    ("availability", ["available", "availability", "free slot", "free time", "disponible", "disponibilit", "creneau",
                      "متاح", "متاحة", "متوفر", "فاضي", "يداوم", "تداوم", "mawjood", "fadi"]),
]
TOPIC_WORDS = [
    ("preapproval_documents", ["pre-approval", "preapproval", "pre approval", "prior approval", "accord prealable",
                               "موافقة مسبقة", "الموافقة المسبقة", "muwafaqa"]),
    ("insurance_list", ["which insurance", "what insurance", "insurances do you", "quelles assurances",
                        "quelle assurance", "شركات التامين", "اي تامين", "وش التامين", "التامينات"]),
    ("preparation", ["fast", "fasting", "prepare", "preparation", "before the test", "before my blood test",
                     "before the scan", "a jeun", "jeun", "preparer", "preparation", "صيام", "صايم", "اصوم",
                     "قبل التحليل", "قبل الاشعة", "asoom", "sayem", "9ayem"]),
    ("what_to_bring", ["bring", "documents do i need", "what do i need for", "apporter", "amener", "احضر معي",
                       "اجيب معي", "اجيب وياي", "احضر معاي", "شو احضر", "ajeeb", "ajib"]),
    ("billing", ["bill", "invoice", "payment", "pay ", "pay?", "co-pay", "copay", "apple pay", "refund", "facture",
                 "paiement", "payer", "rembourse", "فاتورة", "الفاتورة", "الدفع", "ادفع", "استرجاع", "fatora"]),
    ("location", ["where", "address", "location", "directions", "parking", "how do i get", "adresse", "ou etes",
                  "ou se trouve", "itineraire", "parking", "acces", "وين", "عنوان", "العنوان", "موقع", "مواقف",
                  "wain", "wein", "lokeshen"]),
    ("hours", ["open", "opening", "hours", "close", "closing", "timing", "horaire", "ouvert", "ferme", "دوام",
               "مواعيد العمل", "ساعات العمل", "تفتح", "تفتحون", "تسكر", "تسكرون", "مفتوح", "dawam", "timings"]),
    ("lab_results", ["how long do results", "how long for results", "combien de temps pour les resultats",
                     "متى تطلع النتائج"]),
    ("booking_policy", ["cancellation policy", "late", "retard", "متاخر", "تاخير"]),
]
CHOICE_WORDS = {
    1: ["first", "1st", "premier", "premiere", "الاول", "الاولى", "اول واحد", "awal", "awwal"],
    2: ["second", "2nd", "deuxieme", "second", "الثاني", "الثانية", "thani"],
    3: ["third", "3rd", "troisieme", "الثالث", "الثالثة", "thalith"],
}
PART_WORDS = {
    "morning": ["morning", "matin", "صباح", "الصبح", "الصباح", "sabah", "9aba7", "subh"],
    "afternoon": ["afternoon", "apres-midi", "apres midi", "العصر", "بعد الظهر", "الظهر", "3asr", "asr"],
    "evening": ["evening", "soir", "مساء", "المسا", "بالليل", "masa"],
}
GREETINGS = ["hi", "hello", "hey", "salam", "مرحبا", "السلام عليكم", "هلا", "bonjour", "bonsoir", "salut"]


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(normalise(w))}", text) for w in words)


def _choice(text: str) -> int | None:
    for number, choice_words in CHOICE_WORDS.items():
        if _has(text, choice_words):
            return number
    return None


def understand(message: str, context: dict | None = None) -> dict:
    """Return the understanding fields for one message (same schema as the model's JSON)."""
    context = context or {}
    text = normalise(message).replace("’", "'")
    intent = next((name for name, intent_words in INTENT_WORDS if _has(text, intent_words)), None)
    topic = next((name for name, topic_words in TOPIC_WORDS if _has(text, topic_words)), None)
    insurer = resolve_insurer(message)
    if topic in ("preapproval_documents", "insurance_list") and not insurer:
        intent = "clinic_info"
    elif topic and intent in (None, "book", "insurance_check", "availability") and not (intent == "insurance_check" and insurer):
        # "what should I bring to my appointment?" is a question, not a booking
        intent = "clinic_info"
    if intent == "lab_status" and topic == "lab_results":
        intent = "clinic_info"
    if intent == "insurance_check" and not insurer:
        intent, topic = "clinic_info", "insurance_list"
    if intent is None and insurer:
        intent = "insurance_check"

    fields = {
        "file_number": find_file_number(message),
        "date_of_birth": (d.isoformat() if (d := find_birth_date(message, CLINIC_TODAY)) else None),
        "doctor_id": None, "specialty": None,
        "date": (d.isoformat() if (d := find_appointment_date(message, CLINIC_TODAY)) else None),
        "time": next(iter(find_times(message)), None),
        "part_of_day": next((p for p, part_words in PART_WORDS.items() if _has(text, part_words)), None),
        "choice": _choice(text) if context.get("offered_slots") else None,
    }
    fields["doctor_id"] = resolve_doctor(message, load_doctors())
    fields["specialty"] = resolve_specialty(message) if not fields["doctor_id"] else None

    has_details = any(fields[k] for k in ("file_number", "date_of_birth", "date", "time", "choice"))
    yes_words = ["yes", "ok", "okay", "sure", "oui", "d'accord", "نعم", "اي", "ايه", "تمام", "zain", "tamam"]
    if intent is None and (has_details or (context.get("offered_slots") and _has(text, yes_words))):
        intent = "provide_details"
    if intent is None and _has(text, GREETINGS) and len(text.split()) <= 4:
        intent = "greeting"
    team = "billing" if topic == "billing" else "reception"
    return {
        "intent": intent or "other",
        "topic": topic if intent == "clinic_info" else None,
        **fields,
        "insurer": insurer,
        "callback_team": team,
        "clinical_question": safety.clinical_question(message),
        "other_person": safety.asks_about_other_person(message),
        "wants_human": intent == "human",
        "confidence": 0.9 if intent not in (None, "provide_details") else (0.7 if intent else 0.3),
    }
