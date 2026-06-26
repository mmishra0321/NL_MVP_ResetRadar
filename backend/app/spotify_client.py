"""Unified Spotify client with MOCK_MODE branch at every method boundary.

R0 scaffold: real-mode methods raise NotImplementedError; mock-mode
methods read from `mock_data/synthetic_weeks.json` and
`mock_data/mock_candidates.json` (also stubs in R0 - real fixtures land
in R1 + R2 respectively).

Real-mode Spotify Web API integration lands in R4 (reads) + R5 (writes).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings


log = logging.getLogger("reset_radar.spotify")


# ============================================================
# Shared helpers
# ============================================================

def _read_mock_json(filename: str) -> Any:
    """Read a JSON fixture from backend/mock_data/. Returns {} or [] if missing."""
    path: Path = settings.mock_data_dir / filename
    if not path.exists():
        log.warning("Mock fixture %s does not exist yet - returning empty default.", path)
        return {} if filename.endswith("_weeks.json") else []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Read endpoints (R1 uses these for snapshots; R4 wires real Spotify)
# ============================================================

def fetch_recent_snapshot(*, user_id: str, iso_week: str) -> dict[str, Any]:
    """Build a weekly snapshot of the user's recent listening.

    Mock mode: reads `synthetic_weeks.json` and returns the entry for
    the requested `iso_week`.
    Real mode (R4): fetches GET /me/top/tracks +
    GET /me/player/recently-played + GET /me/tracks; aggregates into
    the same dict shape as the mock fixture.

    Returns a dict shaped:
        {
            "iso_week": "2026-W26",
            "user_id": "...",
            "tracks": [
                {
                    "spotify_track_id": str,
                    "title": str,
                    "artist": str,
                    "genres": list[str],
                    "language": str,
                    "era": str,
                    "mood": str,
                    "play_count": int,
                },
                ...
            ],
        }
    """
    if settings.mock_mode:
        weeks = _read_mock_json("synthetic_weeks.json")
        if isinstance(weeks, dict) and iso_week in weeks:
            return weeks[iso_week]
        log.warning("Mock fixture has no entry for week %s; returning empty snapshot.", iso_week)
        return {"iso_week": iso_week, "user_id": user_id, "tracks": []}
    raise NotImplementedError(
        "Real Spotify read endpoints land in R4. "
        "Set MOCK_MODE=true in backend/.env for now."
    )


def fetch_artist_genres(*, artist_id: str) -> list[str]:
    """Fetch the `genres` field for a single artist.

    Mock mode: no-op (mock fixtures already include genres per track).
    Real mode (R4): GET /artists/{id} (batch endpoint is removed since
    Feb 2026, so this fetches one artist at a time).
    """
    if settings.mock_mode:
        return []
    raise NotImplementedError("Real /artists/{id} land in R4.")


# ============================================================
# Candidate generation (R2 uses these; R4 wires real /search)
# ============================================================

def search_candidates(
    *,
    scope_dimensions: list[str],
    scope_values: dict[str, list[str]],
    free_text_intent: str | None = None,
    target_pool_size: int | None = None,
) -> list[dict[str, Any]]:
    """Return a pool of candidate tracks for the reset session.

    Mock mode: filters `mock_candidates.json` by the chosen scope.
    Real mode (R4): builds /search field filters
    (genre:"carnatic" year:2015-2026, etc.), paginates 6-8 calls of 10
    results each, deduplicates by spotify_track_id, returns the pool.

    The returned pool size is bounded by
    `settings.max_candidates_from_search` (default 80).
    """
    if settings.mock_mode:
        candidates = _read_mock_json("mock_candidates.json")
        if not isinstance(candidates, list):
            log.warning("mock_candidates.json is not a list; returning empty pool.")
            return []
        return candidates[: target_pool_size or settings.max_candidates_from_search]
    raise NotImplementedError(
        "Real /search paginated candidate generation lands in R4."
    )


# ============================================================
# Write endpoints (R5 wires the real /me/playlists + /me/library)
# ============================================================

def create_playlist(*, user_id: str, name: str, description: str) -> dict[str, Any]:
    """Create a new playlist in the user's account.

    Mock mode: returns a synthetic playlist dict with a fake URL.
    Real mode (R5): POST /me/playlists (the `/users/{id}/playlists`
    form was removed; only the current-user form works).
    """
    if settings.mock_mode:
        fake_id = f"mock_playlist_{name.lower().replace(' ', '_')}"
        return {
            "id": fake_id,
            "name": name,
            "description": description,
            "external_urls": {
                "spotify": f"https://open.spotify.com/playlist/{fake_id}",
            },
        }
    raise NotImplementedError("Real POST /me/playlists lands in R5.")


def add_tracks_to_playlist(*, playlist_id: str, track_ids: list[str]) -> None:
    """Add tracks to a playlist.

    Mock mode: no-op.
    Real mode (R5): POST /playlists/{id}/items (the endpoint was
    renamed from `/tracks` to `/items` in Feb 2026).
    """
    if settings.mock_mode:
        log.info("[mock] would add %d tracks to playlist %s", len(track_ids), playlist_id)
        return
    raise NotImplementedError("Real POST /playlists/{id}/items lands in R5.")


def save_to_library(*, item_type: str, item_ids: list[str]) -> None:
    """Save items to the user's library (Keep decision).

    Mock mode: no-op.
    Real mode (R5): PUT /me/library (the generic save/follow endpoint
    that replaced the per-type endpoints).
    """
    if settings.mock_mode:
        log.info("[mock] would save %d %ss to library", len(item_ids), item_type)
        return
    raise NotImplementedError("Real PUT /me/library lands in R5.")


def delete_playlist(*, playlist_id: str) -> None:
    """Delete a playlist (Revert decision).

    Mock mode: no-op.
    Real mode (R5): there's no DELETE /playlists endpoint - the standard
    approach is to "unfollow" the playlist via DELETE /me/library, since
    a playlist the user owns disappears from their library when
    unfollowed even though it persists on Spotify's side.
    """
    if settings.mock_mode:
        log.info("[mock] would delete playlist %s", playlist_id)
        return
    raise NotImplementedError("Real playlist deletion (unfollow) lands in R5.")


__all__ = [
    "fetch_recent_snapshot",
    "fetch_artist_genres",
    "search_candidates",
    "create_playlist",
    "add_tracks_to_playlist",
    "save_to_library",
    "delete_playlist",
]
