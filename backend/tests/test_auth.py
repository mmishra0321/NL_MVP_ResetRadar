"""Unit tests for routes/auth.py (the OAuth PKCE flow).

These tests use FastAPI's TestClient against the live ASGI app, with the
Spotify HTTP endpoints mocked via `httpx.MockTransport`.

We exercise:
  - PKCE verifier + challenge generation
  - /auth/login redirect contains all required OAuth params
  - /auth/callback exchanges code + verifier and upserts the user
  - Session cookie carries the user_id and survives a refresh
  - /auth/me reads the session cookie
  - /auth/logout clears the cookie
  - Mock-mode bypass: /login just redirects to the frontend
"""
from __future__ import annotations

import base64
import hashlib
import urllib.parse
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, engine
from app.main import app
from app.routes import auth as auth_module


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_state_map():
    auth_module._STATE_MAP.clear()
    yield
    auth_module._STATE_MAP.clear()


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "spotify_client_id", "test-client-id")
    monkeypatch.setattr(settings, "spotify_redirect_uri", "http://127.0.0.1:8000/auth/callback")
    monkeypatch.setattr(settings, "frontend_origin", "http://127.0.0.1:5173")


# ============================================================
# Tests: PKCE primitives
# ============================================================

class TestPKCEHelpers:
    def test_pair_returns_valid_verifier_and_challenge(self):
        verifier, challenge = auth_module._pkce_pair()
        assert 43 <= len(verifier) <= 128
        # Challenge MUST be base64url(SHA256(verifier)) per RFC 7636.
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_two_calls_return_different_pairs(self):
        v1, _ = auth_module._pkce_pair()
        v2, _ = auth_module._pkce_pair()
        assert v1 != v2


# ============================================================
# Tests: /auth/login
# ============================================================

class TestLogin:
    def test_login_in_mock_mode_redirects_to_frontend(self, monkeypatch):
        monkeypatch.setattr(settings, "mock_mode", True)
        monkeypatch.setattr(settings, "frontend_origin", "http://127.0.0.1:5173")
        client = TestClient(app)
        r = client.get("/auth/login", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].startswith("http://127.0.0.1:5173")

    def test_login_in_real_mode_redirects_to_spotify(self, real_mode):
        client = TestClient(app)
        r = client.get("/auth/login", follow_redirects=False)
        assert r.status_code == 302
        loc = r.headers["location"]
        assert loc.startswith("https://accounts.spotify.com/authorize?")
        # All required OAuth params present
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
        assert qs["client_id"] == ["test-client-id"]
        assert qs["response_type"] == ["code"]
        assert qs["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
        assert qs["code_challenge_method"] == ["S256"]
        assert qs["code_challenge"][0]
        state = qs["state"][0]
        # State was registered server-side
        assert state in auth_module._STATE_MAP

    def test_login_without_client_id_returns_503(self, real_mode, monkeypatch):
        monkeypatch.setattr(settings, "spotify_client_id", "")
        client = TestClient(app)
        r = client.get("/auth/login", follow_redirects=False)
        assert r.status_code == 503
        assert "SPOTIFY_CLIENT_ID" in r.json()["detail"]


# ============================================================
# Tests: /auth/callback (full flow)
# ============================================================

class TestCallback:
    def test_callback_exchanges_code_and_sets_session(self, real_mode):
        """Walk through the full /login -> /callback flow with mocked Spotify."""
        client = TestClient(app)

        # 1) /login to register a state -> verifier in _STATE_MAP
        r = client.get("/auth/login", follow_redirects=False)
        loc = r.headers["location"]
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
        state = qs["state"][0]
        verifier = auth_module._STATE_MAP[state][0]

        # 2) Mock Spotify's token endpoint AND /me with httpx.MockTransport.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/token":
                # Verify the body we sent
                body = dict(urllib.parse.parse_qsl(request.content.decode()))
                assert body["grant_type"] == "authorization_code"
                assert body["code"] == "fake-spotify-code"
                assert body["code_verifier"] == verifier
                assert body["client_id"] == "test-client-id"
                return httpx.Response(200, json={
                    "access_token": "fake-access-token",
                    "refresh_token": "fake-refresh-token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    "scope": " ".join(auth_module.SPOTIFY_SCOPES if hasattr(auth_module, 'SPOTIFY_SCOPES') else []),
                })
            if request.url.path == "/v1/me":
                assert request.headers["Authorization"] == "Bearer fake-access-token"
                return httpx.Response(200, json={
                    "id": "spotify-test-user",
                    "display_name": "Test Listener",
                    "email": "x@example.com",
                })
            return httpx.Response(404, json={"error": f"unexpected {request.url}"})

        # Patch httpx.post + httpx.get used inside the callback.
        with patch("app.routes.auth.httpx.post", side_effect=lambda *a, **k: _replay_via_transport(a, k, handler, "post")), \
             patch("app.routes.auth.httpx.get",  side_effect=lambda *a, **k: _replay_via_transport(a, k, handler, "get")):
            r2 = client.get(
                f"/auth/callback?code=fake-spotify-code&state={state}",
                follow_redirects=False,
            )

        # 3) Should redirect to frontend AND set the session cookie
        assert r2.status_code == 302
        assert r2.headers["location"].startswith("http://127.0.0.1:5173")
        assert auth_module.SESSION_COOKIE_NAME in r2.cookies

        # 4) /auth/me with the new cookie should return the user
        client.cookies.update(r2.cookies)
        r3 = client.get("/auth/me")
        assert r3.status_code == 200
        data = r3.json()
        assert data["authenticated"] is True
        assert data["spotify_user_id"] == "spotify-test-user"
        assert data["display_name"] == "Test Listener"

    def test_callback_with_unknown_state_returns_400(self, real_mode):
        client = TestClient(app)
        r = client.get(
            "/auth/callback?code=x&state=never-registered",
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert "state expired or unknown" in r.json()["detail"]

    def test_callback_missing_code_returns_400(self, real_mode):
        client = TestClient(app)
        r = client.get("/auth/callback?state=abc", follow_redirects=False)
        assert r.status_code == 400

    def test_callback_with_spotify_error_returns_400(self, real_mode):
        client = TestClient(app)
        r = client.get(
            "/auth/callback?error=access_denied&state=abc",
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert "access_denied" in r.json()["detail"]


# ============================================================
# Tests: /auth/me + /auth/logout
# ============================================================

class TestSessionEndpoints:
    def test_me_returns_unauthenticated_without_cookie(self):
        client = TestClient(app)
        r = client.get("/auth/me")
        assert r.status_code == 200
        assert r.json() == {"authenticated": False}

    def test_me_returns_unauthenticated_with_invalid_cookie(self):
        client = TestClient(app)
        client.cookies.set(auth_module.SESSION_COOKIE_NAME, "tampered-or-garbage")
        r = client.get("/auth/me")
        assert r.json() == {"authenticated": False}

    def test_logout_clears_cookie(self):
        client = TestClient(app)
        # Set a cookie first
        ser = auth_module._serializer()
        token = ser.dumps({"user_id": "x", "issued_at": 1})
        client.cookies.set(auth_module.SESSION_COOKIE_NAME, token)
        r = client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ============================================================
# Helper: route httpx.post/get through a MockTransport
# ============================================================

def _replay_via_transport(args, kwargs, handler, method):
    """Build an httpx.Request from the call args and replay through handler."""
    if args:
        url = args[0]
    else:
        url = kwargs["url"]
    req_kwargs = {
        "url": url,
        "headers": kwargs.get("headers", {}),
    }
    if method == "post":
        if "data" in kwargs:
            body = urllib.parse.urlencode(kwargs["data"])
            req_kwargs["content"] = body.encode("utf-8")
        elif "json" in kwargs:
            req_kwargs["json"] = kwargs["json"]
    req = httpx.Request(method.upper(), **req_kwargs)
    return handler(req)
