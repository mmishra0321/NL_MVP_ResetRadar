"""Reset session engine - candidate generation + Groq ranking.

R0 scaffold: function signatures + docstrings only. Real implementation
lands in R2.

Pipeline (per architecture.md section 12):
    1. Build Spotify /search field filters from the chosen scope
    2. Paginate /search (or read mock_candidates.json in mock mode)
    3. Deduplicate the pool by spotify_track_id
    4. Call llm_client.rank_and_explain(candidates) to get
       (score, why) per kept track
    5. Validate every returned track_id against the candidate pool
       (drop hallucinated IDs)
    6. Return top N tracks with explanations
"""
from __future__ import annotations

from typing import Any


def build_search_queries(
    *,
    scope_dimensions: list[str],
    scope_values: dict[str, list[str]],
    free_text_intent: str | None = None,
) -> list[str]:
    """Build a list of Spotify /search query strings from the chosen scope.

    R0 stub - implementation in R2.
    """
    raise NotImplementedError("build_search_queries lands in R2.")


def generate_reset_playlist(
    *,
    user_id: str,
    scope_dimensions: list[str],
    free_text_intent: str | None,
    target_count: int = 20,
) -> list[dict[str, Any]]:
    """End-to-end: scope -> candidates -> ranked + explained playlist.

    R0 stub - implementation in R2. Returns a list of track dicts shaped:
        {
            "spotify_track_id": str,
            "title": str,
            "artist": str,
            "album": str | None,
            "score": float,
            "why": str,
            "order_index": int,
        }
    """
    raise NotImplementedError("generate_reset_playlist lands in R2.")


def _validate_picks(
    *,
    candidate_pool: list[dict[str, Any]],
    llm_picks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop any LLM-picked track_id that wasn't in the candidate pool.

    This is the hallucination-prevention guardrail referenced in
    deck slide 9 (pitfall 1). R0 stub - implementation in R2.
    """
    raise NotImplementedError("_validate_picks lands in R2.")


__all__ = [
    "build_search_queries",
    "generate_reset_playlist",
    "_validate_picks",
]
