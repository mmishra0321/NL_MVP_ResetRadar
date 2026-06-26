"""Reset session engine - candidate generation + Groq ranking + validation.

Pipeline (per architecture.md sections 6 + 12):

    1. Build Spotify /search field filters from the chosen scope.
       (Real mode lives in spotify_client.search_candidates; mock mode
       reads pre-curated entries from mock_data/mock_candidates.json.)
    2. Filter the candidate pool to the chosen scope(s).
    3. Deduplicate by spotify_track_id.
    4. Call llm_client.rank_and_explain(candidates) to get
       (score, why) per kept track.
    5. Validate every returned track_id against the candidate pool
       (drop hallucinated IDs - this is the slide 9 / pitfall 1 guard).
    6. Return the top N tracks (default 20) enriched with the original
       candidate metadata (title, artist, language, era, mood).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from app.config import settings
from app.llm_client import rank_and_explain
from app.spotify_client import search_candidates


log = logging.getLogger("reset_radar.reset_engine")


# ============================================================
# Query building (used by real-mode /search; mock mode bypasses it)
# ============================================================

def build_search_queries(
    *,
    scope_dimensions: list[str],
    scope_values: dict[str, list[str]],
    free_text_intent: str | None = None,
) -> list[str]:
    """Build Spotify /search query strings from the chosen scope.

    Example: scope_dimensions=["genre"], scope_values={"genre":["jazz","neo-soul"]}
    produces queries like ['genre:"jazz"', 'genre:"neo-soul"'].

    For real mode (R4+), each query is run as a paginated /search call.
    For mock mode (R2 default), this function is still called for
    structural symmetry, but its output drives only logging - the actual
    candidate retrieval reads `mock_candidates.json` filtered by scope.
    """
    queries: list[str] = []
    for dim in scope_dimensions:
        values = scope_values.get(dim) or []
        if not values:
            continue
        if dim == "genre":
            queries.extend(f'genre:"{v}"' for v in values)
        elif dim == "language":
            # Spotify has no language filter - in real mode this widens
            # to a generic /search with an artist/title hint and we rely
            # on llm_client.classify_language to tag results post-hoc.
            queries.extend(f'{v}' for v in values)
        elif dim == "era":
            queries.extend(
                f'year:{_year_range_for_era(v)}' for v in values if _year_range_for_era(v)
            )
        elif dim == "mood":
            # No `mood:` field on Spotify. Use a free-text proxy that
            # tends to surface tracks matching the mood vibe.
            queries.extend(f'{v}' for v in values)
    if free_text_intent:
        queries.append(free_text_intent)
    return queries


def _year_range_for_era(era: str) -> str | None:
    """Convert '1990s' -> '1990-1999' for the Spotify year filter."""
    era = (era or "").lower().strip()
    if not era.endswith("s") or not era[:-1].isdigit():
        return None
    start = int(era[:-1])
    return f"{start}-{start + 9}"


# ============================================================
# Candidate filtering + dedup
# ============================================================

def _filter_candidates_by_scope(
    candidates: Iterable[dict[str, Any]],
    scope_dimensions: list[str],
) -> list[dict[str, Any]]:
    """Keep candidates whose `scope_origin` is in the chosen dimensions.

    Mock-mode candidates are pre-tagged with `scope_origin`. Real-mode
    candidates won't have this field, in which case all candidates pass
    through (they're already filtered upstream by the /search queries).
    """
    scope_set = set(scope_dimensions)
    filtered: list[dict[str, Any]] = []
    for c in candidates:
        origin = c.get("scope_origin")
        if origin is None or origin in scope_set:
            filtered.append(c)
    return filtered


def _dedupe_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in candidates:
        tid = c.get("spotify_track_id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(c)
    return out


# ============================================================
# Hallucination guard (the slide-9 / pitfall-1 mitigation)
# ============================================================

def _validate_picks(
    *,
    candidate_pool: list[dict[str, Any]],
    llm_picks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop any LLM-picked track_id that wasn't in the candidate pool.

    Returns enriched picks (LLM fields + original candidate metadata
    merged in). Picks not found in the pool are silently dropped + a
    warning is logged - the route layer can compare lengths to detect
    excessive hallucination.
    """
    by_id: dict[str, dict[str, Any]] = {
        c["spotify_track_id"]: c for c in candidate_pool
    }
    out: list[dict[str, Any]] = []
    dropped: list[str] = []
    for pick in llm_picks:
        tid = pick.get("spotify_track_id")
        cand = by_id.get(tid) if tid else None
        if cand is None:
            dropped.append(str(tid))
            continue
        out.append({
            "spotify_track_id": tid,
            "title": cand.get("title", ""),
            "artist": cand.get("artist", ""),
            "album": cand.get("album"),
            "genres": list(cand.get("genres", [])),
            "language": cand.get("language"),
            "era": cand.get("era"),
            "mood": cand.get("mood"),
            "score": float(pick.get("score", 0.0)),
            "why": str(pick.get("why", "")),
        })
    if dropped:
        log.warning(
            "_validate_picks dropped %d hallucinated track_ids: %s",
            len(dropped), dropped[:5],
        )
    return out


# ============================================================
# End-to-end orchestrator (the main entry point)
# ============================================================

def generate_reset_playlist(
    *,
    user_id: str,
    scope_dimensions: list[str],
    free_text_intent: str | None,
    target_count: int | None = None,
    candidates_override: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a ranked + explained reset playlist for a user's chosen scope.

    Args:
        user_id: who the playlist is for (logged only - no persistence here)
        scope_dimensions: which axes to reset (usually exactly one)
        free_text_intent: optional natural-language steering ("upbeat", etc)
        target_count: how many tracks to return (default settings.reset_playlist_size)
        candidates_override: for tests - skip the search call and use this pool

    Returns:
        list of `target_count` enriched track dicts, ordered most to least
        recommended. Each dict has:
            spotify_track_id, title, artist, album, genres, language, era,
            mood, score (0..1), why (<=200 chars), order_index (0-based).

    Raises:
        ValueError on bad input (empty scope, empty candidate pool).
    """
    if not scope_dimensions:
        raise ValueError("scope_dimensions must contain at least one dimension.")

    target = target_count or settings.reset_playlist_size

    # ----- 1. Get the candidate pool -----
    if candidates_override is not None:
        pool = candidates_override
    elif settings.mock_mode:
        pool = search_candidates(
            scope_dimensions=scope_dimensions,
            scope_values={},
            free_text_intent=free_text_intent,
            target_pool_size=settings.max_candidates_from_search,
        )
    else:
        raise NotImplementedError(
            "Real-Spotify candidate generation lands in R4; "
            "set MOCK_MODE=true to use mock_candidates.json."
        )

    # ----- 2. Filter to chosen scope + 3. Dedupe -----
    pool = _filter_candidates_by_scope(pool, scope_dimensions)
    pool = _dedupe_candidates(pool)

    if not pool:
        raise ValueError(
            f"Empty candidate pool for scope={scope_dimensions}. "
            f"Check mock_candidates.json filtering."
        )

    # ----- 4. LLM rank + explain -----
    llm_picks = rank_and_explain(
        scope_dimensions=scope_dimensions,
        free_text_intent=free_text_intent,
        candidates=pool,
        target_count=target,
    )

    # ----- 5. Validate (drop hallucinated IDs) -----
    validated = _validate_picks(candidate_pool=pool, llm_picks=llm_picks)

    # ----- 6. Trim + stamp order_index -----
    sorted_picks = sorted(validated, key=lambda p: -p["score"])[:target]
    for idx, pick in enumerate(sorted_picks):
        pick["order_index"] = idx

    log.info(
        "reset playlist | user=%s scope=%s pool=%d picks=%d kept_after_validation=%d",
        user_id, scope_dimensions, len(pool), len(llm_picks), len(sorted_picks),
    )
    return sorted_picks


__all__ = [
    "build_search_queries",
    "generate_reset_playlist",
    "_filter_candidates_by_scope",
    "_dedupe_candidates",
    "_validate_picks",
]
