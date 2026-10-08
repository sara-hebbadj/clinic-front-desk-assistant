"""Gradio demo: a WhatsApp-style patient chat and a staff console (red-flag alerts, handover queue, audit log).

Run:  python app/app.py     then open http://127.0.0.1:7860

- With OPENROUTER_API_KEY and MODEL_CHEAP set, the assistant runs live on MODEL_CHEAP.
- Without them it runs in demo mode (live AI off): keyword rules and fixed templates, not a model.
  The red-flag patterns, identity check, output check and staff console are the real code in both modes.
- Each browser session may send DEMO_MESSAGE_LIMIT messages (default 20).
Fictional clinic, synthetic patients. Not for clinical use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run without installing the package

import gradio as gr  # noqa: E402

from clinic_assistant.assistant import FrontDeskAssistant, Session  # noqa: E402
from clinic_assistant.clinic import ClinicStore  # noqa: E402
from clinic_assistant.config import demo_message_limit, env, runtime_dir  # noqa: E402
from clinic_assistant.llm import make_client  # noqa: E402
from clinic_assistant.staff import StaffDesk  # noqa: E402

# Live only when both the key and the model ID are set, so a half-configured Space still starts.
OFFLINE = not (env("OPENROUTER_API_KEY") and env("MODEL_CHEAP"))
LIMIT = demo_message_limit()
store = ClinicStore()
desk = StaffDesk(folder=runtime_dir())
assistant = FrontDeskAssistant(llm=make_client(offline=OFFLINE, role_override="cheap"), store=store, desk=desk)

BANNER = (
    "### Sahara Demo Family Clinic (fictional): AI front-desk assistant, admin only\n"
    "You are chatting with an **AI assistant**, not a person. It handles bookings, opening hours, directions, "
    "insurance and billing questions. **It does not give medical advice.** In an emergency in the UAE call "
    "**998** (ambulance) or **999** (police). Synthetic patients only; a portfolio demo, **not for clinical use**.\n\n"
    + ("**Demo mode — live AI is off; add OPENROUTER_API_KEY in Space settings to enable** (plus a "
       "`MODEL_CHEAP` variable). Replies now come from keyword rules and fixed templates."
       if OFFLINE else f"Live AI: `{env('MODEL_CHEAP')}`, {LIMIT} messages per session.")
)
EXAMPLES = [
    "أبي أغير موعدي إلى يوم الاثنين 19 أكتوبر الساعة 10:00، رقم الملف NFC-10032 وتاريخ الميلاد 11/05/2018",
    "Quels documents faut-il pour l'accord préalable de l'assurance ?",
    "I need to cancel my appointment, my husband has crushing chest pain right now",
    "How many paracetamol tablets can I give my 5-year-old?",
    "What time is my sister's appointment tomorrow?",
]


def demo_patients() -> list[list]:
    """A few synthetic patients to try (file number + date of birth)."""
    rows = []
    for file_number in ("NFC-10002", "NFC-10012", "NFC-10032", "NFC-10011", "NFC-10050"):
        patient = store.patients[file_number]
        upcoming = store.upcoming(file_number)
        rows.append([file_number, patient["date_of_birth"], patient["full_name"],
                     f"{upcoming[0]['date']} {upcoming[0]['time']}" if upcoming else "-"])
    return rows


def send(message: str, history: list, session: Session | None, count: int):
    session = session or Session()
    history = history or []
    if not message.strip():
        return "", history, session, count, ""
    if count >= LIMIT:
        history.append({"role": "assistant", "content": f"Demo limit reached ({LIMIT} messages). Refresh to restart."})
        return "", history, session, count, ""
    turn = assistant.handle(session, message)
    history += [{"role": "user", "content": message}, {"role": "assistant", "content": turn.reply}]
    trace = {"outcome": turn.outcome, "intent": turn.intent, "tools": turn.tool_calls, "red_flag": turn.red_flag,
             "guard_events": turn.guard_events, "latency_ms": turn.latency_ms}
    return "", history, session, count + 1, json.dumps(trace, ensure_ascii=False, indent=1)


def alerts_rows() -> list[list]:
    return [[a["alert_id"], a["ts"][11:19], a["category"], ", ".join(a["sources"]), a["session"], a["status"]]
            for a in reversed(desk.alerts)]


def queue_rows() -> list[list]:
    return [[q["item_id"], q["ts"][11:19], q["kind"], q["session"], q["file_hash"] or "-", q["status"]]
            for q in reversed(desk.queue)]


def audit_rows() -> list[list]:
    return [[a["ts"][11:19], a["session"], a["language"], a["intent"], a["outcome"], ", ".join(a["tools"]),
             a["red_flag"] or "", a["file_hash"] or "-"] for a in reversed(desk.audit[-30:])]


def refresh():
    return alerts_rows(), queue_rows(), audit_rows()


def reset_bookings():
    store.reset()
    return "Bookings reset to the synthetic starting data."


with gr.Blocks(title="Clinic front-desk assistant") as demo:
    session_state = gr.State(None)
    count_state = gr.State(0)
    gr.Markdown(BANNER)
    with gr.Tab("Patient chat"):
        chat = gr.Chatbot(height=430, label="WhatsApp-style chat")
        box = gr.Textbox(placeholder="Write in Arabic, English or French...", label="Your message")
        gr.Examples(EXAMPLES, inputs=box)
        with gr.Accordion("Synthetic patients to try (file number + date of birth)", open=False):
            gr.Dataframe(demo_patients(), headers=["file_number", "date_of_birth", "name", "next appointment"])
        with gr.Accordion("What the assistant did (last message)", open=False):
            trace = gr.Code(language="json", label="trace")
    with gr.Tab("Staff console"):
        gr.Markdown("Red-flag alerts and the handover queue. The audit log keeps no message text: only the "
                    "session ID, a salted hash of the file number, the intent, the outcome and the tools used.")
        refresh_btn = gr.Button("Refresh", variant="primary")
        gr.Markdown("**Red-flag alerts** (in a real clinic these page the duty nurse)")
        alerts = gr.Dataframe(alerts_rows, headers=["alert", "time (UTC)", "category", "detected by", "session",
                                                    "status"])
        gr.Markdown("**Handover queue** (nurse call-backs, reception, billing, blocked replies to review)")
        queue = gr.Dataframe(queue_rows, headers=["item", "time (UTC)", "kind", "session", "file hash", "status"])
        gr.Markdown("**Audit log** (last 30 events, minimised)")
        audit = gr.Dataframe(audit_rows, headers=["time (UTC)", "session", "lang", "intent", "outcome", "tools",
                                                  "red flag", "file hash"])
        reset_note = gr.Markdown()
        gr.Button("Reset demo bookings").click(reset_bookings, outputs=reset_note)

    box.submit(send, [box, chat, session_state, count_state], [box, chat, session_state, count_state, trace])
    refresh_btn.click(refresh, outputs=[alerts, queue, audit])


if __name__ == "__main__":
    demo.launch()
