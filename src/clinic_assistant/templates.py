"""Fixed replies in Arabic, English and French.

Safety replies (urgent, medical refusal, privacy, identity) are ALWAYS these templates, never model text,
so a clinician can sign off every word once. Admin replies are normally written by the model from facts;
the templates below are the fallback and the rules baseline's replies.

The Arabic and French text was machine-written and must be checked by a native speaker and, for the
safety templates, signed off by a clinician before any real use.
"""

from __future__ import annotations

from datetime import date

from .clinic import SPECIALTY_NAMES
from .config import AMBULANCE, CLINIC_PHONE, POLICE

T = {
    "en": {
        "disclosure": f"Hello, I'm the AI assistant of Sahara Demo Family Clinic (fictional). I help with bookings and admin questions only, not medical advice. To reach a person, type \"staff\" or call {CLINIC_PHONE}.",
        "urgent": f"URGENT: this may be an emergency. Call {AMBULANCE} for an ambulance now, or go to the nearest emergency department. Do not wait for a reply in this chat. I have alerted our clinic staff.",
        "urgent_self_harm": f"I'm really sorry you're feeling this way. Your safety matters most right now: call {AMBULANCE} (ambulance) or {POLICE} (police), or go to the nearest emergency department. If you can, stay with someone you trust. I have alerted our clinic staff.",
        "urgent_followup": f"Please call {AMBULANCE} or go to the nearest emergency department now. Our staff have been alerted and will contact you; this chat is paused for admin requests.",
        "medical_refusal": f"I'm sorry, I can't give medical advice: diagnoses, medicines, doses, or what symptoms or test results mean. I've passed your question to our nurse team, who will reply during opening hours. If it feels urgent or gets worse, call {AMBULANCE} or go to the nearest emergency department. I can still help with bookings and admin questions.",
        "unscreened_note": f"If this is an emergency, call {AMBULANCE} or go to the nearest emergency department.",
        "blocked_reply": f"I'm sorry, I can't help with that in this chat. I've asked our team to follow up with you. For medical questions a nurse or doctor will help; in an emergency call {AMBULANCE}.",
        "privacy_refusal": "For privacy, I can't share or confirm any information about another person, including whether they are a patient here. They can contact us themselves, or visit reception with their written consent.",
        "identity_request": "To help with this I first need to check your file. Please send your file number (for example NFC-12345) and your date of birth.",
        "identity_failed": "Sorry, that file number and date of birth don't match our records. Please check them and send them again.",
        "identity_locked": f"I couldn't verify your details, so I've passed this chat to our reception team. They will reply during opening hours, or you can call {CLINIC_PHONE}.",
        "handover": f"I've passed this conversation to our reception team. A person will reply here during opening hours (Monday to Friday 08:00-20:00, Saturday 09:00-17:00), or you can call {CLINIC_PHONE}.",
        "clarify": "I can help with booking, rescheduling or cancelling appointments, doctor availability, opening hours, directions, what to bring, preparation instructions, insurance and billing questions, and whether a lab result is ready. What would you like to do?",
        "ask_doctor": "Which doctor or department would you like? We have family medicine, paediatrics, dermatology, obstetrics and gynaecology, and ENT.",
        "no_appointment": "I can't find an upcoming appointment on your file. Would you like to book one?",
        "no_slots": "Sorry, there are no free times for that in the next 7 days. Would you like another doctor or another week?",
        "slots_intro": "Here are the next free times:",
        "slots_offered_end": "Which one would you like?",
        "booked": "Your appointment is booked: {slot}. Please arrive 15 minutes early with your Emirates ID and insurance card.",
        "rescheduled": "Your appointment is moved to {slot}. Your old time is released.",
        "cancelled": "Your appointment on {slot} is cancelled. If you need a new one, just tell me.",
        "appointment_info": "Your next appointment is {slot}.",
        "lab_ready": "Your {test} result is ready. You can view it in the patient portal or collect it at reception with your Emirates ID. Your doctor will explain it.",
        "lab_processing": "Your {test} result is not ready yet; it is expected by {when}. Your doctor will explain it once it is ready.",
        "lab_none": "I can't find a lab order on your file. If you had a test recently, our reception team can check.",
        "insurance_yes": "Yes, we accept {insurer}. Pre-approval is needed for: {pre}.",
        "insurance_yes_nopre": "Yes, we accept {insurer}.",
        "insurance_no": "Sorry, we don't accept {insurer}. You can be seen as self-pay and claim back from your insurer.",
        "insurance_unknown": "{insurer} is not on our list. We accept Gulf Shield Health, Oasis Care, Falcon Cover, Palm Assure and Lotus Mutual Insurance (demo). Reception can confirm on {phone}.",
        "callback_logged": "I've asked our {team} team to call you back on the number in your file during opening hours.",
        "nurse_team": "nurse", "reception_team": "reception", "billing_team": "billing",
    },
    "fr": {
        "disclosure": f"Bonjour, je suis l'assistant IA de la Clinique familiale de démonstration Sahara (fictive). J'aide uniquement pour les rendez-vous et les questions administratives, pas pour les conseils médicaux. Pour parler à une personne, écrivez « staff » ou appelez le {CLINIC_PHONE}.",
        "urgent": f"URGENT : il peut s'agir d'une urgence. Appelez le {AMBULANCE} (ambulance) maintenant, ou rendez-vous aux urgences les plus proches. N'attendez pas de réponse dans ce chat. J'ai alerté l'équipe de la clinique.",
        "urgent_self_harm": f"Je suis vraiment désolé que vous traversiez cela. Votre sécurité passe avant tout : appelez le {AMBULANCE} (ambulance) ou le {POLICE} (police), ou rendez-vous aux urgences les plus proches. Si possible, restez avec une personne de confiance. J'ai alerté l'équipe de la clinique.",
        "urgent_followup": f"Appelez le {AMBULANCE} ou rendez-vous aux urgences les plus proches maintenant. L'équipe a été alertée et va vous contacter ; ce chat est en pause pour les demandes administratives.",
        "medical_refusal": f"Désolé, je ne peux pas donner de conseil médical : diagnostic, médicaments, doses, ou signification de symptômes ou de résultats. J'ai transmis votre question à l'équipe infirmière, qui vous répondra pendant les heures d'ouverture. Si cela vous semble urgent ou s'aggrave, appelez le {AMBULANCE} ou allez aux urgences les plus proches. Je peux toujours vous aider pour les rendez-vous et l'administratif.",
        "unscreened_note": f"S'il s'agit d'une urgence, appelez le {AMBULANCE} ou rendez-vous aux urgences les plus proches.",
        "blocked_reply": f"Désolé, je ne peux pas vous aider sur ce point dans ce chat. J'ai demandé à l'équipe de vous recontacter. Pour les questions médicales, une infirmière ou un médecin vous aidera ; en cas d'urgence, appelez le {AMBULANCE}.",
        "privacy_refusal": "Pour des raisons de confidentialité, je ne peux ni partager ni confirmer d'information sur une autre personne, y compris si elle est patiente ici. Elle peut nous contacter elle-même, ou passer à l'accueil avec son accord écrit.",
        "identity_request": "Pour vous aider, je dois d'abord vérifier votre dossier. Envoyez-moi votre numéro de dossier (par exemple NFC-12345) et votre date de naissance.",
        "identity_failed": "Désolé, ce numéro de dossier et cette date de naissance ne correspondent pas à nos registres. Vérifiez-les et renvoyez-les.",
        "identity_locked": f"Je n'ai pas pu vérifier vos informations, j'ai donc transmis ce chat à l'accueil. Une personne vous répondra pendant les heures d'ouverture, ou appelez le {CLINIC_PHONE}.",
        "handover": f"J'ai transmis cette conversation à l'accueil. Une personne vous répondra ici pendant les heures d'ouverture (du lundi au vendredi 08:00-20:00, samedi 09:00-17:00), ou appelez le {CLINIC_PHONE}.",
        "clarify": "Je peux vous aider à prendre, déplacer ou annuler un rendez-vous, voir les disponibilités des médecins, les horaires, l'accès, quoi apporter, les consignes de préparation, l'assurance et la facturation, et savoir si un résultat d'analyse est prêt. Que souhaitez-vous faire ?",
        "ask_doctor": "Quel médecin ou quel service souhaitez-vous ? Nous avons la médecine générale, la pédiatrie, la dermatologie, la gynécologie-obstétrique et l'ORL.",
        "no_appointment": "Je ne trouve pas de rendez-vous à venir dans votre dossier. Voulez-vous en prendre un ?",
        "no_slots": "Désolé, il n'y a pas de créneau libre pour cela dans les 7 prochains jours. Voulez-vous un autre médecin ou une autre semaine ?",
        "slots_intro": "Voici les prochains créneaux libres :",
        "slots_offered_end": "Lequel vous convient ?",
        "booked": "Votre rendez-vous est réservé : {slot}. Merci d'arriver 15 minutes en avance avec votre Emirates ID et votre carte d'assurance.",
        "rescheduled": "Votre rendez-vous est déplacé au {slot}. L'ancien créneau est libéré.",
        "cancelled": "Votre rendez-vous du {slot} est annulé. Si vous en voulez un autre, dites-le-moi.",
        "appointment_info": "Votre prochain rendez-vous : {slot}.",
        "lab_ready": "Votre résultat ({test}) est prêt. Vous pouvez le consulter sur le portail patient ou le retirer à l'accueil avec votre Emirates ID. Votre médecin vous l'expliquera.",
        "lab_processing": "Votre résultat ({test}) n'est pas encore prêt ; il est attendu pour le {when}. Votre médecin vous l'expliquera quand il sera prêt.",
        "lab_none": "Je ne trouve pas d'analyse dans votre dossier. Si vous avez fait une analyse récemment, l'accueil peut vérifier.",
        "insurance_yes": "Oui, nous acceptons {insurer}. Un accord préalable est nécessaire pour : {pre}.",
        "insurance_yes_nopre": "Oui, nous acceptons {insurer}.",
        "insurance_no": "Désolé, nous n'acceptons pas {insurer}. Vous pouvez payer directement et vous faire rembourser par votre assureur.",
        "insurance_unknown": "{insurer} ne figure pas sur notre liste. Nous acceptons Gulf Shield Health, Oasis Care, Falcon Cover, Palm Assure et Lotus Mutual Insurance (demo). L'accueil peut confirmer au {phone}.",
        "callback_logged": "J'ai demandé à l'équipe {team} de vous rappeler au numéro de votre dossier pendant les heures d'ouverture.",
        "nurse_team": "infirmière", "reception_team": "d'accueil", "billing_team": "facturation",
    },
    "ar": {
        "disclosure": f"مرحباً، أنا المساعد الذكي (ذكاء اصطناعي) لعيادة صحارى التجريبية للعائلة (وهمية). أساعد في الحجوزات والأسئلة الإدارية فقط، ولا أقدم نصائح طبية. للتحدث مع موظف اكتب \"موظف\" أو اتصل على {CLINIC_PHONE}.",
        "urgent": f"عاجل: قد تكون هذه حالة طارئة. اتصل الآن بالإسعاف على الرقم {AMBULANCE} أو توجه إلى أقرب قسم طوارئ. لا تنتظر الرد في هذه المحادثة. لقد نبهت فريق العيادة.",
        "urgent_self_harm": f"أنا آسف جداً لما تمر به. سلامتك هي الأهم الآن: اتصل بالإسعاف {AMBULANCE} أو الشرطة {POLICE}، أو توجه إلى أقرب قسم طوارئ. إن استطعت، ابقَ مع شخص تثق به. لقد نبهت فريق العيادة.",
        "urgent_followup": f"يرجى الاتصال بالرقم {AMBULANCE} أو التوجه إلى أقرب قسم طوارئ الآن. تم تنبيه الفريق وسيتواصل معك، والمحادثة متوقفة عن الطلبات الإدارية.",
        "medical_refusal": f"عذراً، لا أستطيع تقديم نصيحة طبية: التشخيص أو الأدوية أو الجرعات أو معنى الأعراض أو نتائج التحاليل. حولت سؤالك إلى فريق التمريض وسيرد عليك خلال ساعات العمل. إذا شعرت أن الأمر عاجل أو ساءت الحالة، اتصل بالرقم {AMBULANCE} أو توجه إلى أقرب قسم طوارئ. ما زلت أستطيع مساعدتك في الحجوزات والأمور الإدارية.",
        "unscreened_note": f"إذا كانت حالة طارئة، اتصل بالرقم {AMBULANCE} أو توجه إلى أقرب قسم طوارئ.",
        "blocked_reply": f"عذراً، لا أستطيع المساعدة في هذا الأمر هنا. طلبت من الفريق التواصل معك. الأسئلة الطبية يجيب عنها الممرض أو الطبيب، وفي الطوارئ اتصل بالرقم {AMBULANCE}.",
        "privacy_refusal": "حفاظاً على الخصوصية، لا أستطيع مشاركة أو تأكيد أي معلومات عن شخص آخر، حتى إن كان مريضاً لدينا أم لا. يمكنه التواصل معنا بنفسه، أو زيارة الاستقبال مع موافقته المكتوبة.",
        "identity_request": "لمساعدتك أحتاج أولاً إلى التحقق من ملفك. أرسل رقم الملف (مثلاً NFC-12345) وتاريخ ميلادك.",
        "identity_failed": "عذراً، رقم الملف وتاريخ الميلاد لا يتطابقان مع سجلاتنا. يرجى التأكد منهما وإرسالهما مرة أخرى.",
        "identity_locked": f"لم أتمكن من التحقق من بياناتك، لذلك حولت المحادثة إلى فريق الاستقبال. سيرد عليك موظف خلال ساعات العمل، أو اتصل على {CLINIC_PHONE}.",
        "handover": f"حولت هذه المحادثة إلى فريق الاستقبال. سيرد عليك موظف هنا خلال ساعات العمل (من الاثنين إلى الجمعة 08:00-20:00، والسبت 09:00-17:00)، أو اتصل على {CLINIC_PHONE}.",
        "clarify": "أستطيع مساعدتك في حجز موعد أو تغييره أو إلغائه، ومواعيد الأطباء، وساعات العمل، والعنوان، وما تحضره معك، وتعليمات التحضير، والتأمين والفواتير، ومعرفة إن كانت نتيجة التحليل جاهزة. كيف أساعدك؟",
        "ask_doctor": "أي طبيب أو قسم تفضل؟ لدينا طب الأسرة وطب الأطفال والأمراض الجلدية والنساء والولادة والأنف والأذن والحنجرة.",
        "no_appointment": "لا أجد موعداً قادماً في ملفك. هل تريد حجز موعد؟",
        "no_slots": "عذراً، لا توجد مواعيد متاحة لذلك خلال الأيام السبعة القادمة. هل تفضل طبيباً آخر أو أسبوعاً آخر؟",
        "slots_intro": "هذه أقرب المواعيد المتاحة:",
        "slots_offered_end": "أي موعد يناسبك؟",
        "booked": "تم حجز موعدك: {slot}. يرجى الحضور قبل الموعد بـ 15 دقيقة مع الهوية الإماراتية وبطاقة التأمين.",
        "rescheduled": "تم نقل موعدك إلى {slot}، وتم إلغاء الموعد القديم.",
        "cancelled": "تم إلغاء موعدك في {slot}. إذا احتجت موعداً جديداً أخبرني.",
        "appointment_info": "موعدك القادم: {slot}.",
        "lab_ready": "نتيجة تحليل {test} جاهزة. يمكنك الاطلاع عليها في بوابة المرضى أو استلامها من الاستقبال مع الهوية الإماراتية. سيشرحها لك طبيبك.",
        "lab_processing": "نتيجة تحليل {test} ليست جاهزة بعد، ومن المتوقع أن تكون جاهزة بتاريخ {when}. سيشرحها لك طبيبك عندما تجهز.",
        "lab_none": "لا أجد طلب تحليل في ملفك. إذا أجريت تحليلاً مؤخراً يمكن للاستقبال التحقق.",
        "insurance_yes": "نعم، نقبل تأمين {insurer}. تحتاج موافقة مسبقة في: {pre}.",
        "insurance_yes_nopre": "نعم، نقبل تأمين {insurer}.",
        "insurance_no": "عذراً، لا نقبل تأمين {insurer}. يمكنك الدفع مباشرة ثم المطالبة من شركة التأمين.",
        "insurance_unknown": "{insurer} ليس ضمن قائمتنا. نقبل Gulf Shield Health وOasis Care وFalcon Cover وPalm Assure وLotus Mutual Insurance (demo). يمكن للاستقبال التأكيد على {phone}.",
        "callback_logged": "طلبت من فريق {team} الاتصال بك على الرقم المسجل في ملفك خلال ساعات العمل.",
        "nurse_team": "التمريض", "reception_team": "الاستقبال", "billing_team": "الفواتير",
    },
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
           "ديسمبر"],
}
WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "ar": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
}
PRE_APPROVAL = {
    "ultrasound": {"en": "ultrasound", "fr": "échographie", "ar": "الأشعة الصوتية"},
    "dermatology procedures": {"en": "dermatology procedures", "fr": "actes de dermatologie", "ar": "إجراءات الجلدية"},
    "specialist referral": {"en": "specialist referrals", "fr": "orientation vers un spécialiste", "ar": "التحويل إلى أخصائي"},
}


def text(language: str, key: str) -> str:
    return T.get(language, T["en"])[key]


def format_date(iso: str, language: str) -> str:
    day = date.fromisoformat(iso)
    weekday = WEEKDAYS[language][day.weekday()]
    return f"{weekday} {day.day} {MONTHS[language][day.month - 1]} {day.year}"


def format_slot(slot: dict, language: str) -> str:
    doctor = slot["doctor_ar"] if language == "ar" and slot.get("doctor_ar") else slot["doctor"]
    specialty = SPECIALTY_NAMES.get(slot.get("specialty", ""), {}).get(language, "")
    at = {"en": "at", "fr": "à", "ar": "الساعة"}[language]
    return f"{format_date(slot['date'], language)} {at} {slot['time']}, {doctor}" + (f" ({specialty})" if specialty else "")


def urgent(language: str, category: str) -> str:
    return text(language, "urgent_self_harm" if category == "self_harm" else "urgent")


def render_admin(facts: dict, language: str) -> str:
    """Deterministic admin reply from facts (rules baseline, offline demo, and fallback if the model fails)."""
    outcome = facts["outcome"]
    if outcome in ("slots_offered", "slots_shown"):
        lines = [text(language, "slots_intro")] + [f"- {format_slot(s, language)}" for s in facts["slots"]]
        if outcome == "slots_offered":
            lines.append(text(language, "slots_offered_end"))
        return "\n".join(lines)
    if outcome in ("booked", "rescheduled", "cancelled", "appointment_info"):
        return text(language, outcome).format(slot=format_slot(facts["appointment"], language))
    if outcome == "lab_status":
        if not facts["tests"]:
            return text(language, "lab_none")
        parts = []
        for test in facts["tests"]:
            key = "lab_ready" if test["status"] == "ready" else "lab_processing"
            parts.append(text(language, key).format(test=test["test"],
                                                    when=format_date(test["expected_ready_date"], language)))
        return " ".join(parts)
    if outcome == "insurance_answered":
        result = facts["insurance"]
        if not result["known"]:
            return text(language, "insurance_unknown").format(insurer=result["insurer"] or "?", phone=CLINIC_PHONE)
        if not result["accepted"]:
            return text(language, "insurance_no").format(insurer=result["insurer"])
        pre = ", ".join(PRE_APPROVAL[p][language] for p in result["pre_approval_for"])
        key = "insurance_yes" if pre else "insurance_yes_nopre"
        return text(language, key).format(insurer=result["insurer"], pre=pre)
    if outcome == "callback_logged":
        return text(language, "callback_logged").format(team=text(language, f"{facts['team']}_team"))
    if outcome.startswith("info:"):
        return facts["section"]
    return text(language, outcome) if outcome in T["en"] else text(language, "clarify")
