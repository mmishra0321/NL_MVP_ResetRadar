"""End-to-end real-mode tests for routes/reset.py.

These exercise the FULL request pipeline through FastAPI's TestClient
with both spotify_client and llm_client mocked at module level. We
verify:

  - POST /reset/sessions in real mode calls create_playlist +
    add_tracks_to_playlist with the user's access_token.
  - POST /reset/sessions/{id}/decide on "keep" calls
    resolve_artist_ids_for_tracks AND follows artists AND saves tracks.
  - POST /reset/sessions/{id}/decide on "revert" calls delete_playlist.
  - Mock-mode regression: the same flows still no-op the writes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, db_session, engine
from app.main import app
from app.models import (
    Nudge,
    ResetSession,
    ResetTrack,
    StuckScore,
    User,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def authed_user():
    """Insert an OAuth'd user with a valid (not-expired) access token."""
    with db_session() as db:
        u = User(
            id="u-real-1",
            spotify_user_id="spotify-real-1",
            display_name="Real Listener",
            access_token="live-access-token",
            refresh_token="live-refresh-token",
            token_expires_at=datetime.utcnow() + timedelta(hours=1),
            created_at=datetime.utcnow(),
        )
        db.add(u)
        # Seed a StuckScore so `before_stuck_score` is populated.
        db.add(StuckScore(
            id=str(uuid.uuid4()),
            user_id="u-real-1",
            iso_week="2026-W26",
            genre=0.4, language=0.85, era=0.5, mood=0.6, overall=0.82,
            suggested_scope="language",
            computed_at=datetime.utcnow(),
        ))
        db.commit()
    return "u-real-1"


@pytest.fixture
def existing_session(authed_user):
    """Insert a reset session ready for the decide endpoint to act on."""
    sid = "session-real-1"
    with db_session() as db:
        s = ResetSession(
            id=sid,
            user_id=authed_user,
            nudge_id=None,
            scope_dimensions_json=["language"],
            free_text_intent=None,
            spotify_playlist_id="pl-existing-1",
            trial_end_date=datetime.utcnow() + timedelta(days=10),
            before_stuck_score=0.82,
            created_at=datetime.utcnow(),
        )
        db.add(s)
        for i in range(3):
            db.add(ResetTrack(
                id=str(uuid.uuid4()),
                reset_session_id=sid,
                spotify_track_id=f"track-{i}",
                title=f"Track {i}",
                artist=f"Artist {i}",
                album="Album",
                genre="indie", language="en", era="2010s", mood="chill",
                llm_score=0.8, llm_explanation="because.",
                order_index=i,
            ))
        db.commit()
    return sid


# ============================================================
# Real-mode create_reset_session
# ============================================================

class TestCreateSessionReal:
    def test_real_mode_passes_access_token_to_writes(
        self, monkeypatch, authed_user,
    ):
        monkeypatch.setattr(settings, "mock_mode", False)
        # Stub the engine (no real Groq); return 3 ranked tracks.
        ranked = [
            {"spotify_track_id": f"rt{i}", "title": f"T{i}", "artist": f"A{i}",
             "album": "Alb", "genres": ["indie"], "language": "en",
             "era": "2010s", "mood": "chill", "score": 0.9 - i*0.1,
             "why": f"because {i}", "order_index": i}
            for i in range(3)
        ]

        with patch("app.routes.reset.generate_reset_playlist", return_value=ranked), \
             patch("app.routes.reset.create_playlist") as create_mock, \
             patch("app.routes.reset.add_tracks_to_playlist") as add_mock, \
             patch("app.routes.reset._ensure_fresh_token", return_value="live-access-token"):

            create_mock.return_value = {
                "id": "real-pl-xyz",
                "name": "Reset Radar - language",
                "external_urls": {
                    "spotify": "https://open.spotify.com/playlist/real-pl-xyz",
                },
            }

            client = TestClient(app)
            r = client.post(
                "/reset/sessions",
                json={
                    "user_id": authed_user,
                    "scope_dimensions": ["language"],
                    "free_text_intent": "expand beyond Telugu",
                },
            )

        assert r.status_code == 200, r.text
        # 1) create_playlist was invoked with the access_token
        create_mock.assert_called_once()
        _, ckwargs = create_mock.call_args
        assert ckwargs["access_token"] == "live-access-token"
        assert ckwargs["name"].startswith("Reset Radar")

        # 2) add_tracks_to_playlist was invoked with the playlist + token + tracks
        add_mock.assert_called_once()
        _, akwargs = add_mock.call_args
        assert akwargs["playlist_id"] == "real-pl-xyz"
        assert akwargs["access_token"] == "live-access-token"
        assert akwargs["track_ids"] == ["rt0", "rt1", "rt2"]

        # 3) The session row was persisted with the REAL playlist id
        body = r.json()
        assert "real-pl-xyz" in body["playlist_url"]

    def test_mock_mode_writes_get_none_access_token(self, monkeypatch, authed_user):
        monkeypatch.setattr(settings, "mock_mode", True)
        ranked = [
            {"spotify_track_id": "t1", "title": "T", "artist": "A", "album": "Alb",
             "genres": [], "language": "en", "era": "2010s", "mood": "chill",
             "score": 0.9, "why": "because", "order_index": 0}
        ]
        with patch("app.routes.reset.generate_reset_playlist", return_value=ranked), \
             patch("app.routes.reset.create_playlist") as create_mock, \
             patch("app.routes.reset.add_tracks_to_playlist") as add_mock:
            create_mock.return_value = {
                "id": "mock-pl",
                "name": "X", "description": "Y",
                "external_urls": {"spotify": "https://open.spotify.com/playlist/mock-pl"},
            }
            client = TestClient(app)
            r = client.post(
                "/reset/sessions",
                json={"user_id": authed_user, "scope_dimensions": ["language"]},
            )
        assert r.status_code == 200
        # In mock mode the writes still get called, but with access_token=None
        assert create_mock.call_args.kwargs["access_token"] is None
        assert add_mock.call_args.kwargs["access_token"] is None


# ============================================================
# Real-mode decide_reset_session
# ============================================================

class TestDecideSessionReal:
    def test_keep_in_real_mode_follows_artists_and_saves_tracks(
        self, monkeypatch, existing_session,
    ):
        monkeypatch.setattr(settings, "mock_mode", False)
        with patch("app.routes.reset.resolve_artist_ids_for_tracks",
                   return_value=["art-a", "art-b", "art-c", "art-d", "art-e"]) as resolve_mock, \
             patch("app.routes.reset.save_to_library") as save_mock, \
             patch("app.routes.reset._ensure_fresh_token", return_value="live-access-token"):
            client = TestClient(app)
            r = client.post(
                f"/reset/sessions/{existing_session}/decide",
                json={"decision": "keep"},
            )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["decision"] == "keep"
        assert out["before_stuck_score"] == 0.82
        assert out["after_stuck_score"] == pytest.approx(0.82 * 0.6, abs=1e-4)

        # Artist follow happened
        resolve_mock.assert_called_once()
        rkwargs = resolve_mock.call_args.kwargs
        assert rkwargs["access_token"] == "live-access-token"
        assert rkwargs["track_ids"] == ["track-0", "track-1", "track-2"]

        # save_to_library should be called BOTH for artists AND tracks
        save_calls = [c.kwargs for c in save_mock.call_args_list]
        item_types = [c["item_type"] for c in save_calls]
        assert "artist" in item_types
        assert "track" in item_types

        artist_call = next(c for c in save_calls if c["item_type"] == "artist")
        assert artist_call["item_ids"] == ["art-a", "art-b", "art-c", "art-d", "art-e"]
        assert artist_call["access_token"] == "live-access-token"

        track_call = next(c for c in save_calls if c["item_type"] == "track")
        assert track_call["item_ids"] == ["track-0", "track-1", "track-2"]

    def test_revert_in_real_mode_unfollows_playlist(
        self, monkeypatch, existing_session,
    ):
        monkeypatch.setattr(settings, "mock_mode", False)
        with patch("app.routes.reset.delete_playlist") as delete_mock, \
             patch("app.routes.reset._ensure_fresh_token", return_value="live-access-token"):
            client = TestClient(app)
            r = client.post(
                f"/reset/sessions/{existing_session}/decide",
                json={"decision": "revert"},
            )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["decision"] == "revert"
        # after_stuck_score unchanged from before (no listening change)
        assert out["after_stuck_score"] == out["before_stuck_score"] == 0.82

        delete_mock.assert_called_once()
        dkwargs = delete_mock.call_args.kwargs
        assert dkwargs["playlist_id"] == "pl-existing-1"
        assert dkwargs["access_token"] == "live-access-token"

    def test_mock_mode_keep_does_not_call_resolve_or_follow(
        self, monkeypatch, existing_session,
    ):
        # In mock mode, the demo personas have no access_token; the
        # _maybe_fresh_token branch returns None, and the writes are
        # no-ops. resolve_artist_ids_for_tracks SHOULD still be called
        # (it short-circuits to [] internally in mock mode) so that the
        # control flow is identical between modes.
        monkeypatch.setattr(settings, "mock_mode", True)
        # Strip the access token off the user to mimic a demo persona.
        with db_session() as db:
            u = db.get(User, "u-real-1")
            u.access_token = None
            db.commit()

        with patch("app.routes.reset.resolve_artist_ids_for_tracks",
                   return_value=[]) as resolve_mock, \
             patch("app.routes.reset.save_to_library") as save_mock:
            client = TestClient(app)
            r = client.post(
                f"/reset/sessions/{existing_session}/decide",
                json={"decision": "keep"},
            )
        assert r.status_code == 200
        # resolve was called (yielded []), so the artist-follow branch
        # was skipped, but track save_to_library still fires.
        resolve_mock.assert_called_once()
        save_calls = [c.kwargs for c in save_mock.call_args_list]
        item_types = [c["item_type"] for c in save_calls]
        assert "artist" not in item_types       # no artists to follow
        assert "track" in item_types

    def test_double_decide_returns_409(self, monkeypatch, existing_session):
        monkeypatch.setattr(settings, "mock_mode", True)
        client = TestClient(app)
        r1 = client.post(
            f"/reset/sessions/{existing_session}/decide",
            json={"decision": "keep"},
        )
        assert r1.status_code == 200
        r2 = client.post(
            f"/reset/sessions/{existing_session}/decide",
            json={"decision": "revert"},
        )
        assert r2.status_code == 409
