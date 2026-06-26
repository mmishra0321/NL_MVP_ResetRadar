"""Unified Spotify Web API client with MOCK_MODE branch at every entry point.

R4 ships the real-mode branches for the four READ endpoints called out in
architecture.md section 6 + R4:

  * GET /me/top/tracks           (3 time ranges, merged)
  * GET /me/player/recently-played
  * GET /me/tracks               (saved library, paginated)
  * GET /artists/{id}            (one call per unique artist - the batch
                                  /artists endpoint was removed Feb 2026)

Plus a real-mode `/search` call (paginated 6-8 x 10) that the reset_engine
uses in real mode to assemble its 60-80 candidate pool.

Real and mock code paths return IDENTICALLY-SHAPED data so the rest of
the app never needs to know which mode it's in.

Write endpoints (POST /me/playlists, POST /playlists/{id}/items,
PUT /me/library, etc.) remain stubbed - those land in R5.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from app.config import settings


log = logging.getLogger("reset_radar.spotify")


# ============================================================
# Constants
# ============================================================

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# Reset Radar scopes - everything we need across R4 (reads) + R5 (writes).
# Requested up-front so the user authorises once, never twice.
SPOTIFY_SCOPES: list[str] = [
    # Reads (R4)
    "user-top-read",
    "user-read-recently-played",
    "user-library-read",
    # Writes (R5)
    "user-library-modify",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-follow-modify",
]

# Hard caps that bound a single weekly-snapshot fetch.
MAX_TOP_TRACKS_PER_RANGE = 50           # Spotify's API cap
MAX_RECENTLY_PLAYED = 50                # Spotify's API cap
MAX_SAVED_TRACKS = 100                  # paged 50 + 50; >2 pages slows the job

# Map a 4-digit year string to a decade bucket: "2017" -> "2010s"
def _year_to_era(year_str: str | None) -> str:
    if not year_str or not year_str[:4].isdigit():
        return "unknown"
    decade = (int(year_str[:4]) // 10) * 10
    return f"{decade}s"


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


def _iso_week_for(dt: datetime) -> str:
    """Return ISO 8601 week label, e.g. '2026-W26'."""
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


# ============================================================
# Real-mode auth helpers (token refresh; httpx client builder)
# ============================================================

class SpotifyAuthError(RuntimeError):
    """Raised when token refresh fails (user must re-auth)."""


def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Use a refresh token to mint a fresh access token.

    Spotify may or may not rotate the refresh token; we accept whichever
    pair the response gives us.
    """
    resp = httpx.post(
        SPOTIFY_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.spotify_client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10.0,
    )
    if resp.status_code != 200:
        raise SpotifyAuthError(
            f"Token refresh failed ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()


def _ensure_fresh_token(user_record: Any) -> str:
    """Return a non-expired access_token, refreshing if needed.

    `user_record` is the SQLAlchemy `User` ORM row. If we refresh the
    token, the caller is responsible for `db.commit()`-ing the updated
    fields back to disk.
    """
    if not user_record.access_token:
        raise SpotifyAuthError(
            f"User {user_record.id} has no access_token; complete /auth/login first."
        )

    needs_refresh = (
        user_record.token_expires_at is None
        or user_record.token_expires_at <= datetime.utcnow() + timedelta(seconds=30)
    )
    if not needs_refresh:
        return user_record.access_token

    if not user_record.refresh_token:
        raise SpotifyAuthError(
            f"User {user_record.id} access_token expired and has no refresh_token. "
            f"Re-authentication required."
        )

    payload = _refresh_access_token(user_record.refresh_token)
    user_record.access_token = payload["access_token"]
    if payload.get("refresh_token"):
        user_record.refresh_token = payload["refresh_token"]
    expires_in = int(payload.get("expires_in", 3600))
    user_record.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    log.info("Refreshed Spotify access token for user_id=%s", user_record.id)
    return user_record.access_token


def _spotify_client(access_token: str) -> httpx.Client:
    """Build a configured httpx Client for Spotify Web API calls."""
    return httpx.Client(
        base_url=SPOTIFY_API_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15.0,
    )


def _get_with_retry(
    client: httpx.Client,
    path: str,
    params: Optional[dict[str, Any]] = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """GET with 429 / 5xx retry. Raises for 4xx other than 429."""
    for attempt in range(1, max_attempts + 1):
        resp = client.get(path, params=params)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "1"))
            log.warning("Spotify 429 on %s; sleeping %.1fs (attempt %d)",
                        path, retry_after, attempt)
            time.sleep(retry_after)
            continue
        if 500 <= resp.status_code < 600 and attempt < max_attempts:
            time.sleep(0.5 * attempt)
            continue
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Spotify {resp.status_code} on {path}: {resp.text[:300]}",
                request=resp.request, response=resp,
            )
        return resp.json()
    raise RuntimeError(f"Spotify GET {path}: exhausted retries.")


# ============================================================
# Read endpoints - real-mode implementations
# ============================================================

def _real_top_tracks(client: httpx.Client, time_range: str) -> list[dict[str, Any]]:
    """GET /me/top/tracks for one time range, max 50 items."""
    data = _get_with_retry(client, "/me/top/tracks", params={
        "time_range": time_range,             # short_term | medium_term | long_term
        "limit": MAX_TOP_TRACKS_PER_RANGE,
    })
    return data.get("items", []) or []


def _real_recently_played(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /me/player/recently-played, max 50 items."""
    data = _get_with_retry(client, "/me/player/recently-played", params={
        "limit": MAX_RECENTLY_PLAYED,
    })
    # Each item is `{track: {...}, played_at: "..."}`; unwrap to a flat track list.
    return [it["track"] for it in (data.get("items") or []) if it.get("track")]


def _real_saved_tracks(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /me/tracks (saved library), paged up to MAX_SAVED_TRACKS."""
    out: list[dict[str, Any]] = []
    offset = 0
    while offset < MAX_SAVED_TRACKS:
        data = _get_with_retry(client, "/me/tracks", params={
            "limit": min(50, MAX_SAVED_TRACKS - offset),
            "offset": offset,
        })
        items = data.get("items") or []
        for it in items:
            if it.get("track"):
                out.append(it["track"])
        if len(items) < 50:
            break
        offset += 50
    return out


def fetch_artist_genres(*, artist_id: str, access_token: str | None = None) -> list[str]:
    """Fetch the `genres` field for a single artist.

    Mock mode: no-op (mock fixtures already include genres per track).
    Real mode: GET /artists/{id}. Cached upstream by the snapshot builder
    so each unique artist hits the API at most once per snapshot.
    """
    if settings.mock_mode:
        return []
    if not access_token:
        raise SpotifyAuthError("fetch_artist_genres needs an access_token in real mode.")
    with _spotify_client(access_token) as client:
        data = _get_with_retry(client, f"/artists/{artist_id}")
        return list(data.get("genres") or [])


def _build_genre_lookup(
    client: httpx.Client,
    artist_ids: Iterable[str],
) -> dict[str, list[str]]:
    """One sequential GET /artists/{id} per unique id. Result keyed by id.

    The batch /artists endpoint was removed in Feb 2026 (architecture.md
    section 6); we must fetch individually. ~50 artists at ~150ms each
    is ~7s and only happens once a week.
    """
    out: dict[str, list[str]] = {}
    for aid in {a for a in artist_ids if a}:
        try:
            data = _get_with_retry(client, f"/artists/{aid}")
            out[aid] = list(data.get("genres") or [])
        except Exception as exc:                                       # noqa: BLE001
            log.warning("Could not fetch genres for artist %s: %s", aid, exc)
            out[aid] = []
    return out


# ============================================================
# Snapshot builder (real mode)
# ============================================================

def _aggregate_appearances(
    *,
    top_short:  list[dict[str, Any]],
    top_med:    list[dict[str, Any]],
    top_long:   list[dict[str, Any]],
    recent:     list[dict[str, Any]],
    saved:      list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge the five raw track lists into one play-count map.

    Each appearance counts as 1; the resulting `play_count` is just the
    number of sources that referenced this track. Robust and easy to
    reason about. detection.py's weighted-Jaccard handles the range fine.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for source_list in (top_short, top_med, top_long, recent, saved):
        for tr in source_list:
            tid = tr.get("id")
            if not tid:
                continue
            row = by_id.get(tid)
            if row is None:
                by_id[tid] = {
                    "track": tr,
                    "play_count": 1,
                }
            else:
                row["play_count"] += 1
    return by_id


def _real_fetch_snapshot(
    user_record: Any,
    iso_week: str,
) -> dict[str, Any]:
    """The full real-mode snapshot pipeline for one user, one week.

    Steps:
      1. Refresh access token if needed.
      2. Pull top_tracks (3 time ranges) + recently_played + saved_tracks.
      3. Merge into a unique-track map with `play_count` = source count.
      4. Build a per-artist genre lookup via /artists/{id}.
      5. Derive `era` from each track's album release_date.
      6. Batch-classify language + mood via Groq (1 call each).
      7. Return the snapshot dict in the same shape as mock fixtures.
    """
    # Late import to avoid a startup circular: llm_client needs settings,
    # spotify_client also needs settings, both stay independent at the
    # module-import layer.
    from app.llm_client import classify_languages, classify_moods

    access_token = _ensure_fresh_token(user_record)

    with _spotify_client(access_token) as client:
        top_short = _real_top_tracks(client, "short_term")
        top_med   = _real_top_tracks(client, "medium_term")
        top_long  = _real_top_tracks(client, "long_term")
        recent    = _real_recently_played(client)
        saved     = _real_saved_tracks(client)

        merged = _aggregate_appearances(
            top_short=top_short, top_med=top_med, top_long=top_long,
            recent=recent, saved=saved,
        )

        # Collect unique artist ids across all tracks for one batch of /artists calls
        artist_ids: set[str] = set()
        for row in merged.values():
            for a in row["track"].get("artists") or []:
                if a.get("id"):
                    artist_ids.add(a["id"])
        genre_lookup = _build_genre_lookup(client, artist_ids)

    # ---- Build the bare-snapshot tracks (before LLM classification) ----
    bare_tracks: list[dict[str, Any]] = []
    for tid, row in merged.items():
        tr = row["track"]
        artist_objs = tr.get("artists") or [{}]
        primary_artist = artist_objs[0] if artist_objs else {}
        artist_name = primary_artist.get("name", "")
        # Genres: union across all the track's artists (Spotify attaches genres
        # to artists, not tracks).
        genres: list[str] = []
        seen: set[str] = set()
        for a in artist_objs:
            for g in genre_lookup.get(a.get("id") or "", []):
                if g not in seen:
                    seen.add(g); genres.append(g)
        # Era from album.release_date (e.g. "2017-03-15" or just "2017")
        album = tr.get("album") or {}
        release_date = album.get("release_date", "")
        bare_tracks.append({
            "spotify_track_id": tid,
            "title": tr.get("name", ""),
            "artist": artist_name,
            "album": album.get("name"),
            "genres": genres,
            "era": _year_to_era(release_date),
            "play_count": row["play_count"],
        })

    # ---- Batch language + mood classification ----
    log.info("Classifying language + mood for %d tracks (user_id=%s)",
             len(bare_tracks), user_record.id)
    langs = classify_languages(bare_tracks) if bare_tracks else []
    moods = classify_moods(bare_tracks)     if bare_tracks else []
    for i, t in enumerate(bare_tracks):
        t["language"] = langs[i] if i < len(langs) else "other"
        t["mood"]     = moods[i] if i < len(moods) else "chill"

    return {
        "iso_week": iso_week,
        "user_id": user_record.id,
        "tracks": bare_tracks,
    }


# ============================================================
# Top-level read endpoints (mock/real branch at the top of each)
# ============================================================

def fetch_recent_snapshot(
    *,
    user_id: str,
    iso_week: str,
    user_record: Any = None,
) -> dict[str, Any]:
    """Build a weekly snapshot of the user's recent listening.

    Mock mode: reads `synthetic_weeks.json` and returns the entry for
    the requested `iso_week`.

    Real mode: calls `_real_fetch_snapshot`, which orchestrates the
    Spotify reads + Groq classification. The caller must pass the
    SQLAlchemy `user_record` so token refresh can write the new token
    back. (In mock mode `user_record` is ignored.)

    Returns a dict shaped:
        {
            "iso_week": "2026-W26",
            "user_id": "...",
            "tracks": [
                {
                    "spotify_track_id": str,
                    "title": str,
                    "artist": str,
                    "album": str | None,
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
        if isinstance(weeks, dict):
            week_entries = weeks.get("weeks", weeks)                   # tolerate both wrappers
            if isinstance(week_entries, dict) and iso_week in week_entries:
                snaps = week_entries[iso_week]
                if isinstance(snaps, list):
                    # Old-style fixture: list-of-snaps per week
                    for snap in snaps:
                        if snap.get("user_id") == user_id:
                            return {
                                "iso_week": iso_week,
                                "user_id": user_id,
                                "tracks": snap.get("tracks", []),
                            }
                elif isinstance(snaps, dict) and snaps.get("user_id") == user_id:
                    return snaps
        log.warning("Mock fixture has no entry for week %s; returning empty snapshot.", iso_week)
        return {"iso_week": iso_week, "user_id": user_id, "tracks": []}

    if user_record is None:
        raise SpotifyAuthError(
            "fetch_recent_snapshot in real mode requires a SQLAlchemy user_record."
        )
    return _real_fetch_snapshot(user_record, iso_week)


# ============================================================
# Candidate generation (reset engine uses this)
# ============================================================

def search_candidates(
    *,
    scope_dimensions: list[str],
    scope_values: dict[str, list[str]],
    free_text_intent: str | None = None,
    target_pool_size: int | None = None,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    """Return a pool of candidate tracks for the reset session.

    Mock mode: filters `mock_candidates.json` by the chosen scope.

    Real mode: builds /search field filters (genre:"jazz" year:2015-2026,
    etc.), paginates 6-8 calls of 10 results each, deduplicates, returns
    the pool. The returned pool size is bounded by
    `settings.max_candidates_from_search` (default 80).
    """
    if settings.mock_mode:
        payload = _read_mock_json("mock_candidates.json")
        if isinstance(payload, dict) and "candidates" in payload:
            candidates = payload["candidates"]
        elif isinstance(payload, list):
            candidates = payload
        else:
            log.warning("mock_candidates.json shape unrecognised; returning empty pool.")
            return []
        if not isinstance(candidates, list):
            return []
        scope_set = set(scope_dimensions)
        if scope_set:
            filtered = [
                c for c in candidates
                if c.get("scope_origin") in scope_set or c.get("scope_origin") is None
            ]
        else:
            filtered = list(candidates)
        return filtered[: target_pool_size or settings.max_candidates_from_search]

    # ---- Real mode ----
    if not access_token:
        raise SpotifyAuthError("search_candidates in real mode requires an access_token.")

    # Build queries from the requested scope. Each scope dimension can
    # produce multiple queries (one per value); each query is paginated.
    queries = _build_real_search_queries(scope_dimensions, scope_values, free_text_intent)
    if not queries:
        return []

    pool_cap = target_pool_size or settings.max_candidates_from_search
    page_size = settings.spotify_search_page_size
    by_id: dict[str, dict[str, Any]] = {}

    with _spotify_client(access_token) as client:
        for q in queries:
            offset = 0
            pages_used = 0
            max_pages = 8                                              # 8 * 10 = 80 per query
            while len(by_id) < pool_cap and pages_used < max_pages:
                data = _get_with_retry(client, "/search", params={
                    "q": q,
                    "type": "track",
                    "limit": page_size,
                    "offset": offset,
                })
                items = (data.get("tracks") or {}).get("items") or []
                if not items:
                    break
                new_added = 0
                for tr in items:
                    tid = tr.get("id")
                    if not tid or tid in by_id:
                        continue
                    artist_objs = tr.get("artists") or [{}]
                    by_id[tid] = {
                        "spotify_track_id": tid,
                        "title": tr.get("name", ""),
                        "artist": (artist_objs[0] or {}).get("name", ""),
                        "album": (tr.get("album") or {}).get("name"),
                        "genres": [],                                   # filled by callers via /artists
                        "language": None,
                        "era": _year_to_era((tr.get("album") or {}).get("release_date")),
                        "mood": None,
                    }
                    new_added += 1
                    if len(by_id) >= pool_cap:
                        break
                # If a full page returned but none of it was new, this query
                # has saturated; stop paging it (avoids burning calls).
                if new_added == 0:
                    break
                offset += page_size
                pages_used += 1

    return list(by_id.values())[:pool_cap]


def _build_real_search_queries(
    scope_dimensions: list[str],
    scope_values: dict[str, list[str]],
    free_text_intent: str | None,
) -> list[str]:
    """Concrete /search query strings derived from scope + intent."""
    out: list[str] = []
    for dim in scope_dimensions:
        values = scope_values.get(dim) or []
        if dim == "genre":
            out.extend(f'genre:"{v}"' for v in values)
        elif dim == "era":
            for v in values:
                if v.lower().endswith("s") and v[:-1].isdigit():
                    start = int(v[:-1])
                    out.append(f"year:{start}-{start + 9}")
        elif dim in ("language", "mood"):
            # No field filter; fall through to free-text query
            out.extend(values)
    if free_text_intent:
        out.append(free_text_intent)
    return out


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
    "SpotifyAuthError",
    "SPOTIFY_API_BASE",
    "SPOTIFY_TOKEN_URL",
    "SPOTIFY_SCOPES",
]
