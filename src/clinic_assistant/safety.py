"""Deterministic safety checks. Plain Python, so a prompt or a model mistake cannot switch them off.

1. Red flags (input): possible emergencies in Arabic (MSA, Gulf, Arabizi), English and French.
   Recall-first: a match stops the admin flow. The LLM classifier is a second, independent chance.
2. Clinical questions (input): high-precision phrases that ask for medical advice (doses, "is this normal?",
   "what does my result mean?"). A symptom mentioned as the reason for booking is NOT a clinical question.
3. Output check: every reply is scanned for medical advice (doses, diagnoses, result interpretation,
   treatment tips) and for other patients' identifiers. A blocked reply is swapped for a safe template.
4. Hashing: the audit log stores a salted hash of the file number, never the number itself.

All text is normalised first (lower case, no accents, Arabic hamza forms unified, Arabic-Indic digits as 0-9),
so the phrase lists below are normalised the same way when they are loaded.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache

from .config import env
from .text import normalise

# ---------------------------------------------------------------------------------------------------------
# 1. Red flags. Each category: phrases (any one is enough). Phrases are literal text, normalised on load.
# ---------------------------------------------------------------------------------------------------------
RED_FLAG_PHRASES = {
    "chest_pain": [
        "chest pain", "pain in my chest", "pain in his chest", "pain in her chest", "chest is tight", "tight chest",
        "chest tightness", "pressure in my chest", "pressure in his chest", "crushing pain", "heart attack",
        "pain spreading to my left arm", "pain going down his left arm", "pain in my left arm and jaw",
        "douleur a la poitrine", "douleur dans la poitrine", "douleurs a la poitrine", "douleur thoracique",
        "mal a la poitrine", "oppression dans la poitrine", "poitrine serree", "crise cardiaque", "infarctus",
        "ألم في الصدر", "ألم بالصدر", "الم في صدري", "ألم في صدري", "وجع في الصدر", "وجع بالصدر", "صدري يوجعني",
        "يعورني صدري", "يعوره صدره", "عوار في الصدر", "ضيق في الصدر", "ضغط على صدري", "نوبة قلبية", "جلطة قلبية",
        "sadri y3awerni", "sadri yoja3ni", "alam fi sadri", "wja3 fi sadri", "3awar sadr", "sadra y3awra",
    ],
    "breathing": [
        "can't breathe", "cannot breathe", "can not breathe", "cant breathe", "can't catch my breath",
        "trouble breathing", "struggling to breathe", "difficulty breathing", "hard to breathe", "short of breath",
        "shortness of breath", "gasping for air", "lips are turning blue", "lips are blue", "choking",
        "n'arrive pas a respirer", "n'arrive plus a respirer", "du mal a respirer", "difficulte a respirer",
        "difficultes a respirer", "j'etouffe", "il etouffe", "elle etouffe", "levres bleues", "suffoque",
        "ما أقدر أتنفس", "ما اقدر اتنفس", "ما يقدر يتنفس", "ما تقدر تتنفس", "لا أستطيع التنفس", "صعوبة في التنفس",
        "ضيق تنفس", "ضيق في التنفس", "ضيق نفس", "يختنق", "تختنق", "اختناق", "شفايفه زرقا", "شفايفها زرقا",
        "ma agdar atnafas", "ma a9dar atnafas", "ma yigdar yitnafas", "ma tigdar titnafas", "6ayg nafas", "dheeq nafas",
    ],
    "stroke": [
        "face is drooping", "face drooping", "face droop", "face has dropped", "one side of his face",
        "one side of her face", "one side of my face", "slurred speech", "slurring", "speech is slurred",
        "can't lift his arm", "can't lift her arm", "can't move his arm", "can't move her arm", "can't move my arm",
        "weak on one side", "weakness on one side", "numb on one side", "stroke",
        "visage qui tombe", "visage tombe", "bouche deviee", "bouche de travers", "parle bizarrement",
        "n'arrive plus a parler", "ne peut plus bouger le bras", "ne peut plus lever le bras", "faiblesse d'un cote",
        "engourdi d'un cote", "avc", "paralyse",
        "وجهه مايل", "وجهها مايل", "وجهه مال", "فمه مايل", "فمها مايل", "انحراف الفم", "ثقل في اللسان",
        "كلامه ثقيل", "كلامها ثقيل", "ما يقدر يتكلم", "ما تقدر تتكلم", "ما يقدر يحرك يده", "ما تقدر تحرك يدها",
        "ضعف في جهة", "تنميل في جهة", "جلطة دماغية", "سكتة دماغية", "جلطة",
        "wajha mayel", "wjha mayel", "kalama tageel", "jal6a", "jalta",
    ],
    "heavy_bleeding": [
        "bleeding heavily", "heavy bleeding", "bleeding a lot", "bleeding won't stop", "bleeding that won't stop",
        "bleeding does not stop", "bleeding doesn't stop", "won't stop bleeding", "losing a lot of blood",
        "blood everywhere", "vomiting blood", "coughing up blood", "soaked in blood",
        "saigne beaucoup", "saignement abondant", "saignement important", "saignement qui ne s'arrete pas",
        "ne s'arrete pas de saigner", "vomit du sang", "crache du sang", "perd beaucoup de sang",
        "نزيف قوي", "نزيف شديد", "نزيف ما يوقف", "نزيف ما وقف", "الدم ما وقف", "الدم ما يوقف", "ينزف كثير",
        "تنزف كثير", "ينزف بشدة", "يتقيأ دم", "يستفرغ دم", "يرجع دم",
        "nazeef gawi", "nazif gawi", "ynazif wayed", "dam ma wagaf", "el dam ma wagaf",
    ],
    "self_harm": [
        "kill myself", "end my life", "suicide", "suicidal", "don't want to live", "dont want to live",
        "don't want to be alive", "hurt myself", "harm myself", "self-harm", "self harm", "no reason to live",
        "better off dead", "take all my pills", "end it all",
        "me tuer", "me suicider", "en finir", "mettre fin a mes jours", "mettre fin a ma vie",
        "plus envie de vivre", "me faire du mal", "me blesser",
        "أنتحر", "انتحار", "أقتل نفسي", "أنهي حياتي", "ما أبي أعيش", "ما أبغى أعيش", "ما ابغي اعيش",
        "لا أريد أن أعيش", "لا اريد العيش", "أؤذي نفسي", "اذي نفسي", "أذية نفسي", "أموت نفسي",
        "abi amoot", "aby amoot", "abgha amoot", "ma abi a3eesh", "ma aby a3ish", "anta7ir", "ant7ar", "a2thi nafsi",
    ],
    "unresponsive_or_seizure": [
        "unconscious", "passed out and", "not waking up", "won't wake up", "he isn't responding",
        "she isn't responding", "he's not responding", "she's not responding", "not responding to me",
        "seizure", "convulsion", "fitting",
        "inconscient", "ne se reveille pas", "ne reagit pas", "convulse", "crise d'epilepsie",
        "فاقد الوعي", "فقد الوعي", "ما يصحى", "ما تصحى", "ما يستجيب", "ما تستجيب", "تشنج", "تشنجات", "نوبة صرع",
        "ma yis7a", "ma tis7a", "tashanuj",
    ],
}
# Two-part red flags: every group must match (e.g. pregnant AND bleeding).
COMBINED_FLAGS = {
    "pregnancy_bleeding": [
        ["pregnan", "enceinte", "حامل", "حمل", "7amel", "hamel"],
        # not "blood" alone: "I'm pregnant and need a blood test" is an ordinary booking
        ["bleed", "spotting", "saign", "perte de sang", "pertes de sang", "نزيف", "تنزف", "ينزف", "نزل دم",
         "نزول دم", "nazeef", "nazif", "dam yanzil"],
    ],
    "child_fever_drowsy": [
        ["baby", "son", "daughter", "child", "kid", "toddler", "bebe", "enfant", "fils", "fille", "petit",
         "طفل", "ولدي", "بنتي", "ابني", "بنيتي", "رضيع", "ياهل", "الياهل", "wildi", "bnti", "bntii", "ibni", "yahal"],
        ["fever", "temperature", "feverish", "fievre", "temperature", "حرارة", "حمى", "سخونة", "skhona", "7arara"],
        ["drowsy", "very sleepy", "hard to wake", "won't wake", "floppy", "limp", "lethargic", "barely moving",
         "somnolent", "difficile a reveiller", "tout mou", "toute molle", "ne bouge presque plus", "amorphe",
         "نعسان", "نعسانة", "ما يصحى", "ما تصحى", "خامل", "خاملة", "مرتخي", "مرتخية", "ما يتحرك", "na3san", "kha6il"],
    ],
}


@lru_cache(maxsize=1)
def _red_flag_regexes() -> dict[str, re.Pattern]:
    compiled = {}
    for category, phrases in RED_FLAG_PHRASES.items():
        alternatives = "|".join(re.escape(normalise(p)) for p in sorted(phrases, key=len, reverse=True))
        compiled[category] = re.compile(rf"(?<!\w)(?:{alternatives})")
    return compiled


ARABIC_PREFIX = "(?:ال|بال|وال|و|ب|ل)?"  # the, with the, and the, and, with, for
ARABIC_SUFFIX = "(?:ي|ه|ها|ك|كم|نا|هم)?"  # my, his, her, your, your (pl.), our, their: طفلي، حرارتها
# \w already matches Arabic letters. The whole Arabic block (\u0600-\u06FF) would also count the
# punctuation ؟ and ، as letters, so "حامل؟" (pregnant?) would not match "حامل".
WORD_END = r"(?!\w)"
WORD_START = r"(?<!\w)"


def _word_regex(word: str) -> str:
    """Match a word at the start of a word; short words (4 letters or fewer) must also end there.

    Arabic words may carry a prefix and a possessive suffix, and a final ة becomes ت before a suffix
    (حرارة -> حرارتها), so both spellings are accepted.
    """
    word = normalise(word)
    end = WORD_END if len(word) <= 4 else ""
    if re.match(r"[\u0600-\u06FF]", word):
        stem = re.escape(word[:-1]) + "(?:ة|ت)" if word.endswith("ة") else re.escape(word)
        return WORD_START + ARABIC_PREFIX + stem + ARABIC_SUFFIX + end
    return WORD_START + re.escape(word) + end


def _has_any(text: str, words: list[str]) -> bool:
    return any(re.search(_word_regex(w), text) for w in words)


def pattern_red_flag(message: str) -> str | None:
    """The first red-flag category the message matches, or None."""
    text = normalise(message).replace("’", "'")
    for category, regex in _red_flag_regexes().items():
        if regex.search(text):
            return category
    for category, groups in COMBINED_FLAGS.items():
        if all(_has_any(text, group) for group in groups):
            return category
    return None


# ---------------------------------------------------------------------------------------------------------
# 2. Clinical questions on the way in (asks for advice, not just mentions a symptom)
# ---------------------------------------------------------------------------------------------------------
# Medicine words (normalised). "Can I take..." only counts when a medicine follows: "can we take an earlier
# slot?" and "ممكن آخذ موعد" (can I book) are admin.
MED = (r"(medicine|medication|pill|tablet|dose|syrup|antibiotic|painkiller|paracetamol|panadol|ibuprofen|brufen|"
       r"aspirin|insulin|cream|ointment|drops|inhaler|vitamin|supplement|medicament|comprime|sirop|doliprane|"
       r"ibuprofene|antibiotique|creme|pommade|دواء|الدواء|حبوب|حبة|بنادول|مضاد|كريم|مرهم|انسولين|شراب|فيتامين|مسكن)")
CLINICAL_QUESTION_PATTERNS = [
    # doses and medicines
    r"how (much|many) .{0,40}(take|give|should)", r"\bdose\b", r"\bdosage\b", r"\d+\s*mg\b",
    rf"(can|should|may) (i|he|she|we) (take|give|stop|double|skip|mix|use) .{{0,30}}{MED}",
    r"double (the|my|his|her) dose",
    r"stop (taking|my|his|her) (medicine|medication|pills|tablets|treatment)",
    r"which (medicine|medication|antibiotic|cream|painkiller|tablet|syrup)", r"what (medicine|cream|antibiotic|painkiller|syrup)",
    r"combien de (comprimes|gouttes|cuilleres|mg|doliprane|paracetamol)", r"\bposologie\b", r"quelle dose",
    rf"(je peux|puis-je|peut-on|est-ce que je peux|dois-je) (prendre|donner|arreter|doubler|melanger) .{{0,30}}{MED}",
    r"quel (medicament|antibiotique|sirop)", r"quelle creme",
    r"كم (حبة|حبه|جرعة|ملعقة|مل)", r"جرعة",
    rf"(اقدر|ممكن|هل يمكنني|هل اقدر|يصير) (اخذ|اعطي|اوقف|اترك|اضاعف|استخدم) .{{0,30}}{MED}",
    r"(اي|ايش|وش|شو) (دواء|مضاد|كريم|مسكن|علاج)", r"اوقف (الدواء|العلاج|الحبوب)",
    r"kam 7aba", r"agdar akhith (dawa|7bob|panadol)", r"a9dar akhith (dawa|7bob|panadol)",
    # "is this normal?" / should I worry / what could it be
    r"is (it|this|that) normal", r"should i (be )?worr", r"what (could|might) (it|this) be", r"is (it|this) serious",
    r"do i need antibiotics", r"is (it|this) an? (infection|allergy)",
    r"(est-ce|c'est) (normal|grave)", r"dois-je m'inquieter", r"qu'est-ce que (ca|cela) peut etre",
    r"هل (هذا|هذي|هذه|ذا) (طبيعي|خطير)", r"(طبيعي|عادي|خطير)\s*[?؟]", r"لازم اقلق", r"(وش|ايش|شو) ممكن يكون",
    r"tabee3i", r"6abee3i", r"5a6eer",
    # what does my result mean
    r"what does (my|the|his|her) (result|level|number|value|report|test)s? (mean|say|show)", r"(is|are) my .{0,20}(result|level|value)s? (normal|high|low|ok|okay|good|bad)",
    r"(hba1c|cholesterol|ldl|tsh|ferritin|vitamin d|glucose|sugar|haemoglobin|hemoglobin)\D{0,15}\d", r"interpret",
    r"que (veut dire|signifie) (mon|le|ce) (resultat|taux)", r"(mon|ce) (resultat|taux) est(-il)? (normal|bon|eleve|bas)",
    r"(معنى|يعني ايش|وش يعني|شو يعني) .{0,20}(النتيجة|نتيجتي|التحليل|تحليلي)", r"(نتيجتي|تحليلي|النتيجة) (طبيعية|طبيعي|زينة|عالية|مرتفعة|منخفضة)",
    r"(نسبة|معدل) (السكر|الكوليسترول|فيتامين|الحديد|الغدة)",
]


@lru_cache(maxsize=1)
def _clinical_regex() -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in CLINICAL_QUESTION_PATTERNS))


def clinical_question(message: str) -> bool:
    return bool(_clinical_regex().search(normalise(message).replace("’", "'")))


# ---------------------------------------------------------------------------------------------------------
# 3a. Output check: medical advice in a reply
# ---------------------------------------------------------------------------------------------------------
DRUGS = ("paracetamol|acetaminophen|panadol|adol|doliprane|ibuprofen|ibuprofene|advil|brufen|nurofen|aspirin|aspirine|"
         "amoxicillin|amoxicilline|augmentin|antibiotic|antibiotique|antihistamine|antihistaminique|cetirizine|"
         "loratadine|metformin|insulin|insuline|omeprazole|hydrocortisone|steroid|cortisone|ors|"
         "بنادول|باراسيتامول|ادول|بروفين|ايبوبروفين|اسبرين|مضاد حيوي|مضادات حيوية|مضاد هيستامين|انسولين|كورتيزون")
ADVICE_PATTERNS = {
    "dose": r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|milligrams?|tablets?|pills?|capsules?|caplets?|puffs?|drops?|teaspoons?|"
            r"comprimes?|gelules?|cachets?|gouttes?|cuilleres?|حبة|حبات|حبوب|قرص|اقراص|ملغ|ملجم|مجم|ملغم|مل|نقطة|نقاط|ملعقة)(?![a-z])",
    "frequency": r"(?:every|each|toutes les|chaque|كل)\s*\d+\s*(?:hours|hrs|heures|ساعات|ساعة)|"
                 r"(?:once|twice|three times|une fois|deux fois|trois fois)\s+(?:a|per|par)\s+(?:day|jour)|"
                 r"(?:مرتين|مرة|ثلاث مرات)\s*(?:في اليوم|باليوم|يوميا)",
    "medicine_advice": rf"(?:you can|you could|you should|you may|try|take|give (?:him|her|them)|use|"
                       rf"vous pouvez|prenez|donnez|essayez|utilisez|appliquez|"
                       rf"يمكنك|تقدر|خذ|خذي|استخدم|استخدمي|اعطه|اعطيه|اعطيها|جرب|جربي)\b.{{0,40}}"
                       # whole words only ("ors" must not match inside "lors"); Arabic may start with ال
                       rf"(?<!\w)(?:ال|بال)?(?:{DRUGS})(?!\w)",
    "diagnosis": r"(?:it|this|that) (?:sounds|looks|seems) like|you (?:probably|likely|may|might|could) have|"
                 r"(?:is|it's|that's) (?:probably|likely|most likely) (?:a|an|just|nothing|not)|nothing to worry about|"
                 r"(?:is|it's|isn't) (?:not )?serious|"
                 r"il semble que vous ayez|vous avez probablement|c'est (?:probablement|surement|sans doute) (?:une|un|rien)|"
                 r"rien de grave|pas grave|ce n'est pas (?:grave|serieux)|"
                 r"يبدو (?:انك|انه|انها|ان عندك)|على الاغلب (?:عندك|هذا|انه)|غالبا (?:عندك|هذا)|ما فيه شي خطير|"
                 r"مو خطير|ليس خطيرا|ليست خطيرة|لا داعي للقلق",
    "result_meaning": r"(?:your|the|his|her) (?:result|level|value|reading|number|hba1c|cholesterol|tsh|ferritin|"
                      r"vitamin d|sugar|glucose)s? (?:is|are|looks?|seems?) (?:normal|high|low|fine|good|ok|okay|"
                      r"abnormal|elevated|borderline|within)|within (?:the )?normal range|in the normal range|"
                      r"(?:slightly|a bit|mildly) (?:high|low|elevated|raised)|prediabet|pre-diabet|"
                      r"(?:votre|le|ce) (?:resultat|taux) (?:est|semble) (?:normal|eleve|bas|bon)|dans la norme|"
                      r"legerement (?:eleve|bas)|"
                      r"(?:نتيجتك|النتيجة|المعدل|النسبة|نسبة السكر) (?:طبيعية|طبيعي|مرتفعة|منخفضة|عالية|زينة|جيدة)|"
                      r"ضمن المعدل الطبيعي|في الحدود الطبيعية|ضمن الطبيعي",
    "symptom_reassurance": r"(?:it's|it is|this is|that's|that is) (?:completely |perfectly |quite |very )?(?:normal|common) "
                           r"(?:to|for|after|when)|c'est (?:tout a fait |assez )?(?:normal|frequent) (?:de|d'|apres|quand)|"
                           r"هذا (?:طبيعي|شي طبيعي|عادي) (?:بعد|عند|مع)",
    "treatment_tip": r"(?:i recommend|i suggest|i'd suggest|you should try|try) (?:rest|resting|drinking|applying|using|"
                     r"taking|ice|a cold compress|a warm compress|fluids)|apply (?:a|some) (?:cream|ointment|ice|compress)|"
                     r"je vous (?:conseille|recommande|suggere) de (?:prendre|appliquer|boire|vous reposer)|"
                     r"(?:انصحك|اقترح عليك) (?:ب|ان|تشرب|تاخذ|تحط)|ضع كمادات|اشرب سوائل",
}


@lru_cache(maxsize=1)
def _advice_regexes() -> dict[str, re.Pattern]:
    return {name: re.compile(pattern) for name, pattern in ADVICE_PATTERNS.items()}


def find_medical_advice(reply: str) -> list[str]:
    """Names of the advice patterns found in a reply ([] = clean)."""
    text = normalise(reply).replace("’", "'")
    return [name for name, regex in _advice_regexes().items() if regex.search(text)]


# ---------------------------------------------------------------------------------------------------------
# 3b. Output check: other patients' identifiers in a reply
# ---------------------------------------------------------------------------------------------------------
def _digits(text: str) -> str:
    return re.sub(r"\D", "", normalise(text))


def _phone_key(phone: str) -> str:
    digits = _digits(phone)
    for prefix in ("00971", "971", "0"):
        if digits.startswith(prefix):
            return digits[len(prefix):]
    return digits


def _date_spellings(iso: str) -> list[str]:
    year, month, day = iso.split("-")
    d, m = str(int(day)), str(int(month))
    return [iso, f"{day}/{month}/{year}", f"{d}/{m}/{year}", f"{day}-{month}-{year}", f"{day}.{month}.{year}"]


def find_pii_leaks(reply: str, patients: dict, allowed_file: str | None, public_text: str = "") -> list[str]:
    """Identifiers of patients other than `allowed_file` that appear in the reply.

    public_text is what the user typed: repeating it back is not a leak.
    Checks full names (either order), phone digits, emails, file numbers and dates of birth.
    """
    text, public = normalise(reply), normalise(public_text)
    reply_numbers = [_digits(run) for run in re.findall(r"\+?\d[\d\s\-.()/]*\d", text)]
    public_numbers = _digits(public)
    leaks = []
    for file_number, patient in patients.items():
        if file_number == allowed_file:
            continue
        found = []
        name_words = re.findall(r"[a-z]+", normalise(patient["full_name"]))
        sep = r"[\W_]*"
        forward = sep.join(map(re.escape, name_words))
        backward = sep.join(map(re.escape, name_words[-1:] + name_words[:-1]))
        if re.search(rf"\b(?:{forward}|{backward})\b", text) and not re.search(rf"\b(?:{forward}|{backward})\b", public):
            found.append("name")
        key = _phone_key(patient["phone"])
        if any(key and key in number for number in reply_numbers) and key not in public_numbers:
            found.append("phone")
        email = normalise(patient["email"])
        if email in text and email not in public:
            found.append("email")
        number = file_number.split("-")[1]
        if re.search(rf"(?<!\d){number}(?!\d)", text) and number not in public_numbers:
            found.append("file_number")
        if any(s in text for s in _date_spellings(patient["date_of_birth"])) and \
                not any(s in public for s in _date_spellings(patient["date_of_birth"])):
            found.append("date_of_birth")
        leaks += [f"{file_number}:{kind}" for kind in found]
    return leaks


# ---------------------------------------------------------------------------------------------------------
# 4. Requests about another person, and hashing for the audit log
# ---------------------------------------------------------------------------------------------------------
OTHER_PERSON_PATTERNS = [
    r"(?:my|our) (?:sister|brother|wife|husband|mother|mum|mom|father|dad|friend|neighbou?r|colleague|cousin|aunt|uncle)'?s? "
    r"(?:appointment|booking|result|results|file|details|phone|number|visit)",
    r"(?:is|was) .{2,40} (?:a patient|registered) (?:here|at|with|of)", r"(?:phone|mobile) number of (?:patient|mr|mrs|ms|miss)",
    r"(?:list|show me|tell me) (?:all |today's |the )?(?:patients|appointments of|bookings of)",
    r"(?:rendez-vous|resultats?|dossier|numero) de (?:ma|mon) (?:soeur|frere|femme|mari|mere|pere|amie?|voisine?|collegue)",
    r"est-ce que .{2,40} est (?:patient|patiente|inscrite?)", r"(?:la liste|liste) des patients",
    r"(?:موعد|مواعيد|نتيجة|نتائج|ملف|رقم) (?:اختي|اخوي|اخي|زوجتي|زوجي|امي|ابوي|ابي|صديقتي|صديقي|جارتي|جاري|زميلتي|زميلي)",
    r"(?:هل|اذا) .{2,30} (?:مريض|مريضة|مسجل|مسجلة) (?:عندكم|في العيادة)", r"قائمة المرضى",
    r"maw3ed (?:ukhti|ukhty|akhoy|zawjti|zoji|ummi|ubooy)",
]


@lru_cache(maxsize=1)
def _other_person_regex() -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in OTHER_PERSON_PATTERNS))


def asks_about_other_person(message: str) -> bool:
    return bool(_other_person_regex().search(normalise(message).replace("’", "'")))


def hash_id(value: str | None) -> str | None:
    """Salted SHA-256, first 16 hex characters. The audit log never sees the raw file number."""
    if not value:
        return None
    salt = env("AUDIT_HASH_SALT", "demo-salt-change-me")
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]
