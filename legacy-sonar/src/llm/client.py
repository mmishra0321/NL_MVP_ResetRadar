"""Shared Groq client for the MVP.

Mirrors `01-ai-review-engine/src/pipeline/groq_client.py`: process-wide
throttle (to stay within Groq's free TPM), exponential-backoff retries on
429/5xx, and a JSON-mode helper so every LLM call returns a clean dict.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from groq import Groq
from tenacity import (
    before_sleep_log, retry, retry_if_exception_type,
    stop_after_attempt, wait_exponential,
)

from src.config import (
    GROQ_API_KEY, GROQ_MODEL_FAST, GROQ_MODEL_REASONER,
)

log = logging.getLogger("mvp.groq")

# ----- Process-wide rate limiter -----
# Groq's free tier is primarily TPM (tokens per minute) limited. Keeping
# requests at least N seconds apart smooths out the rate.
_MIN_INTERVAL_SECONDS = 6.5
_lock = threading.Lock()
_last_call_at: float = 0.0


def _throttle() -> None:
    global _last_call_at
    with _lock:
        delta = time.monotonic() - _last_call_at
        if delta < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - delta)
        _last_call_at = time.monotonic()


class GroqError(RuntimeError):
    """Wraps any error from the Groq SDK in a single type our callers can catch."""


def _get_client() -> Groq:
    if not GROQ_API_KEY:
        raise GroqError(
            "GROQ_API_KEY is not set. Add it to 02-mvp/.env (or your shell env)."
        )
    return Groq(api_key=GROQ_API_KEY)


@retry(
    retry=retry_if_exception_type(GroqError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def chat_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """Run a chat completion in JSON mode and return the parsed dict.

    Use this for every structured LLM call in the MVP. If the model returns
    invalid JSON, this raises GroqError and tenacity retries.
    """
    _throttle()
    client = _get_client()
    model = model or GROQ_MODEL_REASONER
    try:
        completion = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except Exception as exc:                                       # noqa: BLE001
        raise GroqError(f"Groq chat call failed: {exc}") from exc

    content = (completion.choices[0].message.content or "").strip()
    if not content:
        raise GroqError("Groq returned an empty response.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise GroqError(
            f"Groq returned non-JSON content. First 300 chars: {content[:300]!r}"
        ) from exc


def ping() -> str:
    """Smoke-test the connection. Returns the model's free-text reply."""
    _throttle()
    client = _get_client()
    completion = client.chat.completions.create(
        model=GROQ_MODEL_FAST,
        max_tokens=20,
        messages=[
            {"role": "system", "content": "Reply with the single word PONG."},
            {"role": "user", "content": "ping"},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


__all__ = ["chat_json", "ping", "GroqError", "GROQ_MODEL_REASONER", "GROQ_MODEL_FAST"]
