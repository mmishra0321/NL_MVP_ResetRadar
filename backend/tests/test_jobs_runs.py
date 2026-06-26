"""R8 tests: JobRun persistence + /jobs/runs endpoints + hybrid mode."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, db_session, engine
from app.main import app
from app.models import JobRun, User


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================
# JobRun is written after every (non-dry) detection run
# ============================================================

class TestJobRunPersistence:
    def test_mock_run_persists_a_jobrun_row(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        r = client.post("/jobs/run-detection", json={})
        assert r.status_code == 200
        with db_session() as db:
            rows = db.query(JobRun).all()
            assert len(rows) == 1
            jr = rows[0]
            assert jr.mode in ("mock", "hybrid")
            assert jr.users_processed >= 2                          # both demo personas
            assert jr.nudges_fired == 2                             # both should trigger
            assert len(jr.details_json) >= 2
            for d in jr.details_json[:2]:
                assert "reason" in d
                assert "stuck_streak_weeks" in d
                assert "latest_overall" in d

    def test_dry_run_does_NOT_persist(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        r = client.post("/jobs/run-detection?dry_run=true", json={})
        assert r.status_code == 200
        with db_session() as db:
            assert db.query(JobRun).count() == 0


# ============================================================
# Query endpoints
# ============================================================

class TestRunQueryEndpoints:
    def test_last_returns_none_when_no_runs(self, client):
        r = client.get("/jobs/runs/last")
        assert r.status_code == 200
        assert r.json() == {"found": False}

    def test_list_returns_empty_when_no_runs(self, client):
        r = client.get("/jobs/runs")
        assert r.status_code == 200
        assert r.json() == {"count": 0, "runs": []}

    def test_full_run_then_last_returns_summary(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        client.post("/jobs/run-detection", json={})
        r = client.get("/jobs/runs/last")
        body = r.json()
        assert body["found"] is True
        assert body["users_processed"] >= 2
        assert body["nudges_fired"] == 2
        assert body["mode"] in ("mock", "hybrid")
        assert body["duration_ms"] is not None and body["duration_ms"] >= 0
        assert isinstance(body["details"], list) and len(body["details"]) >= 2

    def test_list_returns_runs_newest_first(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        # Two distinct runs
        client.post("/jobs/run-detection", json={})
        client.post("/jobs/run-detection", json={})

        r = client.get("/jobs/runs?limit=10")
        body = r.json()
        assert body["count"] == 2
        ts0 = body["runs"][0]["completed_at"]
        ts1 = body["runs"][1]["completed_at"]
        assert ts0 >= ts1                                            # newest first

    def test_list_respects_limit(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        for _ in range(3):
            client.post("/jobs/run-detection", json={})
        r = client.get("/jobs/runs?limit=2")
        assert r.json()["count"] == 2

    def test_list_view_excludes_full_details(self, client, monkeypatch):
        """List view is summary-only; full details only on GET /runs/{id}."""
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        client.post("/jobs/run-detection", json={})
        r = client.get("/jobs/runs")
        assert "details" not in r.json()["runs"][0]

    def test_get_run_by_id_returns_full_trace(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        client.post("/jobs/run-detection", json={})
        run_id = client.get("/jobs/runs?limit=1").json()["runs"][0]["id"]

        r = client.get(f"/jobs/runs/{run_id}")
        body = r.json()
        assert body["id"] == run_id
        assert isinstance(body["details"], list)
        assert len(body["details"]) >= 2                             # per-user trace present

    def test_get_run_by_id_unknown_returns_404(self, client):
        r = client.get("/jobs/runs/does-not-exist")
        assert r.status_code == 404


# ============================================================
# Hybrid mode (R8)
# ============================================================

class TestHybridMode:
    """When MOCK_MODE=true AND an OAuth-authenticated user exists in
    the DB, the same detection run should fold the real user in as
    well, so the dashboard transitions cleanly when someone logs in."""

    def test_no_oauth_users_stays_mock(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        r = client.post("/jobs/run-detection", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "mock"
        assert "real_users_in_hybrid" not in body

    def test_oauth_user_present_folds_into_hybrid(self, client, monkeypatch):
        """A User row with access_token != NULL triggers the hybrid
        path. We mock the actual Spotify fetcher so the test runs
        offline + deterministically."""
        # Seed an OAuth-shaped user
        with db_session() as db:
            db.add(User(
                id="oauth-user-001",
                spotify_user_id="spotify:user:test",
                display_name="Real Spotify User",
                access_token="dummy-token",
                refresh_token="dummy-refresh",
                token_expires_at=datetime.utcnow() + timedelta(hours=1),
            ))
            db.commit()

        # Mock the Spotify snapshot fetcher so real-mode produces a
        # benign payload without hitting any HTTP.
        from app import spotify_client as spc

        def _fake_snapshot(*, user_id, iso_week, user_record):
            return {
                "iso_week": iso_week,
                "tracks": [
                    {"id": "trk1", "name": "T", "artist": "A",
                     "genre": "indie", "language": "en", "era": "2020s",
                     "mood": "chill"},
                ],
            }

        monkeypatch.setattr(spc, "fetch_recent_snapshot", _fake_snapshot)
        monkeypatch.setattr("app.routes.jobs.fetch_recent_snapshot", _fake_snapshot)
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")

        r = client.post("/jobs/run-detection", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "hybrid"
        assert body["real_users_in_hybrid"] == 1
        # Hybrid summary's details should include BOTH the 2 demo
        # personas AND the OAuth user
        user_ids_in_trace = {d.get("user_id") for d in body["details"] if d.get("user_id")}
        assert "oauth-user-001" in user_ids_in_trace
        assert "demo-karthik-001" in user_ids_in_trace
        assert "demo-aanya-002" in user_ids_in_trace

    def test_hybrid_real_pass_failure_is_non_fatal(self, client, monkeypatch):
        """If the real-mode pass throws (e.g. Spotify outage), the mock
        side of the run still returns 200 - the dashboard never has to
        choose between 'demo broken' and 'real broken'."""
        with db_session() as db:
            db.add(User(
                id="oauth-user-002", access_token="t",
                token_expires_at=datetime.utcnow() + timedelta(hours=1),
            ))
            db.commit()

        def _boom(*a, **kw):
            raise RuntimeError("simulated Spotify outage")
        monkeypatch.setattr("app.routes.jobs.fetch_recent_snapshot", _boom)
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")

        r = client.post("/jobs/run-detection", json={})
        assert r.status_code == 200
        body = r.json()
        # Real-mode pass swallows its own per-user errors (see _run_real_mode
        # exception handlers), so the hybrid summary still completes.
        # The OAuth user is processed but with `error: ...` in its trace.
        oauth_trace = [
            d for d in body["details"] if d.get("user_id") == "oauth-user-002"
        ]
        assert len(oauth_trace) == 1
        assert "error" in oauth_trace[0]
