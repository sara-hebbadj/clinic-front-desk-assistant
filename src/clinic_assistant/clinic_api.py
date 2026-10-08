"""A small FastAPI mock of the clinic's booking system, over the same ClinicStore the assistant uses.

Run:  uvicorn clinic_assistant.clinic_api:app --port 8002     then open http://127.0.0.1:8002/docs

Every endpoint that touches a patient's file asks for the file number AND the date of birth again, so the
API itself refuses another patient's data even if a caller (or a future agent) skips the chat's check.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .clinic import ClinicStore

app = FastAPI(title="Sahara Demo Family Clinic (fictional) - mock booking API")
store = ClinicStore()


class Identity(BaseModel):
    file_number: str
    date_of_birth: str


class BookRequest(Identity):
    doctor_id: str
    date: str
    time: str


class MoveRequest(Identity):
    date: str
    time: str


def require_identity(file_number: str, date_of_birth: str) -> None:
    if not store.verify_identity(file_number, date_of_birth):
        raise HTTPException(status_code=403, detail="file number and date of birth do not match")


def own_appointment(appointment_id: str, file_number: str) -> None:
    if not any(a["appointment_id"] == appointment_id for a in store.upcoming(file_number)):
        raise HTTPException(status_code=404, detail="no such upcoming appointment on this file")


@app.get("/doctors")
def doctors() -> list[dict]:
    return [{k: v for k, v in d.items() if k != "schedule"} for d in store.doctors.values()]


@app.get("/slots")
def slots(doctor_id: str | None = None, specialty: str | None = None, date: str | None = None,
          part: str | None = None) -> list[dict]:
    return store.find_slots(doctor_id, specialty, date, part, limit=10)


@app.post("/identity/verify")
def verify(body: Identity) -> dict:
    return {"verified": store.verify_identity(body.file_number, body.date_of_birth)}


@app.post("/appointments")
def book(body: BookRequest) -> dict:
    require_identity(body.file_number, body.date_of_birth)
    result = store.book(body.file_number, body.doctor_id, body.date, body.time)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@app.patch("/appointments/{appointment_id}")
def reschedule(appointment_id: str, body: MoveRequest) -> dict:
    require_identity(body.file_number, body.date_of_birth)
    own_appointment(appointment_id, body.file_number)
    result = store.reschedule(appointment_id, body.date, body.time)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@app.delete("/appointments/{appointment_id}")
def cancel(appointment_id: str, file_number: str, date_of_birth: str) -> dict:
    require_identity(file_number, date_of_birth)
    own_appointment(appointment_id, file_number)
    return store.cancel(appointment_id)


@app.get("/lab-status/{file_number}")
def lab_status(file_number: str, date_of_birth: str) -> list[dict]:
    """Ready or not, never a value: the store has no result values at all."""
    require_identity(file_number, date_of_birth)
    return store.lab_status(file_number)


@app.get("/insurance/{name}")
def insurance(name: str) -> dict:
    return store.check_insurance(name)
