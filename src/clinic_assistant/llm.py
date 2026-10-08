"""The only module that talks to a language model.

- OpenRouterClient: real calls through the OpenAI-compatible SDK (OpenRouter).
- FakeLLM: a deterministic stand-in for tests, --dry-run and the offline demo. It is NOT a model:
  it answers with the keyword rules (keyword_brain.py) and the fixed templates (templates.py).

Every call is written to a traces file (JSON lines) with model, tokens, cost, latency and outcome.
The traces never contain the patient's message or the reply text (minimised logging).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import keyword_brain, safety, templates
from .config import EVALS_DIR, env, model_id


class LLMNotConfigured(RuntimeError):
    """Raised when OPENROUTER_API_KEY or a model ID is missing."""


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""


@dataclass
class Tracer:
    """Appends one JSON line per model call and keeps running totals per conversation."""

    _file_lock = threading.Lock()  # several evaluation workers may share one traces file

    path: Path = field(default_factory=lambda: Path(env("TRACES_PATH") or EVALS_DIR / "traces.jsonl"))
    context: dict = field(default_factory=dict)  # e.g. {"run_id": ..., "conversation_id": ...}
    totals: dict = field(default_factory=dict)  # conversation_id -> {"cost_usd", "tokens", "calls"}

    def log(self, purpose: str, result: LLMResult | None, outcome: str, model: str = "") -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            **self.context,
            "purpose": purpose,
            "model": result.model if result else model,
            "prompt_tokens": result.prompt_tokens if result else 0,
            "completion_tokens": result.completion_tokens if result else 0,
            "cost_usd": result.cost_usd if result else 0.0,
            "latency_ms": result.latency_ms if result else 0,
            "outcome": outcome,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        key = self.context.get("conversation_id", "-")
        total = self.totals.setdefault(key, {"cost_usd": 0.0, "tokens": 0, "calls": 0})
        total["cost_usd"] += record["cost_usd"]
        total["tokens"] += record["prompt_tokens"] + record["completion_tokens"]
        total["calls"] += 1

    def total_cost(self) -> float:
        return sum(t["cost_usd"] for t in self.totals.values())


class OpenRouterClient:
    def __init__(self, tracer: Tracer | None = None, role_override: str | None = None):
        from openai import OpenAI  # imported here so tests never need network setup

        key = env("OPENROUTER_API_KEY")
        if not key:
            raise LLMNotConfigured("OPENROUTER_API_KEY is not set (see .env.example)")
        self.client = OpenAI(api_key=key, base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                             timeout=60, max_retries=2)
        self.tracer = tracer or Tracer()
        self.role_override = role_override  # e.g. "cheap": every assistant call on MODEL_CHEAP (not the judge)
        self.offline = False

    def complete(self, messages: list[dict], role: str = "cheap", purpose: str = "",
                 json_mode: bool = False, max_tokens: int = 500, temperature: float = 0.0) -> LLMResult:
        role = self.role_override if (self.role_override and role != "judge") else role
        model = model_id(role)
        if not model:
            raise LLMNotConfigured(f"MODEL_{role.upper()} is not set")
        extra_body = {"usage": {"include": True}}  # OpenRouter returns the cost in usage
        # Reasoning models spend max_tokens on hidden "thinking" first; earlier projects lost JSON that way.
        effort = env("REASONING_EFFORT", "low")
        if effort != "default":
            extra_body["reasoning"] = {"effort": effort}
        kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                  "extra_body": extra_body}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as error:  # log failed calls too, then let the caller decide
            self.tracer.log(purpose, None, f"error: {type(error).__name__}", model)
            raise
        usage = response.usage
        extra = getattr(usage, "model_extra", None) or {}
        result = LLMResult(
            text=response.choices[0].message.content or "",
            model=response.model or model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=float(extra.get("cost") or getattr(usage, "cost", 0) or 0),
            latency_ms=int((time.perf_counter() - start) * 1000),
            finish_reason=response.choices[0].finish_reason or "",
        )
        # "length" = cut off at max_tokens: say so in the trace instead of hiding it.
        self.tracer.log(purpose, result, "truncated" if result.finish_reason == "length" else "ok")
        return result


TAG_RE = {name: re.compile(rf"<{name}>(.*?)</{name}>", re.DOTALL)
          for name in ("patient_message", "facts", "context")}


def tagged(text: str, name: str) -> str:
    found = TAG_RE[name].findall(text)
    return found[-1].strip() if found else ""


class FakeLLM:
    """Deterministic offline stand-in. Its traces say model='fake-offline'. Not a model, not results."""

    def __init__(self, tracer: Tracer | None = None):
        self.tracer = tracer or Tracer()
        self.offline = True

    def complete(self, messages: list[dict], role: str = "cheap", purpose: str = "",
                 json_mode: bool = False, max_tokens: int = 500, temperature: float = 0.0) -> LLMResult:
        user_part = messages[-1]["content"]
        message = tagged(user_part, "patient_message")
        if purpose == "red_flag":
            category = safety.pattern_red_flag(message)
            text = json.dumps({"emergency": bool(category), "category": category or "none", "reason": "keywords"})
        elif purpose == "understand":
            context = json.loads(tagged(user_part, "context") or "{}")
            text = json.dumps(keyword_brain.understand(message, context), ensure_ascii=False)
        elif purpose == "reply":
            facts = json.loads(tagged(user_part, "facts"))
            text = templates.render_admin(facts, facts["language"])
        elif purpose.startswith("judge"):
            text = json.dumps({"medical_advice": False, "tone": 3, "helpfulness": 3, "language_ok": True,
                               "reason": "fake judge"})
        elif purpose == "plain":
            text = "(offline placeholder reply)"
        else:
            text = "(offline placeholder)"
        prompt_tokens = sum(len(m["content"]) for m in messages) // 4  # rough size only; the fake costs nothing
        result = LLMResult(text=text, model="fake-offline", prompt_tokens=prompt_tokens,
                           completion_tokens=len(text) // 4)
        self.tracer.log(purpose, result, "ok")
        return result


def make_client(offline: bool | None = None, tracer: Tracer | None = None, role_override: str | None = None):
    """Real client when a key exists (or offline=False), otherwise the FakeLLM."""
    if offline is None:
        offline = not env("OPENROUTER_API_KEY")
    return FakeLLM(tracer) if offline else OpenRouterClient(tracer, role_override)


def parse_json(text: str) -> dict:
    """Parse a JSON object even if the model wrapped it in ```json fences or added words around it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    return json.loads(match.group(0))
