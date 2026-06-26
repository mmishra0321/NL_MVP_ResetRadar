"""Intent parser - free-form English to a typed Intent (LLM call #1).

Why an LLM and not a form: users say things like
    "energetic Spanish music, similar vibe to Rosalia but no Rosalia,
     things I'm unlikely to know"
which expresses 5 axes (mood, language, seed, exclude, novelty) in one
sentence. No form can capture that without a friction step the user won't
pay for.
"""
from __future__ import annotations

import logging
import re

from pydantic import ValidationError

from src.llm.client import GROQ_MODEL_REASONER, GroqError, chat_json
from src.schema import Intent

log = logging.getLogger("mvp.intent")


_SYSTEM_PROMPT = """You parse natural-language music discovery requests into a STRICT JSON object.

The user is talking to a Spotify discovery agent ("Sonar"). Extract these axes:
- mood: short adjectives like ["energetic", "melancholic", "uplifting"]
- languages: ISO 639-1 codes of song lyrics they want, e.g. ["es","ta","hi"]. Default [] if not stated.
- genres: ["indie pop", "lo-fi", "reggaeton"] (lowercased, full names)
- seed_artists: artist names mentioned as POSITIVE references
- seed_tracks: specific track titles mentioned as POSITIVE references
- exclude_artists: artists they explicitly do NOT want (e.g. "no Rosalia")
- exclude_genres: genres they explicitly do NOT want
- novelty_level: 0-10 integer. 0 = "music I already know", 10 = "deep cuts I'd never find". Tune from phrases like "haven't heard", "deep cuts", "fresh", "obscure", "comfort music", "old favourites".
- target_track_count: integer 5-50; default 20 if not stated
- activity_context: one of "workout", "study", "commute", "focus", "party", "chill", "sleep", null
- locale: BCP-47 like "en-IN" if user mentions a country/region, else null
- notes: any residual instruction not captured above (max 140 chars), or null

Output rules:
- Return ONLY a JSON object. No prose.
- Every field MUST be present, using [] or null where empty.
- Never invent artists or songs the user did not mention.
- If the request is not about music discovery at all, set notes="non_music_request" and leave other arrays empty.

Few-shot examples:

USER: "I want energetic Spanish music, similar vibe to Rosalia but no Rosalia, things I'm unlikely to know"
JSON: {"mood":["energetic"],"languages":["es"],"genres":[],"seed_artists":["Rosalia"],"seed_tracks":[],"exclude_artists":["Rosalia"],"exclude_genres":[],"novelty_level":9,"target_track_count":20,"activity_context":null,"locale":null,"notes":null}

USER: "soft instrumental stuff for late-night study, nothing with lyrics"
JSON: {"mood":["soft","calm"],"languages":[],"genres":["ambient","instrumental"],"seed_artists":[],"seed_tracks":[],"exclude_artists":[],"exclude_genres":["pop","rock"],"novelty_level":6,"target_track_count":20,"activity_context":"study","locale":null,"notes":"instrumental only"}

USER: "playlist for my morning run, like Imagine Dragons or Coldplay, 30 tracks"
JSON: {"mood":["energetic","uplifting"],"languages":[],"genres":[],"seed_artists":["Imagine Dragons","Coldplay"],"seed_tracks":[],"exclude_artists":[],"exclude_genres":[],"novelty_level":4,"target_track_count":30,"activity_context":"workout","locale":null,"notes":null}
"""


def _heuristic_fallback(text: str, novelty_hint: int | None = None) -> Intent:
    """Best-effort fallback when the LLM fails (network / 429 burnout)."""
    artists = re.findall(r"(?:like|by)\s+([A-Z][A-Za-z0-9 .'-]{1,40})", text)
    excluded = re.findall(r"(?:no|not|except|without)\s+([A-Z][A-Za-z0-9 .'-]{1,40})", text)
    novelty = novelty_hint if novelty_hint is not None else 7
    if any(w in text.lower() for w in ("comfort", "old favourites", "already love")):
        novelty = 2
    elif any(w in text.lower() for w in ("deep cut", "obscure", "never heard", "fresh")):
        novelty = 9
    return Intent(
        raw_text=text,
        seed_artists=[a.strip() for a in artists if a.strip()],
        exclude_artists=[a.strip() for a in excluded if a.strip()],
        novelty_level=novelty,
        notes="parsed via heuristic fallback (LLM unavailable)",
    )


def parse_intent(
    raw_text: str,
    *,
    novelty_override: int | None = None,
    activity_override: str | None = None,
    languages_override: list[str] | None = None,
    track_count_override: int | None = None,
) -> Intent:
    """Parse a user's free-text + UI control state into a typed Intent.

    UI override values (novelty slider, activity preset chips, language toggle,
    track count input) take precedence over what the LLM extracted from the
    raw text. This makes the controls feel direct - the user sees them win.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty intent text.")

    user_payload = f"USER: {text}\nJSON:"

    try:
        raw = chat_json(
            system=_SYSTEM_PROMPT,
            user=user_payload,
            model=GROQ_MODEL_REASONER,
            temperature=0.1,
            max_tokens=400,
        )
    except GroqError as exc:
        log.warning("Intent LLM call failed (%s); using heuristic fallback.", exc)
        intent = _heuristic_fallback(text, novelty_hint=novelty_override)
    else:
        raw.setdefault("raw_text", text)
        try:
            intent = Intent.model_validate(raw)
        except ValidationError as exc:
            log.warning("Intent validation failed (%s); using heuristic fallback.", exc)
            intent = _heuristic_fallback(text, novelty_hint=novelty_override)

    # UI overrides win over LLM extraction.
    if novelty_override is not None:
        intent.novelty_level = max(0, min(10, int(novelty_override)))
    if activity_override:
        intent.activity_context = activity_override
    if languages_override:
        intent.languages = list(dict.fromkeys(languages_override))
    if track_count_override:
        intent.target_track_count = max(5, min(50, int(track_count_override)))

    return intent


__all__ = ["parse_intent"]
