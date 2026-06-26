"""R6 tests for the canonical /jobs/run-detection alias and the
optional Bearer-token authentication that the GitHub Actions workflow
sends in production.

Architecture references:
  - architecture.md §6: POST /jobs/run-detection (canonical name)
  - architecture.md §10: workflow file calls /jobs/run-detection with
    `Authorization: Bearer ${{ secrets.RESET_RADAR_API_TOKEN }}`
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, engine
from app.main import app


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
def client():
    return TestClient(app)


# ============================================================
# Canonical /jobs/run-detection endpoint
# ============================================================

class TestCanonicalAlias:
    def test_canonical_run_detection_exists(self, client):
        """The new canonical name from architecture §6 is registered."""
        schema = app.openapi()
        assert "/jobs/run-detection" in schema["paths"]
        assert "post" in {m.lower() for m in schema["paths"]["/jobs/run-detection"]}

    def test_legacy_run_weekly_detection_still_exists(self, client):
        """R3 frontend's existing call point keeps working (no breaking change)."""
        schema = app.openapi()
        assert "/jobs/run-weekly-detection" in schema["paths"]

    def test_canonical_runs_the_same_handler(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")               # no auth required
        r = client.post("/jobs/run-detection", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mock_mode"] is True
        # Same fields that /run-weekly-detection always returned:
        assert "users_processed" in body
        assert "scores_computed" in body
        assert "nudges_fired" in body

    def test_legacy_alias_returns_identical_shape(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        r1 = client.post("/jobs/run-detection?dry_run=true", json={})
        r2 = client.post("/jobs/run-weekly-detection?dry_run=true", json={})
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both dry runs - no DB writes either way. The exact same keys.
        assert set(r1.json().keys()) == set(r2.json().keys())


# ============================================================
# JOBS_API_TOKEN Bearer auth
# ============================================================

class TestJobsApiTokenAuth:
    """When `JOBS_API_TOKEN` is empty (the default), the endpoint is open.
    When set, callers MUST send a matching `Authorization: Bearer ...`."""

    def test_empty_token_means_no_auth_required(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "")
        r = client.post("/jobs/run-detection?dry_run=true", json={})
        assert r.status_code == 200

    def test_matching_bearer_token_accepted(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "s3cr3t-demo-token")
        r = client.post(
            "/jobs/run-detection?dry_run=true",
            headers={"Authorization": "Bearer s3cr3t-demo-token"},
            json={},
        )
        assert r.status_code == 200, r.text

    def test_missing_authorization_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "s3cr3t-demo-token")
        r = client.post("/jobs/run-detection?dry_run=true", json={})
        assert r.status_code == 401
        assert "Missing" in r.json()["detail"] or "Bearer" in r.json()["detail"]
        # RFC 7235 compliance: WWW-Authenticate header on 401
        assert r.headers.get("www-authenticate", "").lower().startswith("bearer")

    def test_wrong_token_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "s3cr3t-demo-token")
        r = client.post(
            "/jobs/run-detection?dry_run=true",
            headers={"Authorization": "Bearer not-the-right-one"},
            json={},
        )
        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"]

    def test_malformed_authorization_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "s3cr3t-demo-token")
        r = client.post(
            "/jobs/run-detection?dry_run=true",
            headers={"Authorization": "Basic abc:def"},                # not Bearer
            json={},
        )
        assert r.status_code == 401

    def test_case_insensitive_bearer_keyword(self, client, monkeypatch):
        """Authorization scheme is case-insensitive per RFC 7235."""
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "tok")
        r = client.post(
            "/jobs/run-detection?dry_run=true",
            headers={"Authorization": "bearer tok"},                   # lowercase
            json={},
        )
        assert r.status_code == 200

    def test_auth_applies_to_legacy_alias_too(self, client, monkeypatch):
        """Both the canonical name and the legacy name are protected
        once a token is configured - no auth-bypass via the old path."""
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "jobs_api_token", "s3cr3t-demo-token")
        r = client.post("/jobs/run-weekly-detection?dry_run=true", json={})
        assert r.status_code == 401


# ============================================================
# Workflow YAML sanity
# ============================================================

class TestWeeklyDetectionWorkflow:
    """The architecture promises this file exists, points at the right
    endpoint, and uses the architecture's exact cron expression. Catch
    regressions if anyone edits it."""

    WORKFLOW_PATH = (
        Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "weekly-detection.yml"
    )

    def test_workflow_file_exists(self):
        assert self.WORKFLOW_PATH.exists(), (
            f"Expected workflow at {self.WORKFLOW_PATH} per architecture §10"
        )

    def test_workflow_parses_as_valid_yaml(self):
        with self.WORKFLOW_PATH.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        assert isinstance(doc, dict)
        # PyYAML normalises `on:` to the literal True boolean because
        # YAML 1.1 treats `on` as a synonym for true. Accept either key.
        triggers = doc.get(True) or doc.get("on")
        assert triggers is not None, "workflow must declare triggers"
        assert "schedule" in triggers
        assert "workflow_dispatch" in triggers

    def test_cron_matches_architecture_spec(self):
        with self.WORKFLOW_PATH.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        triggers = doc.get(True) or doc.get("on")
        cron = triggers["schedule"][0]["cron"]
        assert cron == "0 9 * * 1", (
            f"architecture.md §10 specifies Mondays 09:00 UTC ('0 9 * * 1'); "
            f"workflow declares {cron!r}"
        )

    def test_workflow_calls_canonical_endpoint(self):
        text = self.WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "/jobs/run-detection" in text
        # And uses Bearer auth per architecture §10:
        assert "Authorization: Bearer" in text
        # And references the architecture-mandated secret names:
        assert "RESET_RADAR_API_URL" in text
        assert "RESET_RADAR_API_TOKEN" in text
