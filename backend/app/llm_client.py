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


_RANK_SYSTEM_PROMPT = """\
You are Reset Radar's track-ranking assistant. The user is a Spotify
Premium listener whose listening has narrowed onto one dimension; they
have explicitly chosen ONE reset SCOPE (genre / language / era / mood)
to step outside their current pattern.

You will receive:
- the chosen scope dimensions (most commonly a single one)
- an optional free-text intent describing the user's preference
- a candidate pool of tracks (already filtered by scope on the backend)

You MUST:
1. Pick exactly `target_count` tracks from the pool, ordered most to least
   recommended.
2. Use ONLY `spotify_track_id` values that appear in the candidate pool.
   Do NOT invent IDs or use any external knowledge of Spotify catalog
   identifiers - hallucinated IDs are dropped by a downstream guard and
   would waste a slot.
3. For each pick, write a `why` string (<= 160 characters) that:
   - is written directly to the user (second person, "you")
   - references the chosen reset scope by name
   - explains why this track is a good bridge from where the user is
     stuck to something new (NOT a marketing pitch; honest framing)
   - never mentions "AI", "LLM", "Groq", or implementation details

Return JSON of exactly this shape:
{
  "picks": [
    {"spotify_track_id": "<id from pool>", "score": <float 0..1>, "why": "<<=160 chars>"},
    ...
  ]
}

Pick exactly `target_count` items. Score must be in [0, 1] reflecting
how strong a recommendation this is (1 = best fit for this reset).
"""


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

    Hallucination guard: the caller (`reset_engine._validate_picks`)
    drops any track_id not in the candidate pool. This function does NOT
    enforce that on its own - the system prompt asks the LLM to comply,
    and the guard catches the (rare) failures.
    """
    if not candidates:
        raise ValueError("rank_and_explain called with empty candidate pool.")

    # Compact candidate dicts for the prompt - the LLM only needs the
    # fields it can reason about (title, artist, genres, language, era,
    # mood). The spotify_track_id is the join key it MUST echo back.
    compact = [
        {
            "spotify_track_id": c["spotify_track_id"],
            "title": c["title"],
            "artist": c["artist"],
            "genres": c.get("genres", []),
            "language": c.get("language"),
            "era": c.get("era"),
            "mood": c.get("mood"),
        }
        for c in candidates
    ]

    user_payload = {
        "scope_dimensions": scope_dimensions,
        "free_text_intent": free_text_intent or "",
        "target_count": target_count,
        "candidates": compact,
    }
    user_msg = json.dumps(user_payload, ensure_ascii=False)

    # Heuristic max_tokens: 20 picks * ~200 tokens/pick (id + score + why
    # + JSON overhead) ≈ 4000. Round up to give headroom.
    payload = chat_json(
        system=_RANK_SYSTEM_PROMPT,
        user=user_msg,
        model=settings.groq_model_reasoner,
        temperature=0.3,
        max_tokens=4096,
    )

    picks = payload.get("picks") if isinstance(payload, dict) else None
    if not isinstance(picks, list):
        raise GroqError(
            f"rank_and_explain response missing 'picks' list; got {payload!r}"
        )

    normalised: list[dict[str, Any]] = []
    for entry in picks:
        if not isinstance(entry, dict):
            continue
        tid = entry.get("spotify_track_id")
        if not isinstance(tid, str) or not tid:
            continue
        score = float(entry.get("score", 0.5))
        score = max(0.0, min(1.0, score))
        why = str(entry.get("why", ""))[:200]
        normalised.append({
            "spotify_track_id": tid,
            "score": score,
            "why": why,
        })

    return normalised


__all__ = [
    "chat_json",
    "ping",
    "classify_language",
    "classify_mood",
    "rank_and_explain",
    "GroqError",
]
