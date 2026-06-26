"""Real-mode tests for the R5 Spotify write endpoints.

httpx is mocked at the module level via `httpx.MockTransport` patched
into `httpx.request`, so we can assert on the exact method + path +
body that each function sends. These tests never hit real Spotify.

Endpoints under test:
  POST   /me/playlists                  -> create_playlist
  POST   /playlists/{id}/items          -> add_tracks_to_playlist
  PUT    /me/tracks?ids=...             -> save_to_library(track)
  PUT    /me/following?type=artist&...  -> save_to_library(artist)
  DELETE /playlists/{id}/followers      -> delete_playlist
  GET    /tracks?ids=...                -> resolve_artist_ids_for_tracks
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app import spotify_client


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(spotify_client.settings, "mock_mode", False)


@pytest.fixture
def captured_calls():
    """List of (method, path, params, json_body) tuples for each request."""
    return []


@pytest.fixture
def fake_request(monkeypatch, captured_calls):
    """Patch httpx.request to capture calls and return a configurable body."""
    responses: list[dict] = []  # FIFO queue; default {} when empty

    def _request(method, url, headers=None, params=None, json=None, timeout=None):
        # Strip the absolute base URL for assertion clarity.
        path = url
        if path.startswith(spotify_client.SPOTIFY_API_BASE):
            path = path[len(spotify_client.SPOTIFY_API_BASE):]
        captured_calls.append({
            "method": method,
            "path": path,
            "params": params,
            "json": json,
            "auth": (headers or {}).get("Authorization"),
        })
        body = responses.pop(0) if responses else {}
        return httpx.Response(
            200,
            json=body,
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(spotify_client.httpx, "request", _request)
    # Allow tests to queue specific responses.
    _request.responses = responses
    return _request


# ============================================================
# create_playlist
# ============================================================

class TestCreatePlaylistReal:
    def test_posts_to_me_playlists_with_private_default(
        self, real_mode, fake_request, captured_calls
    ):
        fake_request.responses.append({
            "id": "pl-123",
            "name": "Reset Radar - language",
            "external_urls": {"spotify": "https://open.spotify.com/playlist/pl-123"},
        })
        out = spotify_client.create_playlist(
            user_id="u1",
            name="Reset Radar - language",
            description="Sandboxed 10-day reset trial.",
            access_token="tok-A",
        )
        assert out["id"] == "pl-123"
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/me/playlists"
        assert call["auth"] == "Bearer tok-A"
        assert call["json"] == {
            "name": "Reset Radar - language",
            "description": "Sandboxed 10-day reset trial.",
            "public": False,
            "collaborative": False,
        }

    def test_missing_token_raises_auth_error(self, real_mode):
        with pytest.raises(spotify_client.SpotifyAuthError):
            spotify_client.create_playlist(
                user_id="u1", name="X", description="Y", access_token=None,
            )

    def test_mock_mode_returns_synthetic_playlist_dict(self, monkeypatch):
        monkeypatch.setattr(spotify_client.settings, "mock_mode", True)
        out = spotify_client.create_playlist(
            user_id="u1", name="Reset Radar - mood", description="...",
        )
        assert out["id"].startswith("mock_playlist_")
        assert "open.spotify.com/playlist/" in out["external_urls"]["spotify"]


# ============================================================
# add_tracks_to_playlist
# ============================================================

class TestAddTracksToPlaylistReal:
    def test_posts_uris_to_items_endpoint(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.add_tracks_to_playlist(
            playlist_id="pl-123",
            track_ids=["t1", "t2", "t3"],
            access_token="tok-A",
        )
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/playlists/pl-123/items"   # NOT /tracks
        assert call["json"] == {
            "uris": ["spotify:track:t1", "spotify:track:t2", "spotify:track:t3"],
        }

    def test_chunks_to_100_per_call(
        self, real_mode, fake_request, captured_calls
    ):
        ids = [f"t{i}" for i in range(250)]
        spotify_client.add_tracks_to_playlist(
            playlist_id="pl-123", track_ids=ids, access_token="tok-A",
        )
        assert len(captured_calls) == 3   # 100 + 100 + 50
        assert len(captured_calls[0]["json"]["uris"]) == 100
        assert len(captured_calls[2]["json"]["uris"]) == 50

    def test_empty_track_list_short_circuits(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.add_tracks_to_playlist(
            playlist_id="pl-123", track_ids=[], access_token="tok-A",
        )
        assert captured_calls == []

    def test_missing_token_raises_auth_error(self, real_mode):
        with pytest.raises(spotify_client.SpotifyAuthError):
            spotify_client.add_tracks_to_playlist(
                playlist_id="pl-123", track_ids=["t1"], access_token=None,
            )


# ============================================================
# save_to_library
# ============================================================

class TestSaveToLibraryReal:
    def test_track_type_calls_put_me_tracks(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.save_to_library(
            item_type="track", item_ids=["t1", "t2"], access_token="tok-A",
        )
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["method"] == "PUT"
        assert call["path"] == "/me/tracks"
        assert call["params"] == {"ids": "t1,t2"}
        assert call["auth"] == "Bearer tok-A"

    def test_artist_type_calls_put_me_following(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.save_to_library(
            item_type="artist", item_ids=["a1", "a2"], access_token="tok-A",
        )
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["method"] == "PUT"
        assert call["path"] == "/me/following"
        assert call["params"] == {"type": "artist", "ids": "a1,a2"}

    def test_chunks_to_50_per_call(
        self, real_mode, fake_request, captured_calls
    ):
        ids = [f"a{i}" for i in range(120)]
        spotify_client.save_to_library(
            item_type="artist", item_ids=ids, access_token="tok-A",
        )
        assert len(captured_calls) == 3   # 50 + 50 + 20
        assert captured_calls[0]["params"]["ids"].count(",") == 49   # 50 ids -> 49 commas
        assert captured_calls[2]["params"]["ids"].count(",") == 19   # 20 ids -> 19 commas

    def test_empty_id_list_short_circuits(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.save_to_library(
            item_type="track", item_ids=[], access_token="tok-A",
        )
        assert captured_calls == []

    def test_unknown_item_type_raises(self, real_mode):
        with pytest.raises(ValueError, match="Unknown item_type"):
            spotify_client.save_to_library(
                item_type="album", item_ids=["x"], access_token="tok-A",
            )

    def test_missing_token_raises_auth_error(self, real_mode):
        with pytest.raises(spotify_client.SpotifyAuthError):
            spotify_client.save_to_library(
                item_type="track", item_ids=["t1"], access_token=None,
            )


# ============================================================
# delete_playlist (unfollow)
# ============================================================

class TestDeletePlaylistReal:
    def test_deletes_via_followers_endpoint(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.delete_playlist(
            playlist_id="pl-123", access_token="tok-A",
        )
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["method"] == "DELETE"
        assert call["path"] == "/playlists/pl-123/followers"
        assert call["auth"] == "Bearer tok-A"

    def test_empty_playlist_id_short_circuits(
        self, real_mode, fake_request, captured_calls
    ):
        spotify_client.delete_playlist(playlist_id="", access_token="tok-A")
        assert captured_calls == []

    def test_missing_token_raises_auth_error(self, real_mode):
        with pytest.raises(spotify_client.SpotifyAuthError):
            spotify_client.delete_playlist(playlist_id="pl-1", access_token=None)


# ============================================================
# resolve_artist_ids_for_tracks
# ============================================================

class TestResolveArtistIdsReal:
    def test_returns_unique_artist_ids_in_order(
        self, real_mode, fake_request, captured_calls
    ):
        fake_request.responses.append({
            "tracks": [
                {"id": "t1", "artists": [{"id": "a1"}, {"id": "a2"}]},
                {"id": "t2", "artists": [{"id": "a1"}, {"id": "a3"}]},   # a1 dup
                {"id": "t3", "artists": [{"id": "a4"}]},
            ],
        })
        out = spotify_client.resolve_artist_ids_for_tracks(
            track_ids=["t1", "t2", "t3"], access_token="tok-A",
        )
        # First-seen order: a1, a2, a3, a4
        assert out == ["a1", "a2", "a3", "a4"]
        assert captured_calls[0]["method"] == "GET"
        assert captured_calls[0]["path"] == "/tracks"
        assert captured_calls[0]["params"] == {"ids": "t1,t2,t3"}

    def test_chunks_to_50_per_call(
        self, real_mode, fake_request, captured_calls
    ):
        # Two pages of 50 + a final 25.
        fake_request.responses.extend([
            {"tracks": [{"id": f"t{i}", "artists": [{"id": f"a{i}"}]} for i in range(50)]},
            {"tracks": [{"id": f"t{i}", "artists": [{"id": f"a{i}"}]} for i in range(50, 100)]},
            {"tracks": [{"id": f"t{i}", "artists": [{"id": f"a{i}"}]} for i in range(100, 125)]},
        ])
        out = spotify_client.resolve_artist_ids_for_tracks(
            track_ids=[f"t{i}" for i in range(125)], access_token="tok-A",
        )
        assert len(out) == 125
        assert len(captured_calls) == 3

    def test_empty_input_short_circuits(
        self, real_mode, fake_request, captured_calls
    ):
        out = spotify_client.resolve_artist_ids_for_tracks(
            track_ids=[], access_token="tok-A",
        )
        assert out == []
        assert captured_calls == []

    def test_mock_mode_returns_empty(self, monkeypatch):
        monkeypatch.setattr(spotify_client.settings, "mock_mode", True)
        out = spotify_client.resolve_artist_ids_for_tracks(
            track_ids=["mock-genre-1"], access_token="ignored",
        )
        assert out == []


# ============================================================
# Retry behaviour (regression for the shared _spotify_request helper)
# ============================================================

class TestSpotifyRequestRetry:
    def test_429_triggers_sleep_and_retry(self, real_mode, monkeypatch):
        attempts = []

        def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
            attempts.append(1)
            if len(attempts) == 1:
                resp = httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    request=httpx.Request(method, url),
                )
                return resp
            return httpx.Response(200, json={}, request=httpx.Request(method, url))

        monkeypatch.setattr(spotify_client.httpx, "request", fake_request)
        spotify_client._spotify_request(
            "POST", "/me/playlists", access_token="x", json_body={"name": "n"},
        )
        assert len(attempts) == 2

    def test_4xx_other_than_429_raises_immediately(self, real_mode, monkeypatch):
        def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
            return httpx.Response(
                404,
                text='{"error":"not found"}',
                request=httpx.Request(method, url),
            )

        monkeypatch.setattr(spotify_client.httpx, "request", fake_request)
        with pytest.raises(httpx.HTTPStatusError, match="404"):
            spotify_client._spotify_request(
                "DELETE", "/playlists/x/followers", access_token="t",
            )
