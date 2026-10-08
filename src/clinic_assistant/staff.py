"""What the clinic staff see: red-flag alerts, the handover queue, and a minimised audit log.

Data minimisation is the point of this file. No record here contains the patient's message, the reply,
a symptom description, a name or a raw file number. Records hold a random session ID, a salted hash of the
file number (if verified), the alert category and what the assistant did. Staff open the chat itself to
read the conversation; the log only proves what happened and when.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .safety import hash_id


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class StaffDesk:
    folder: Path | None = None  # None = keep in memory only (tests, evaluation)
    alerts: list = field(default_factory=list)
    queue: list = field(default_factory=list)
    audit: list = field(default_factory=list)

    def _write(self, name: str, record: dict) -> None:
        if self.folder:
            self.folder.mkdir(parents=True, exist_ok=True)
            with (self.folder / name).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def alert(self, session_id: str, file_number: str | None, category: str, sources: list[str]) -> dict:
        """A possible emergency. In a real clinic this would page the duty nurse (see docs/governance.md)."""
        record = {"alert_id": f"ALERT-{len(self.alerts) + 1:04d}", "ts": now(), "session": session_id,
                  "file_hash": hash_id(file_number), "category": category, "sources": sources, "status": "open"}
        self.alerts.append(record)
        self._write("alerts.jsonl", record)
        return record

    def handover(self, session_id: str, file_number: str | None, kind: str) -> dict:
        """kind: nurse, reception, billing, identity, review (blocked reply), emergency_followup."""
        record = {"item_id": f"Q-{len(self.queue) + 1:04d}", "ts": now(), "session": session_id,
                  "file_hash": hash_id(file_number), "kind": kind, "status": "open"}
        self.queue.append(record)
        self._write("handover_queue.jsonl", record)
        return record

    def log(self, session_id: str, file_number: str | None, **event) -> dict:
        record = {"ts": now(), "session": session_id, "file_hash": hash_id(file_number), **event}
        self.audit.append(record)
        self._write("audit_log.jsonl", record)
        return record
