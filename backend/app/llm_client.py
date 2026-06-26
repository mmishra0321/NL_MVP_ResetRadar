"""Groq LLM client - the single AI surface for the Reset Radar backend.

Carried over from `legacy-sonar/src/llm/client.py` (the throttled Groq
wrapper with `tenacity` retry + JSON mode helper) and extended with
three Reset-Radar-specific methods that are filled in across R1-R4:

- `classify_language(...)` - replaces Spotify's missing language field
- `classify_mood(...)` - replaces Spotify's removed `/audio-features`
- `rank_and_explain(...)` - per-track ranking + one-line "why"

These three method bodies are deliberate stubs in R0; real prompts +
parsing land in R1 (language/mood) and R2 (rank_and_explain).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from groq import Groq
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


log = logging.getLogger("reset_radar.llm")


# ============================================================
# Process-wide rate limiter
# Groq's free tier is primarily TPM (tokens per minute) limited.
# Keeping requests at least N seconds apart smooths out the rate.
# ============================================================

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
    if not settings.groq_api_key:
        raise GroqError(
            "GROQ_API_KEY is not set. Add it to 02-mvp/backend/.env "
            "(or to your shell environment)."
        )
    return Groq(api_key=settings.groq_api_key)


# ============================================================
# Core chat_json helper - all structured LLM calls go through this
# ============================================================

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

    Use this for every structured LLM call in the backend. If the model
    returns invalid JSON, this raises GroqError and tenacity retries.
    """
    _throttle()
    client = _get_client()
    model = model or settings.groq_model_reasoner
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
        model=settings.groq_model_fast,
        max_tokens=20,
        messages=[
            {"role": "system", "content": "Reply with the single word PONG."},
            {"role": "user", "content": "ping"},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


# ============================================================
# Reset Radar-specific LLM operations (stubs - real impls in R1, R2, R4)
# ============================================================

def classify_language(
    *,
    track_title: str,
    artist_name: str,
    genres: list[str] | None = None,
) -> str:
    """Return an ISO 639-1 language code for the track.

    Replaces Spotify's missing language field. Reset Radar treats
    language as a first-class diversity dimension, so this function's
    accuracy directly affects the detection signal.

    Real implementation lands in R1 (Detection · mock-first).
    Returns "en" as a placeholder so R0 doesn't crash if a caller hits
    this prematurely.
    """
    raise NotImplementedError(
        "classify_language is implemented in R1; "
        "do not call it in R0 scaffold tests."
    )


def classify_mood(
    *,
    track_title: str,
    artist_name: str,
    genres: list[str] | None = None,
    album: str | None = None,
) -> str:
    """Return a mood label for the track.

    Replaces Spotify's removed /audio-features endpoint. Treated as an
    approximation - mood is the lowest-weight dimension in detection.

    Real implementation lands in R1 (Detection · mock-first).
    """
    raise NotImplementedError(
        "classify_mood is implemented in R1; "
        "do not call it in R0 scaffold tests."
    )


def rank_and_explain(
    *,
    scope_dimensions: list[str],
    free_text_intent: str | None,
    candidates: list[dict[str, Any]],
    target_count: int = 20,
) -> list[dict[str, Any]]:
    """Rank the candidate pool and write a one-line `why` per kept track.

    Returns a list of `target_count` items, each shaped:
        {
            "spotify_track_id": str,
            "score": float (0-1),
            "why": str (max 160 chars),
        }

    Real implementation lands in R2 (Reset engine · mock candidates).
    """
    raise NotImplementedError(
        "rank_and_explain is implemented in R2; "
        "do not call it in R0 scaffold tests."
    )


__all__ = [
    "chat_json",
    "ping",
    "classify_language",
    "classify_mood",
    "rank_and_explain",
    "GroqError",
]
