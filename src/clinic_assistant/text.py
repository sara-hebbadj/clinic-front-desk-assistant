"""Small text helpers: digits, language detection, file numbers, dates and times.

Used by the keyword baseline, by the code that double-checks the model's JSON, and by the scoring.
Patients write dates and times in many ways ("14/10", "14 octobre", "١٤ أكتوبر", "10h30", "3pm"),
so everything is normalised before it is compared.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
FILE_RE = re.compile(r"(?<![a-z0-9])nfc[\s\-_]?(\d{5})(?!\d)", re.IGNORECASE)
FILE_WORDS_RE = re.compile(r"(?:file|dossier|ملف|ملفي|mlf|malaf)\D{0,15}(1\d{4})(?!\d)", re.IGNORECASE)

# Latin-script Arabic ("Arabizi"): digits used as letters, and common Gulf words.
ARABIZI_WORDS = {"abi", "aby", "abgha", "abga", "mumkin", "mmkn", "momken", "shlon", "shlonik", "wayed", "yalla",
                 "inshallah", "ana", "3indi", "3ndi", "3ndy", "maw3id", "maw3ed", "mow3ed", "mawid", "bukra", "bachir",
                 "baachir", "al7een", "alhin", "el7en", "wain", "wein", "shukran", "doctora", "dakhtar", "ams", "elyom",
                 "lyom", "alyoum", "ba3d", "ma3", "wala", "3shan", "3ashan", "abi7", "agdar", "a9dar", "galbi", "rasi",
                 "bntii", "bnti", "wildi", "waldi", "akhoy", "ukhti", "ukhty", "zawjti", "zoji", "7ag", "7ق", "ta3ban",
                 "mawa3eed", "el3iyada", "3iyada", "alkhamis", "aljum3a", "alsabt", "il", "hal", "kam", "sa3a", "sa3ah"}
FRENCH_WORDS = {"je", "vous", "bonjour", "bonsoir", "rendez-vous", "rdv", "mon", "ma", "mes", "est-ce", "pour", "avec",
                "le", "la", "les", "une", "un", "des", "du", "pouvez", "puis-je", "voudrais", "merci", "quels", "quelle",
                "quand", "où", "c'est", "j'ai", "n'est", "est", "suis", "pas", "mais", "aussi", "demain", "fille", "fils",
                "mari", "femme", "médecin", "docteur", "dossier", "né", "née", "naissance", "s'il", "plaît", "et"}
ENGLISH_WORDS = {"the", "i", "my", "is", "you", "to", "for", "with", "can", "please", "what", "when", "where", "do",
                 "have", "an", "a", "and", "appointment", "hi", "hello", "thanks", "need", "want", "would", "like",
                 "it", "me", "of", "on", "at", "are", "your", "doctor", "file", "born", "birth"}

MONTHS = {  # English, French and the month names used in the Gulf (Arabic)
    1: ["january", "jan", "janvier", "janv", "يناير"], 2: ["february", "feb", "février", "fevrier", "fév", "فبراير"],
    3: ["march", "mar", "mars", "مارس"], 4: ["april", "apr", "avril", "أبريل", "ابريل", "إبريل"],
    5: ["may", "mai", "مايو"], 6: ["june", "jun", "juin", "يونيو"], 7: ["july", "jul", "juillet", "يوليو"],
    8: ["august", "aug", "août", "aout", "أغسطس", "اغسطس"], 9: ["september", "sep", "sept", "septembre", "سبتمبر"],
    10: ["october", "oct", "octobre", "أكتوبر", "اكتوبر"], 11: ["november", "nov", "novembre", "نوفمبر"],
    12: ["december", "dec", "décembre", "decembre", "ديسمبر"],
}
WEEKDAYS = {
    0: ["monday", "lundi", "الاثنين", "الإثنين", "اثنين", "ithnain", "al-ithnayn", "alithnain"],
    1: ["tuesday", "mardi", "الثلاثاء", "ثلاثاء", "thulatha", "althulatha", "el thalath"],
    2: ["wednesday", "mercredi", "الأربعاء", "الاربعاء", "اربعاء", "arba3a", "alarba3a", "arbi3a"],
    3: ["thursday", "jeudi", "الخميس", "خميس", "khamis", "alkhamis"],
    4: ["friday", "vendredi", "الجمعة", "جمعة", "jum3a", "aljum3a"],
    5: ["saturday", "samedi", "السبت", "سبت", "sabt", "alsabt"],
    6: ["sunday", "dimanche", "الأحد", "الاحد", "ahad", "al7ad"],
}
TOMORROW_WORDS = ["tomorrow", "demain", "غدا", "غداً", "بكرة", "باجر", "bukra", "bachir", "baachir"]
MONTH_WORD_TO_NUMBER = {word: number for number, words in MONTHS.items() for word in words}
MONTH_ALTERNATION = "|".join(sorted(map(re.escape, MONTH_WORD_TO_NUMBER), key=len, reverse=True))
DAY_MONTH_RE = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th|er)?\s+(?:of\s+)?({MONTH_ALTERNATION})\.?(?:,?\s+(\d{{4}}))?",
                          re.IGNORECASE)
MONTH_DAY_RE = re.compile(rf"({MONTH_ALTERNATION})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?(?!\d)", re.IGNORECASE)
NUMERIC_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{4}))?(?![\d:])")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
TIME_RE = re.compile(r"(?<![\d/\-])(?<!\d\.)(\d{1,2})\s*(?::|h|\.)\s*(\d{2})(?![\d/\-]|\.\d)\s*(am|pm|a\.m\.|p\.m\.|ص|م|صباحا|صباحاً|مساء|مساءً)?",
                     re.IGNORECASE)
HOUR_ONLY_RE = re.compile(r"(?<![\d:/\-])(?<!\d\.)(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.|h(?![a-z])|ص(?![\u0600-\u06FF])|م(?![\u0600-\u06FF])|صباحا|صباحاً|مساء|مساءً|الصبح|العصر)",
                          re.IGNORECASE)
PM_WORDS = ("pm", "p.m.", "م", "مساء", "مساءً", "العصر")


def normalise_digits(text: str) -> str:
    return text.translate(ARABIC_DIGITS)


def normalise(text: str) -> str:
    """Lower case, Arabic-Indic digits as 0-9, no accents or invisible characters ("Élodie" -> "elodie")."""
    text = normalise_digits(text).replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae")  # "sœur" -> "soeur"
    decomposed = unicodedata.normalize("NFKD", text)
    kept = "".join(ch for ch in decomposed if unicodedata.category(ch) not in ("Mn", "Cf"))
    return kept.lower()


def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\u00C0-\u017F'\-]+", text.lower())


def detect_language(text: str, fallback: str = "en") -> str:
    """'ar' for Arabic script or Arabizi, 'fr' or 'en' by common words; fallback when unclear."""
    if len(ARABIC_LETTER_RE.findall(text)) >= 2:
        return "ar"
    tokens = words(text)
    if is_arabizi(text):
        return "ar"
    french = sum(t in FRENCH_WORDS for t in tokens) + 2 * len(re.findall(r"[éèêàçù]", text.lower()))
    english = sum(t in ENGLISH_WORDS for t in tokens)
    if french == english == 0:
        return fallback
    return "fr" if french > english else "en"


def is_arabizi(text: str) -> bool:
    tokens = words(normalise_digits(text))
    markers = sum(t in ARABIZI_WORDS for t in tokens)
    digit_letters = sum(bool(re.search(r"[a-z][2379][a-z]|^[379][a-z]|[a-z][379]$", t)) for t in tokens
                        if not t.isdigit() and not re.fullmatch(r"nfc-?\d+", t))
    return markers + digit_letters >= 2


def find_file_number(text: str) -> str | None:
    text = normalise_digits(text)
    match = FILE_RE.search(text) or FILE_WORDS_RE.search(text)
    return f"NFC-{match.group(1)}" if match else None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str, today: date) -> list[date]:
    """Every calendar date written in the text. A date without a year is the next one on or after today."""
    text = normalise_digits(text)
    found: list[tuple[int, date]] = []

    def add(position: int, day: int, month: int, year: str | None) -> None:
        if year:
            value = _safe_date(int(year), month, day)
        else:
            value = _safe_date(today.year, month, day)
            if value and value < today:
                value = _safe_date(today.year + 1, month, day)
        if value:
            found.append((position, value))

    for m in ISO_DATE_RE.finditer(text):
        value = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if value:
            found.append((m.start(), value))
    for m in DAY_MONTH_RE.finditer(text):
        add(m.start(), int(m.group(1)), MONTH_WORD_TO_NUMBER[m.group(2).lower()], m.group(3))
    for m in MONTH_DAY_RE.finditer(text):
        add(m.start(), int(m.group(2)), MONTH_WORD_TO_NUMBER[m.group(1).lower()], m.group(3))
    stripped = ISO_DATE_RE.sub(" ", text)
    for m in NUMERIC_DATE_RE.finditer(stripped):
        add(m.start(), int(m.group(1)), int(m.group(2)), m.group(3))
    return [value for _, value in sorted(found, key=lambda pair: pair[0])]


def find_birth_date(text: str, today: date) -> date | None:
    """A date at least one year in the past is taken as a date of birth."""
    for value in find_dates(text, today):
        if value < today - timedelta(days=365):
            return value
    return None


def find_appointment_date(text: str, today: date) -> date | None:
    """The first date that is today or later (explicit date, weekday name or 'tomorrow')."""
    for value in find_dates(text, today):
        if value >= today:
            return value
    lowered = normalise_digits(text).lower()
    if any(word in lowered for word in TOMORROW_WORDS):
        return today + timedelta(days=1)
    for weekday, names in WEEKDAYS.items():
        if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", lowered) for name in names):
            days_ahead = (weekday - today.weekday()) % 7 or 7  # "Thursday" said on a Thursday = next week
            return today + timedelta(days=days_ahead)
    return None


def _to_24h(hour: int, minute: int, suffix: str | None) -> str | None:
    suffix = (suffix or "").lower()
    if suffix in PM_WORDS and hour < 12:
        hour += 12
    if suffix in ("am", "a.m.", "ص", "صباحا", "صباحاً", "الصبح") and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def find_times(text: str) -> list[str]:
    """All clock times as 'HH:MM' (24 h): '10:30', '10h30', '3pm', '٣ م', '15.00'."""
    text = normalise_digits(text)
    times = []
    for m in TIME_RE.finditer(text):
        value = _to_24h(int(m.group(1)), int(m.group(2)), m.group(3))
        if value:
            times.append(value)
    for m in HOUR_ONLY_RE.finditer(TIME_RE.sub(" ", text)):
        value = _to_24h(int(m.group(1)), 0, m.group(2) if m.group(2).lower() != "h" else None)
        if value:
            times.append(value)
    return times


def iso_or_none(value: str | None) -> str | None:
    """Accept 'YYYY-MM-DD' from a model; anything else becomes None."""
    if isinstance(value, str) and ISO_DATE_RE.fullmatch(value.strip()):
        parts = [int(p) for p in value.strip().split("-")]
        return value.strip() if _safe_date(*parts) else None
    return None


def hhmm_or_none(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    times = find_times(value)
    return times[0] if times else None
