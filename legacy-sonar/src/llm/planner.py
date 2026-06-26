"""Query planner - Intent -> Spotify Web API blueprint (LLM call #2).

Turns a structured Intent into a QueryPlan: which endpoints to call (search
vs recommendations vs both), what raw search strings to use, what audio
feature targets to set, and what artists to exclude. The plan is what the
Spotify client (real or mock) consumes next.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from src.llm.client import GROQ_MODEL_REASONER, GroqError, chat_json
from src.schema import Intent, QueryPlan

log = logging.getLogger("mvp.planner")


_SYSTEM_PROMPT = """You are a query planner for Spotify Sonar. Convert the user's parsed Intent
into a strict JSON QueryPlan describing which Spotify endpoints to call.

Output fields:
- endpoints: subset of ["search","recommendations"]. Use both unless the intent is one-track-narrow.
- search_queries: 1-3 raw Spotify search strings (use Spotify operators: artist:"X", genre:"Y", year:2020-2024).
- seed_artist_names: subset of intent.seed_artists to seed Recommendations.
- target_audio_features: floats 0.0-1.0 for target_energy, target_danceability, target_valence,
  target_acousticness; plus min_popularity / max_popularity (0-100). Choose based on mood + novelty.
  HIGH novelty (>=8) -> min_popularity around 15, max_popularity around 55 (less mainstream).
  LOW novelty (<=3) -> min_popularity 60+ (familiar / charted).
- exclude_artist_names: copy from intent.exclude_artists.
- rationale: ONE sentence, <140 chars, plain English, used in the deck.

Output rules:
- Return ONLY a JSON object. No prose.
- Every field present, using [] or {} where empty.
- Never invent artists not present in the intent.
- If intent.notes == "non_music_request", return endpoints=[] and rationale="non-music request; skipping Spotify".
"""


_FALLBACK_PLAN_RATIONALE = "Heuristic plan: LLM unavailable, used intent fields directly."


def _heuristic_plan(intent: Intent) -> QueryPlan:
    """No-LLM fallback so the demo never hard-fails on Groq outages."""
    search_q: list[str] = []
    if intent.seed_artists:
        search_q.append(f'artist:"{intent.seed_artists[0]}"')
    for g in intent.genres[:1]:
        search_q.append(f'genre:"{g}"')
    if intent.mood:
        search_q.append(" ".join(intent.mood[:2]))

    novelty = intent.novelty_level
    if novelty >= 8:
        min_pop, max_pop = 15, 55
    elif novelty <= 3:
        min_pop, max_pop = 60, 100
    else:
        min_pop, max_pop = 25, 80

    mood_set = {m.lower() for m in intent.mood}
    energy = 0.85 if "energetic" in mood_set else 0.55 if "calm" in mood_set or "soft" in mood_set else 0.7
    danceability = 0.8 if intent.activity_context in {"workout", "party"} else 0.55
    valence = 0.7 if "uplifting" in mood_set else 0.4 if "melancholic" in mood_set else 0.55
    acousticness = 0.7 if intent.activity_context == "sleep" or "instrumental" in (intent.notes or "") else 0.3

    return QueryPlan(
        endpoints=["search"] if not intent.seed_artists else ["search", "recommendations"],
        search_queries=search_q[:3] or ["popular"],
        seed_artist_names=intent.seed_artists[:3],
        target_audio_features={
            "target_energy": energy,
            "target_danceability": danceability,
            "target_valence": valence,
            "target_acousticness": acousticness,
            "min_popularity": float(min_pop),
            "max_popularity": float(max_pop),
        },
        exclude_artist_names=intent.exclude_artists,
        rationale=_FALLBACK_PLAN_RATIONALE,
    )


def plan_queries(intent: Intent) -> QueryPlan:
    """Run the LLM planner. Falls back to a heuristic plan if Groq fails."""
    if intent.notes == "non_music_request":
        return QueryPlan(rationale="non-music request; skipping Spotify")

    user_payload = "INTENT_JSON:\n" + intent.model_dump_json(indent=0)

    try:
        raw = chat_json(
            system=_SYSTEM_PROMPT,
            user=user_payload,
            model=GROQ_MODEL_REASONER,
            temperature=0.2,
            max_tokens=500,
        )
    except GroqError as exc:
        log.warning("Planner LLM call failed (%s); using heuristic plan.", exc)
        return _heuristic_plan(intent)

    try:
        plan = QueryPlan.model_validate(raw)
    except ValidationError as exc:
        log.warning("Planner validation failed (%s); using heuristic plan.", exc)
        return _heuristic_plan(intent)

    if not plan.search_queries and not plan.seed_artist_names:
        # LLM gave us nothing actionable - fall back
        log.info("Planner returned empty plan; falling back to heuristic.")
        return _heuristic_plan(intent)

    return plan


__all__ = ["plan_queries"]
