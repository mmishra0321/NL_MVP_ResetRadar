"""Real-mode tests for spotify_client.py.

The Spotify Web API is mocked at the httpx layer via `httpx.MockTransport`
so we can exercise:
  * /me/top/tracks merging across 3 time ranges
  * /me/player/recently-played unwrap
  * /me/tracks pagination
  * /artists/{id} per-artist genre fetch
  * The aggregator that counts appearances across all 5 sources
  * The snapshot builder that calls Groq for language/mood
  * /search paginated candidate generation
  * Token refresh

Groq is mocked at the `app.llm_client.classify_languages` / `classify_moods`
boundary so these tests never hit the real LLM.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app import spotify_client


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_settings(monkeypatch):
    """Force real-mode by patching settings.mock_mode at the call sites."""
    monkeypatch.setattr(spotify_client.settings, "mock_mode", False)
    monkeypatch.setattr(spotify_client.settings, "spotify_client_id", "test-client-id")
    monkeypatch.setattr(spotify_client.settings, "max_candidates_from_search", 80)
    monkeypatch.setattr(spotify_client.settings, "spotify_search_page_size", 10)
    return spotify_client.settings


@pytest.fixture
def fake_user_record():
    """A duck-typed stand-in for the SQLAlchemy User row."""
    return SimpleNamespace(
        id="test-user-uuid",
        spotify_user_id="spotify-test",
        display_name="Test User",
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
    )


def _track(track_id: str, name: str, artist_id: str, artist_name: str,
           release_date: str = "2017-05-01", album_name: str = "Test Album"):
    """Build a Spotify API-shaped track object."""
    return {
        "id": track_id,
        "name": name,
        "artists": [{"id": artist_id, "name": artist_name}],
        "album": {"name": album_name, "release_date": release_date},
    }


# ============================================================
# Tests: per-endpoint readers
# ============================================================

class TestReadEndpoints:
    def test_top_tracks_merges_short_medium_long(self, mock_settings):
        handler = _build_transport([
            ("/me/top/tracks", {"time_range": "short_term", "limit": "50"},
                {"items": [_track("t1", "S1", "a1", "A1")]}),
            ("/me/top/tracks", {"time_range": "medium_term", "limit": "50"},
                {"items": [_track("t2", "M1", "a1", "A1")]}),
            ("/me/top/tracks", {"time_range": "long_term", "limit": "50"},
                {"items": [_track("t3", "L1", "a2", "A2")]}),
        ])
        with httpx.Client(transport=handler, base_url=spotify_client.SPOTIFY_API_BASE,
                          headers={"Authorization": "Bearer x"}) as client:
            short = spotify_client._real_top_tracks(client, "short_term")
            med   = spotify_client._real_top_tracks(client, "medium_term")
            long_ = spotify_client._real_top_tracks(client, "long_term")
        assert [t["id"] for t in short] == ["t1"]
        assert [t["id"] for t in med]   == ["t2"]
        assert [t["id"] for t in long_] == ["t3"]

    def test_recently_played_unwraps_track(self, mock_settings):
        handler = _build_transport([
            ("/me/player/recently-played", {"limit": "50"},
                {"items": [
                    {"played_at": "2026-06-25T08:00:00Z", "track": _track("rp1", "R1", "a3", "A3")},
                    {"played_at": "2026-06-25T07:00:00Z", "track": _track("rp2", "R2", "a3", "A3")},
                ]}),
        ])
        with httpx.Client(transport=handler, base_url=spotify_client.SPOTIFY_API_BASE,
                          headers={"Authorization": "Bearer x"}) as client:
            tracks = spotify_client._real_recently_played(client)
        assert [t["id"] for t in tracks] == ["rp1", "rp2"]

    def test_saved_tracks_pagination(self, mock_settings):
        handler = _build_transport([
            ("/me/tracks", {"limit": "50", "offset": "0"},
                {"items": [{"track": _track(f"st{i}", f"S{i}", "a4", "A4")} for i in range(50)]}),
            ("/me/tracks", {"limit": "50", "offset": "50"},
                {"items": [{"track": _track(f"st{i}", f"S{i}", "a4", "A4")} for i in range(50, 75)]}),
        ])
        with httpx.Client(transport=handler, base_url=spotify_client.SPOTIFY_API_BASE,
                          headers={"Authorization": "Bearer x"}) as client:
            tracks = spotify_client._real_saved_tracks(client)
        # 50 from page 1 + 25 from page 2 (page 2 short -> loop breaks)
        assert len(tracks) == 75

    def test_genre_lookup_one_call_per_unique_artist(self, mock_settings):
        handler = _build_transport([
            ("/artists/a1", None, {"id": "a1", "genres": ["jazz", "neo-soul"]}),
            ("/artists/a2", None, {"id": "a2", "genres": ["indie-pop"]}),
        ])
        with httpx.Client(transport=handler, base_url=spotify_client.SPOTIFY_API_BASE,
                          headers={"Authorization": "Bearer x"}) as client:
            out = spotify_client._build_genre_lookup(client, ["a1", "a2", "a1"])  # dedup
        assert out["a1"] == ["jazz", "neo-soul"]
        assert out["a2"] == ["indie-pop"]


# ============================================================
# Tests: aggregation + snapshot builder
# ============================================================

class TestAggregator:
    def test_track_in_all_sources_counts_5(self):
        tr = _track("x1", "X", "a", "Artist")
        out = spotify_client._aggregate_appearances(
            top_short=[tr], top_med=[tr], top_long=[tr],
            recent=[tr], saved=[tr],
        )
        assert out["x1"]["play_count"] == 5

    def test_track_in_one_source_counts_1(self):
        tr = _track("x1", "X", "a", "Artist")
        out = spotify_client._aggregate_appearances(
            top_short=[tr], top_med=[], top_long=[], recent=[], saved=[],
        )
        assert out["x1"]["play_count"] == 1

    def test_skips_tracks_with_missing_id(self):
        bad = {"name": "no id"}
        out = spotify_client._aggregate_appearances(
            top_short=[bad], top_med=[], top_long=[], recent=[], saved=[],
        )
        assert out == {}


class TestSnapshotBuilder:
    def test_full_snapshot_classifies_with_groq(self, mock_settings, fake_user_record):
        """End-to-end real-mode snapshot with Spotify mocked + Groq mocked."""
        handler = _build_transport([
            ("/me/top/tracks", {"time_range": "short_term", "limit": "50"},
                {"items": [_track("t1", "Song One", "a1", "Artist One", "2017-05-01")]}),
            ("/me/top/tracks", {"time_range": "medium_term", "limit": "50"},
                {"items": [_track("t1", "Song One", "a1", "Artist One", "2017-05-01")]}),
            ("/me/top/tracks", {"time_range": "long_term", "limit": "50"},
                {"items": [_track("t2", "Song Two", "a2", "Artist Two", "1995-01-01")]}),
            ("/me/player/recently-played", {"limit": "50"},
                {"items": [{"played_at": "x", "track": _track("t1", "Song One", "a1", "Artist One", "2017-05-01")}]}),
            ("/me/tracks", {"limit": "50", "offset": "0"},
                {"items": [{"track": _track("t2", "Song Two", "a2", "Artist Two", "1995-01-01")}]}),
            ("/artists/a1", None, {"id": "a1", "genres": ["indie-rock"]}),
            ("/artists/a2", None, {"id": "a2", "genres": ["alt-rock"]}),
        ])

        def fake_client_factory(_):
            return httpx.Client(
                transport=handler,
                base_url=spotify_client.SPOTIFY_API_BASE,
                headers={"Authorization": "Bearer x"},
            )

        with patch("app.spotify_client._spotify_client", side_effect=fake_client_factory), \
             patch("app.llm_client.classify_languages", return_value=["en", "en"]), \
             patch("app.llm_client.classify_moods",     return_value=["chill", "nostalgic"]):
            snap = spotify_client.fetch_recent_snapshot(
                user_id=fake_user_record.id,
                iso_week="2026-W26",
                user_record=fake_user_record,
            )

        assert snap["user_id"] == "test-user-uuid"
        assert snap["iso_week"] == "2026-W26"
        assert len(snap["tracks"]) == 2
        t1 = next(t for t in snap["tracks"] if t["spotify_track_id"] == "t1")
        t2 = next(t for t in snap["tracks"] if t["spotify_track_id"] == "t2")
        # t1 appears in short_term + medium_term + recent_played = 3
        assert t1["play_count"] == 3
        # t2 appears in long_term + saved = 2
        assert t2["play_count"] == 2
        # Genres flowed through from /artists endpoint
        assert "indie-rock" in t1["genres"]
        assert "alt-rock" in t2["genres"]
        # Era derived from release_date
        assert t1["era"] == "2010s"
        assert t2["era"] == "1990s"
        # LLM classifications stamped on
        assert t1["language"] == "en"
        assert t2["mood"] == "nostalgic"


# ============================================================
# Tests: search candidates (real mode)
# ============================================================

class TestSearchCandidatesReal:
    def test_real_search_paginates_and_dedups(self, mock_settings):
        # Two queries from the two genre values; each query returns 10 + 10 then empty
        handler = _build_transport([
            ("/search", {"q": 'genre:"jazz"', "type": "track", "limit": "10", "offset": "0"},
                {"tracks": {"items": [_track(f"j{i}", f"J{i}", "aj", "JArt") for i in range(10)]}}),
            ("/search", {"q": 'genre:"jazz"', "type": "track", "limit": "10", "offset": "10"},
                {"tracks": {"items": [_track(f"j{i}", f"J{i}", "aj", "JArt") for i in range(10)]}}),  # dups, dropped
            ("/search", {"q": 'genre:"neo-soul"', "type": "track", "limit": "10", "offset": "0"},
                {"tracks": {"items": [_track(f"n{i}", f"N{i}", "an", "NArt") for i in range(10)]}}),
            ("/search", {"q": 'genre:"neo-soul"', "type": "track", "limit": "10", "offset": "10"},
                {"tracks": {"items": []}}),  # exhausted
        ])

        def fake_client_factory(_):
            return httpx.Client(
                transport=handler,
                base_url=spotify_client.SPOTIFY_API_BASE,
                headers={"Authorization": "Bearer x"},
            )

        with patch("app.spotify_client._spotify_client", side_effect=fake_client_factory):
            pool = spotify_client.search_candidates(
                scope_dimensions=["genre"],
                scope_values={"genre": ["jazz", "neo-soul"]},
                access_token="x",
                target_pool_size=80,
            )
        ids = [c["spotify_track_id"] for c in pool]
        # 10 unique jazz + 10 unique neo-soul = 20 (duplicate page on jazz drops)
        assert len(ids) == 20
        assert len(set(ids)) == 20

    def test_query_builder_era_to_year_range(self, mock_settings):
        q = spotify_client._build_real_search_queries(
            scope_dimensions=["era"], scope_values={"era": ["1990s"]},
            free_text_intent=None,
        )
        assert q == ["year:1990-1999"]


# ============================================================
# Tests: token refresh
# ============================================================

class TestTokenRefresh:
    def test_refresh_triggered_when_expired(self, mock_settings, fake_user_record):
        fake_user_record.token_expires_at = datetime.utcnow() - timedelta(minutes=1)
        with patch.object(spotify_client, "_refresh_access_token",
                          return_value={
                              "access_token": "new-token",
                              "refresh_token": "new-refresh",
                              "expires_in": 3600,
                          }) as refresh_call:
            token = spotify_client._ensure_fresh_token(fake_user_record)
        assert token == "new-token"
        assert fake_user_record.access_token == "new-token"
        assert fake_user_record.refresh_token == "new-refresh"
        assert refresh_call.call_count == 1

    def test_refresh_not_triggered_when_fresh(self, mock_settings, fake_user_record):
        fake_user_record.token_expires_at = datetime.utcnow() + timedelta(hours=1)
        with patch.object(spotify_client, "_refresh_access_token") as refresh_call:
            token = spotify_client._ensure_fresh_token(fake_user_record)
        assert token == "fake-access-token"
        assert refresh_call.call_count == 0

    def test_refresh_fails_without_refresh_token(self, mock_settings, fake_user_record):
        fake_user_record.token_expires_at = datetime.utcnow() - timedelta(minutes=1)
        fake_user_record.refresh_token = None
        with pytest.raises(spotify_client.SpotifyAuthError, match="refresh_token"):
            spotify_client._ensure_fresh_token(fake_user_record)


# ============================================================
# Tests: mock-mode still works (regression)
# ============================================================

class TestMockModeStillWorks:
    """R4 must not regress R1+R2 mock-mode behaviour."""

    def test_mock_mode_returns_synthetic_snapshot(self, monkeypatch):
        monkeypatch.setattr(spotify_client.settings, "mock_mode", True)
        snap = spotify_client.fetch_recent_snapshot(
            user_id="demo-karthik-001", iso_week="2026-W26",
        )
        assert snap["user_id"] == "demo-karthik-001"
        assert snap["iso_week"] == "2026-W26"
        assert len(snap["tracks"]) > 0

    def test_mock_mode_search_candidates_filters_by_scope(self, monkeypatch):
        monkeypatch.setattr(spotify_client.settings, "mock_mode", True)
        pool = spotify_client.search_candidates(
            scope_dimensions=["language"], scope_values={}, target_pool_size=80,
        )
        assert len(pool) > 0
        assert all(c.get("scope_origin") == "language" for c in pool)


# ============================================================
# Tests: helpers
# ============================================================

class TestHelpers:
    @pytest.mark.parametrize("year_str,expected", [
        ("2017",       "2010s"),
        ("2017-05-01", "2010s"),
        ("1995-01-01", "1990s"),
        ("",           "unknown"),
        (None,         "unknown"),
        ("not-a-year", "unknown"),
    ])
    def test_year_to_era(self, year_str, expected):
        assert spotify_client._year_to_era(year_str) == expected


# ============================================================
# Helper: httpx MockTransport that routes by (path, query-params)
# ============================================================

def _build_transport(
    routes: list[tuple[str, dict | None, dict]],
) -> httpx.MockTransport:
    """Match by (path, sorted query-params).

    routes is a list of (path, expected_params_or_None, response_json).
    expected_params=None matches any query string for that path.
    """

    def _norm_params(qs_or_dict):
        if isinstance(qs_or_dict, dict):
            return tuple(sorted((k, str(v)) for k, v in qs_or_dict.items()))
        return tuple(sorted(qs_or_dict.multi_items()))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/v1"):
            path = path[3:]
        params = _norm_params(request.url.params)
        # Prefer exact (path + params) matches; fall back to path-only.
        for r_path, r_params, r_resp in routes:
            if r_path != path:
                continue
            if r_params is None or _norm_params(r_params) == params:
                return httpx.Response(200, json=r_resp)
        return httpx.Response(404, json={
            "error": f"unmocked {path}?{request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query}",
        })

    return httpx.MockTransport(handler)
