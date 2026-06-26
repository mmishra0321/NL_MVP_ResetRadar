"""End-to-end orchestrator: raw text -> Playlist.

Single entry point used by both the Streamlit UI and the smoke-test script.
Wraps the four phases (intent parse, planner, Spotify fetch, reasoner) and
returns one validated Playlist (with timing + provenance metadata).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.llm.intent import parse_intent
from src.llm.planner import plan_queries
from src.llm.reasoner import rank_and_explain
from src.schema import Intent, Playlist
from src.spotify.client import SpotifyClient, get_spotify_client

log = logging.getLogger("mvp.pipeline")


def generate_playlist(
    raw_text: str,
    *,
    novelty: int | None = None,
    activity: str | None = None,
    languages: list[str] | None = None,
    track_count: int | None = None,
    spotify_client: SpotifyClient | None = None,
) -> Playlist:
    """Run the full Sonar pipeline. Returns a Playlist even on partial failures
    (the reasoner has its own heuristic fallback, and the planner's too).
    """
    started = time.monotonic()

    intent = parse_intent(
        raw_text,
        novelty_override=novelty,
        activity_override=activity,
        languages_override=languages,
        track_count_override=track_count,
    )
    log.info("Intent parsed: novelty=%d langs=%s mood=%s seeds=%s",
             intent.novelty_level, intent.languages, intent.mood, intent.seed_artists)

    plan = plan_queries(intent)
    log.info("Plan: endpoints=%s queries=%s seeds=%s",
             plan.endpoints, plan.search_queries, plan.seed_artist_names)

    sp = spotify_client or get_spotify_client()
    candidates = sp.fetch_candidates(plan) if plan.endpoints else []
    log.info("Candidates fetched: %d (source=%s)", len(candidates), sp.name)

    if not candidates:
        log.warning("No candidates returned by Spotify layer; producing empty playlist.")
        return Playlist(
            intent=intent,
            plan=plan,
            tracks=[],
            generated_at=datetime.now(timezone.utc),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            using_real_spotify=sp.using_real_api,
        )

    tracks = rank_and_explain(intent, candidates, n=intent.target_track_count)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info("Reasoner produced %d ranked tracks in %d ms (total).", len(tracks), elapsed_ms)

    return Playlist(
        intent=intent,
        plan=plan,
        tracks=tracks,
        generated_at=datetime.now(timezone.utc),
        elapsed_ms=elapsed_ms,
        using_real_spotify=sp.using_real_api,
    )


__all__ = ["generate_playlist", "Intent", "Playlist"]
