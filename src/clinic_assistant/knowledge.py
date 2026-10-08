"""The clinic's own documents (EN/AR/FR), split into sections by topic.

Retrieval is deliberately simple: the intent step names a topic (e.g. "preparation") and we return that
section in the patient's language. With 11 short sections, a topic lookup is easier to test than embeddings,
and the model only ever sees the clinic's approved wording. Each file has the same section keys:

    ## hours: Opening hours
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR

TOPICS = ["hours", "location", "what_to_bring", "preparation", "insurance_list", "preapproval_documents",
          "billing", "booking_policy", "lab_results", "contact", "privacy"]
SECTION_RE = re.compile(r"^## (\w+): (.+)$", re.MULTILINE)


@lru_cache(maxsize=8)
def load_sections(language: str, data_dir: Path = DATA_DIR) -> dict[str, dict]:
    """{topic: {"title": ..., "text": ...}} for one language."""
    raw = (data_dir / f"clinic_docs_{language}.md").read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(raw))
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        sections[match.group(1)] = {"title": match.group(2).strip(), "text": raw[match.end():end].strip()}
    return sections


def section(topic: str, language: str) -> dict | None:
    return load_sections(language if language in ("ar", "en", "fr") else "en").get(topic)


def public_text() -> str:
    """All clinic documents in all languages: repeating them is never a privacy leak."""
    return "\n".join(s["text"] for lang in ("ar", "en", "fr") for s in load_sections(lang).values())
