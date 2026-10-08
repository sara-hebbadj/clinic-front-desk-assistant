"""The front-desk assistant: one call to `handle()` per patient message.

Order of checks (each step can end the turn):

 1. Emergency already raised in this chat -> repeat the urgent advice, hand over.
 2. Red flags: pattern list OR model classifier ("either fires") -> urgent template + 998 + staff alert.
 3. Understanding (model, or keywords in the rules baseline) -> intent and details as JSON.
 4. Clinical question (model flag OR pattern list) -> kind refusal + route to the nurse queue.
 5. Question about another person -> privacy refusal.
 6. Asks for a person -> handover queue.
 7. Admin route chosen by CODE: identity check, then tools (slots, book, reschedule, cancel, lab status,
    insurance, clinic documents).
 8. Reply: the model writes admin replies from facts; safety replies are fixed templates.
 9. Output check: medical advice or another patient's data -> blocked, safe template instead.
10. AI disclosure on the first reply; minimised audit log line.

The model never chooses a tool and never sees another patient's record.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import keyword_brain, knowledge, prompts, safety, templates
from .clinic import ClinicStore
from .config import LOW_CONFIDENCE, MAX_IDENTITY_ATTEMPTS
from .llm import parse_json
from .staff import StaffDesk
from .templates import text
from .text import detect_language, hhmm_or_none, iso_or_none

NEEDS_IDENTITY = {"book", "reschedule", "cancel", "lab_status", "callback", "my_appointment"}
MODEL_WRITTEN = {"slots_offered", "slots_shown", "booked", "rescheduled", "cancelled", "lab_status",
                 "insurance_answered", "callback_logged", "appointment_info"}  # plus every "info:<topic>"
INTENTS = {"book", "reschedule", "cancel", "availability", "clinic_info", "insurance_check", "lab_status",
           "callback", "my_appointment", "human", "provide_details", "greeting", "other"}


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    language: str = "en"
    disclosed: bool = False
    emergency: bool = False
    verified_file: str | None = None
    identity: dict = field(default_factory=dict)  # file number / date of birth given so far
    failed_checks: int = 0
    pending: dict = field(default_factory=dict)  # the request being completed, e.g. {"intent": "book", ...}
    offered: list = field(default_factory=list)  # slots offered in the last reply
    unclear_turns: int = 0
    typed_text: str = ""  # what the patient typed; repeating it back is not a leak. Memory only, never logged.
    last_reply: str = ""


@dataclass
class Turn:
    reply: str
    outcome: str
    intent: str
    language: str
    tool_calls: list
    red_flag: dict | None
    guard_events: list
    latency_ms: int
    facts: dict = field(default_factory=dict)  # what the tools returned (for scoring and the staff console)


class FrontDeskAssistant:
    def __init__(self, llm=None, store: ClinicStore | None = None, desk: StaffDesk | None = None,
                 reply_role: str = "cheap"):
        """llm=None is the rules-only baseline: keyword understanding, template replies, patterns only."""
        self.llm = llm
        self.store = store or ClinicStore()
        self.desk = desk or StaffDesk()
        self.reply_role = reply_role

    # ------------------------------------------------------------------ main entry point
    def handle(self, session: Session, message: str) -> Turn:
        start = time.perf_counter()
        session.typed_text += "\n" + message
        session.language = detect_language(message, fallback=session.language)
        events: list[str] = []
        if session.emergency:  # 1
            self.desk.handover(session.session_id, session.verified_file, "emergency_followup")
            return self._finish(session, text(session.language, "urgent_followup"), "emergency_followup",
                                "emergency", [], None, events, start)
        flag, u = self._screen_and_understand(message, session, events)  # 2 and 3
        if flag:
            session.emergency = True
            self.desk.alert(session.session_id, session.verified_file, flag["category"], flag["sources"])
            flag["alert_ms"] = int((time.perf_counter() - start) * 1000)
            reply = templates.urgent(session.language, flag["category"])
            return self._finish(session, reply, "emergency", "emergency", [], flag, events, start)

        if u["clinical_question"] or safety.clinical_question(message):  # 4
            self.desk.handover(session.session_id, session.verified_file, "nurse")
            session.pending, session.offered = {}, []
            return self._finish(session, text(session.language, "medical_refusal"), "routed_to_nurse",
                                "medical_question", ["route_to_nurse"], None, events, start)
        other_file = bool(session.verified_file and u["file_number"] and u["file_number"] != session.verified_file)
        if other_file and u["date_of_birth"]:  # a second file with its own date of birth: check it again
            session.verified_file, other_file = None, False
        asks_other_file = other_file  # another file number without its date of birth
        if u["other_person"] or safety.asks_about_other_person(message) or asks_other_file:  # 5
            return self._finish(session, text(session.language, "privacy_refusal"), "privacy_refused",
                                "other_person", [], None, events, start)
        if u["wants_human"] or u["intent"] == "human":  # 6
            self.desk.handover(session.session_id, session.verified_file, "reception")
            return self._finish(session, text(session.language, "handover"), "handover", "human",
                                ["handover"], None, events, start)

        tools: list[str] = []
        facts = self._route(session, u, tools)  # 7
        facts["language"] = session.language
        reply = self._write_reply(message, facts, events)  # 8
        reply, outcome = self._check_output(session, reply, facts["outcome"], events)  # 9
        turn = self._finish(session, reply, outcome, facts.get("intent", u["intent"]), tools, None, events, start)
        turn.facts = {k: v for k, v in facts.items() if k != "section"}
        return turn

    # ------------------------------------------------------------------ steps
    def _screen_and_understand(self, message: str, session: Session, events: list) -> tuple[dict | None, dict | None]:
        """Red flags first. The pattern list is instant; if it fires, nothing else runs.

        Otherwise the model red-flag screen and the understanding step run at the same time (two threads),
        which saves one model round trip on every normal message. If the screen flags an emergency we answer
        at once and ignore the understanding result.
        """
        category = safety.pattern_red_flag(message)
        if category:
            return {"category": category, "sources": ["pattern"]}, None
        if not self.llm:  # rules baseline: patterns only
            return None, self._understand(message, session, events)
        pool = ThreadPoolExecutor(max_workers=2)
        screen = pool.submit(self._model_red_flag, message, events)
        understanding = pool.submit(self._understand, message, session, events)
        flag = screen.result()
        pool.shutdown(wait=False)  # an emergency reply does not wait for the understanding step
        return (flag, None) if flag else (None, understanding.result())

    def _model_red_flag(self, message: str, events: list) -> dict | None:
        """The model screen, tried twice. A flag dict, or None when the model says it is not an emergency.

        If both tries fail (outage, or no valid JSON), the message is "unscreened": the chat goes on, but
        `_finish` adds the 998 line to the reply and puts the chat in the staff queue (fail safe, not silent).
        """
        for _ in range(2):
            try:
                result = self.llm.complete(
                    [{"role": "system", "content": prompts.RED_FLAG_SYSTEM},
                     {"role": "user", "content": f"<patient_message>{message}</patient_message>"}],
                    role="cheap", purpose="red_flag", json_mode=True, max_tokens=1000)
                data = parse_json(result.text)
                break
            except Exception as error:
                events.append(f"red_flag_model_failed:{type(error).__name__}")
        else:
            events.append("red_flag_screen_failed")
            return None
        if data.get("emergency") is True or str(data.get("emergency")).lower() == "true":
            return {"category": str(data.get("category") or "other"), "sources": ["llm"]}
        return None

    def _context(self, session: Session) -> dict:
        return {"pending_request": session.pending.get("intent"), "identity_verified": bool(session.verified_file),
                "offered_slots": [{"n": i + 1, "date": s["date"], "time": s["time"], "doctor": s["doctor"]}
                                  for i, s in enumerate(session.offered)],
                "last_assistant_reply": session.last_reply[-400:]}

    def _understand(self, message: str, session: Session, events: list) -> dict:
        context = self._context(session)
        if not self.llm:
            return keyword_brain.understand(message, context)
        try:
            result = self.llm.complete(
                [{"role": "system", "content": prompts.understand_system()},
                 {"role": "user", "content": prompts.understand_user(message, context)}],
                role="cheap", purpose="understand", json_mode=True, max_tokens=1000)
            return clean_understanding(parse_json(result.text), self.store)
        except Exception as error:
            events.append(f"understand_fallback:{type(error).__name__}")
            return keyword_brain.understand(message, context)

    def _route(self, session: Session, u: dict, tools: list) -> dict:
        intent = u["intent"]
        if intent == "provide_details" and session.pending.get("intent"):
            intent = session.pending["intent"]
        if intent == "availability" and session.offered and (u.get("choice") or u.get("time")):
            intent = session.pending["intent"] = "book"  # picked one of the free times shown: book it
        for key in ("file_number", "date_of_birth"):
            if u.get(key):
                session.identity[key] = u[key]
        if intent in NEEDS_IDENTITY | {"availability"}:
            if session.pending.get("intent") != intent:
                session.pending, session.offered = {"intent": intent}, []
            for key in ("doctor_id", "specialty", "date", "time", "part_of_day"):
                if u.get(key):
                    session.pending[key] = u[key]
            if u.get("doctor_id"):
                session.pending.pop("specialty", None)
        if intent == "clinic_info":
            found = knowledge.section(u.get("topic") or "", session.language)
            if found:
                tools.append("policy_lookup")
                return {"outcome": f"info:{u['topic']}", "intent": intent, "section": found["text"]}
        if intent == "insurance_check":
            tools.append("check_insurance")
            return {"outcome": "insurance_answered", "intent": intent,
                    "insurance": self.store.check_insurance(u.get("insurer"))}
        if intent == "availability":
            return self._slots(session, tools, intent, offer=False)
        if intent in NEEDS_IDENTITY:
            blocked = self._check_identity(session, tools)
            if blocked:
                return {**blocked, "intent": intent}
            return {**getattr(self, f"_{intent}")(session, u, tools), "intent": intent}
        if intent == "greeting":
            return {"outcome": "clarify", "intent": intent}
        session.unclear_turns += 1
        if session.unclear_turns >= 2:  # twice unclear in a row -> a person takes over
            self.desk.handover(session.session_id, session.verified_file, "reception")
            return {"outcome": "handover", "intent": intent}
        return {"outcome": "clarify", "intent": intent}

    def _check_identity(self, session: Session, tools: list) -> dict | None:
        """None when the patient is verified; otherwise the reply to send. Plain code, not the model."""
        if session.verified_file:
            return None
        file_number, birth = session.identity.get("file_number"), session.identity.get("date_of_birth")
        if not (file_number and birth):
            return {"outcome": "identity_request"}
        tools.append("verify_identity")
        session.identity = {}
        if self.store.verify_identity(file_number, birth):
            session.verified_file, session.failed_checks = file_number, 0
            return None
        session.failed_checks += 1
        if session.failed_checks >= MAX_IDENTITY_ATTEMPTS:
            session.pending = {}
            self.desk.handover(session.session_id, None, "identity")
            return {"outcome": "identity_locked"}
        return {"outcome": "identity_failed"}

    def _slots(self, session: Session, tools: list, intent: str, offer: bool = True) -> dict:
        p = session.pending
        if not (p.get("doctor_id") or p.get("specialty")):
            return {"outcome": "ask_doctor"}
        tools.append("find_slots")
        slots = self.store.find_slots(p.get("doctor_id"), p.get("specialty"), p.get("date"), p.get("part_of_day"))
        if not slots:
            return {"outcome": "no_slots"}
        session.offered = slots  # shown or offered: the patient may pick one next
        slots = [{**s, "display": templates.format_slot(s, session.language)} for s in slots]
        return {"outcome": "slots_offered" if offer else "slots_shown", "slots": slots}

    def _chosen_slot(self, session: Session, u: dict) -> dict | None:
        choice = u.get("choice")
        if session.offered and isinstance(choice, int) and 1 <= choice <= len(session.offered):
            return session.offered[choice - 1]
        if session.offered and u.get("time"):
            matches = [s for s in session.offered if s["time"] == u["time"]
                       and (not u.get("date") or s["date"] == u["date"])]
            return matches[0] if matches else None
        return None

    def _requested_slot(self, session: Session) -> dict | None:
        """The exact date + time the patient asked for, if one of the right doctors is free then."""
        p = session.pending
        if not (p.get("date") and p.get("time")):
            return None
        doctor_ids = [p["doctor_id"]] if p.get("doctor_id") else \
            [d for d, row in self.store.doctors.items() if row["specialty"] == p.get("specialty")]
        for doctor_id in doctor_ids:
            if self.store.is_free(doctor_id, p["date"], p["time"]):
                return self.store.slot_facts(doctor_id, p["date"], p["time"])
        return None

    def _done(self, session: Session, outcome: str, appointment: dict) -> dict:
        session.pending, session.offered = {}, []
        slot = self.store.slot_facts(appointment["doctor_id"], appointment["date"], appointment["time"])
        facts = {"outcome": outcome, "appointment": {**slot, "display": templates.format_slot(slot, session.language)}}
        if outcome != "cancelled":
            facts["reminder"] = "Arrive 15 minutes early with Emirates ID and insurance card."
        return facts

    def _book(self, session: Session, u: dict, tools: list) -> dict:
        slot = self._chosen_slot(session, u) or self._requested_slot(session)
        if slot:
            tools.append("book_slot")
            booked = self.store.book(session.verified_file, slot["doctor_id"], slot["date"], slot["time"])
            if booked["ok"]:
                return self._done(session, "booked", booked)
        return self._slots(session, tools, "book")

    def _reschedule(self, session: Session, u: dict, tools: list) -> dict:
        tools.append("get_appointments")
        upcoming = self.store.upcoming(session.verified_file)
        if not upcoming:
            session.pending = {}
            return {"outcome": "no_appointment"}
        appointment = upcoming[0]
        session.pending["doctor_id"] = appointment["doctor_id"]  # same doctor; a new doctor is a new booking
        slot = self._chosen_slot(session, u) or self._requested_slot(session)
        if slot:
            tools.append("reschedule")
            moved = self.store.reschedule(appointment["appointment_id"], slot["date"], slot["time"])
            if moved["ok"]:
                return self._done(session, "rescheduled", moved)
        return self._slots(session, tools, "reschedule")

    def _cancel(self, session: Session, u: dict, tools: list) -> dict:
        tools.append("get_appointments")
        upcoming = self.store.upcoming(session.verified_file)
        if not upcoming:
            session.pending = {}
            return {"outcome": "no_appointment"}
        tools.append("cancel_appointment")
        cancelled = self.store.cancel(upcoming[0]["appointment_id"])
        return self._done(session, "cancelled", cancelled)

    def _my_appointment(self, session: Session, u: dict, tools: list) -> dict:
        tools.append("get_appointments")
        session.pending = {}
        upcoming = self.store.upcoming(session.verified_file)
        if not upcoming:
            return {"outcome": "no_appointment"}
        first = upcoming[0]
        slot = self.store.slot_facts(first["doctor_id"], first["date"], first["time"])
        return {"outcome": "appointment_info",
                "appointment": {**slot, "display": templates.format_slot(slot, session.language)}}

    def _lab_status(self, session: Session, u: dict, tools: list) -> dict:
        tools.append("lab_status")
        session.pending = {}
        tests = [{**t, "expected_ready_display": templates.format_date(t["expected_ready_date"], session.language)}
                 for t in self.store.lab_status(session.verified_file)]
        return {"outcome": "lab_status", "tests": tests}

    def _callback(self, session: Session, u: dict, tools: list) -> dict:
        tools.append("request_callback")
        team = u.get("callback_team") if u.get("callback_team") in ("billing", "reception") else "reception"
        self.desk.handover(session.session_id, session.verified_file, team)
        session.pending = {}
        return {"outcome": "callback_logged", "team": team}

    def _write_reply(self, message: str, facts: dict, events: list) -> str:
        language, outcome = facts["language"], facts["outcome"]
        fallback = templates.render_admin(facts, language)
        if not self.llm or not (outcome in MODEL_WRITTEN or outcome.startswith("info:")):
            return fallback
        try:
            result = self.llm.complete(
                [{"role": "system", "content": prompts.reply_system(language)},
                 {"role": "user", "content": prompts.reply_user(message, facts)}],
                role=self.reply_role, purpose="reply", max_tokens=700)
            if result.text.strip():
                return result.text.strip()
            events.append("reply_empty:template_fallback")
        except Exception as error:
            events.append(f"reply_model_failed:{type(error).__name__}:template_fallback")
        return fallback

    def _check_output(self, session: Session, reply: str, outcome: str, events: list) -> tuple[str, str]:
        advice = safety.find_medical_advice(reply)
        leaks = safety.find_pii_leaks(reply, self.store.patients, session.verified_file, session.typed_text)
        if not (advice or leaks):
            return reply, outcome
        if advice:
            events.append("output_blocked:medical_advice:" + ",".join(advice))
        if leaks:
            events.append("output_blocked:other_patient_data")  # which patient is not logged
        self.desk.handover(session.session_id, session.verified_file, "review")
        return text(session.language, "blocked_reply"), "blocked_reply"

    def _finish(self, session: Session, reply: str, outcome: str, intent: str, tools: list, flag: dict | None,
                events: list, start: float) -> Turn:
        if not session.disclosed:  # AI disclosure on the first reply (after urgent advice, never before it)
            disclosure = text(session.language, "disclosure")
            reply = f"{reply}\n\n{disclosure}" if outcome == "emergency" else f"{disclosure}\n\n{reply}"
            session.disclosed = True
        if "red_flag_screen_failed" in events:  # the model screen could not run: say 998 anyway, tell staff
            reply = f"{reply}\n\n{text(session.language, 'unscreened_note')}"
            self.desk.handover(session.session_id, session.verified_file, "unscreened")
        if outcome not in ("clarify", "handover"):
            session.unclear_turns = 0
        session.last_reply = reply
        latency = int((time.perf_counter() - start) * 1000)
        self.desk.log(session.session_id, session.verified_file, language=session.language, intent=intent,
                      outcome=outcome, tools=tools, red_flag=(flag or {}).get("category"),
                      red_flag_sources=(flag or {}).get("sources"), guard_events=[e.split(":")[0] for e in events],
                      latency_ms=latency)
        return Turn(reply, outcome, intent, session.language, tools, flag, events, latency)


def clean_understanding(data: dict, store: ClinicStore) -> dict:
    """Check every field the model returned. Unknown values become None, so code never acts on a bad guess."""
    intent = data.get("intent") if data.get("intent") in INTENTS else "other"
    doctor_id = data.get("doctor_id") if data.get("doctor_id") in store.doctors else None
    specialty = data.get("specialty") if data.get("specialty") in {r["specialty"] for r in store.doctors.values()} \
        else None
    choice = data.get("choice")
    try:
        confidence = float(data.get("confidence", 0.8))
    except (TypeError, ValueError):
        confidence = 0.5
    file_number = data.get("file_number")
    file_number = file_number.upper().replace(" ", "-") if isinstance(file_number, str) else None
    if file_number and not file_number.startswith("NFC-"):
        file_number = f"NFC-{file_number[-5:]}" if file_number[-5:].isdigit() else None
    if confidence < LOW_CONFIDENCE and intent != "provide_details":
        intent = "other"
    return {
        "intent": intent,
        "topic": data.get("topic") if data.get("topic") in knowledge.TOPICS else None,
        "file_number": file_number,
        "date_of_birth": iso_or_none(data.get("date_of_birth")),
        "doctor_id": doctor_id,
        "specialty": None if doctor_id else specialty,
        "date": iso_or_none(data.get("date")),
        "time": hhmm_or_none(data.get("time")),
        "part_of_day": data.get("part_of_day") if data.get("part_of_day") in ("morning", "afternoon", "evening")
        else None,
        "choice": int(choice) if isinstance(choice, (int, float)) or (isinstance(choice, str) and choice.isdigit())
        else None,
        "insurer": data.get("insurer") if isinstance(data.get("insurer"), str) else None,
        "callback_team": data.get("callback_team"),
        "clinical_question": data.get("clinical_question") is True,
        "other_person": data.get("other_person") is True,
        "wants_human": data.get("wants_human") is True,
        "confidence": confidence,
    }
