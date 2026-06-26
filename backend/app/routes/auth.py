"""Spotify OAuth Authorization Code Flow with PKCE.

Endpoints:
  GET  /auth/login        -> redirect to Spotify consent screen
  GET  /auth/callback     -> exchange code+verifier for tokens, persist
                             user, set session cookie, redirect to frontend
  GET  /auth/me           -> who am I? (reads the session cookie)
  POST /auth/logout       -> clear the session cookie

Why PKCE: Reset Radar is a public client (browser-driven; no
confidential server secret in the OAuth exchange). PKCE protects against
auth-code interception in the redirect. Spotify supports PKCE without a
client_secret in the token exchange, which is what we use.

Session model: after a successful callback we mint a signed session
cookie carrying ONLY the internal user_id (UUID). The Spotify
access/refresh tokens never leave the backend.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings
from app.db import db_session
from app.models import User
from app.spotify_client import (
    SPOTIFY_SCOPES,
    SPOTIFY_TOKEN_URL,
    SpotifyAuthError,
)


log = logging.getLogger("reset_radar.auth")
router = APIRouter()


# ============================================================
# Cookie + state plumbing
# ============================================================

SESSION_COOKIE_NAME = "rr_session"
STATE_TTL_SECONDS = 10 * 60                # how long /login -> /callback may take


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key, salt="reset-radar-session")


def _set_session_cookie(response: Response, user_id: str) -> None:
    token = _serializer().dumps({"user_id": user_id, "issued_at": int(time.time())})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=60 * 60 * 24 * 14,                                     # 14 days
        httponly=True,
        samesite="lax",
        secure=False,                                                  # set True behind HTTPS in R7
    )


def _read_session_cookie(request: Request) -> Optional[str]:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw)
    except BadSignature:
        return None
    uid = data.get("user_id") if isinstance(data, dict) else None
    return uid if isinstance(uid, str) else None


# In-memory state -> (verifier, created_at). Per-process; fine for a
# single-instance demo. A real deploy would Redis-back this.
_STATE_MAP: dict[str, tuple[str, float]] = {}


def _gc_state_map() -> None:
    now = time.time()
    stale = [k for k, (_, ts) in _STATE_MAP.items() if now - ts > STATE_TTL_SECONDS]
    for k in stale:
        _STATE_MAP.pop(k, None)


# ============================================================
# PKCE helpers
# ============================================================

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(64)                                # ~85 chars
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ============================================================
# Endpoints
# ============================================================

@router.get("/login")
def login() -> RedirectResponse:
    """Start the OAuth flow.

    Requires SPOTIFY_CLIENT_ID. We DON'T require SPOTIFY_CLIENT_SECRET
    because PKCE protects the code exchange and Spotify allows
    secretless PKCE for public clients.
    """
    if settings.mock_mode:
        # Honest in-mock-mode behaviour: this endpoint is a no-op redirect
        # back to the frontend. The demo never needs OAuth.
        log.info("/auth/login called in mock mode - redirecting straight to frontend.")
        return RedirectResponse(url=settings.frontend_origin, status_code=302)

    if not settings.spotify_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SPOTIFY_CLIENT_ID is not configured. Add your Spotify Developer "
                "Dashboard app credentials to backend/.env, OR set MOCK_MODE=true "
                "to run the demo without live Spotify integration."
            ),
        )

    _gc_state_map()
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _STATE_MAP[state] = (verifier, time.time())

    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": " ".join(SPOTIFY_SCOPES),
    }
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    log.info("OAuth login redirect -> spotify (state=%s, scopes=%d)", state, len(SPOTIFY_SCOPES))
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Spotify redirects here. Exchange code+verifier for tokens."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Spotify returned error in callback: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback missing required 'code' or 'state' parameter.",
        )

    _gc_state_map()
    entry = _STATE_MAP.pop(state, None)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "OAuth state expired or unknown. Restart the login from "
                "/auth/login (the state token lives 10 minutes)."
            ),
        )
    verifier, _ = entry

    # ---- 1) Exchange code+verifier for tokens ----
    try:
        token_resp = httpx.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
                "client_id": settings.spotify_client_id,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Spotify token endpoint unreachable: {exc}",
        )
    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Spotify token exchange failed ({token_resp.status_code}): {token_resp.text[:300]}",
        )
    tokens = token_resp.json()

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = int(tokens.get("expires_in", 3600))
    token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # ---- 2) Fetch /me to identify the user ----
    try:
        me_resp = httpx.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Spotify /me unreachable: {exc}",
        )
    if me_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Spotify /me failed ({me_resp.status_code}): {me_resp.text[:300]}",
        )
    me = me_resp.json()
    spotify_user_id = me.get("id") or ""
    display_name = me.get("display_name") or spotify_user_id

    # ---- 3) Upsert the User row ----
    with db_session() as db:
        user = (
            db.query(User)
            .filter(User.spotify_user_id == spotify_user_id)
            .first()
        )
        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                spotify_user_id=spotify_user_id,
                display_name=display_name,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                created_at=datetime.utcnow(),
            )
            db.add(user)
        else:
            user.display_name = display_name
            user.access_token = access_token
            if refresh_token:
                user.refresh_token = refresh_token
            user.token_expires_at = token_expires_at
        db.commit()
        user_id = user.id

    log.info("OAuth callback: linked Spotify user %r to internal id %s",
             spotify_user_id, user_id)

    # ---- 4) Set the session cookie + redirect to the frontend ----
    response = RedirectResponse(url=settings.frontend_origin, status_code=302)
    _set_session_cookie(response, user_id)
    return response


@router.get("/me")
def whoami(request: Request) -> dict:
    """Return the currently logged-in user.

    Reads the signed session cookie; if absent or invalid, returns
    `{authenticated: false}` (NOT a 401) so the frontend can render the
    "Login with Spotify" CTA without crashing.
    """
    user_id = _read_session_cookie(request)
    if not user_id:
        return {"authenticated": False}
    with db_session() as db:
        user = db.get(User, user_id)
        if user is None:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "user_id": user.id,
            "spotify_user_id": user.spotify_user_id,
            "display_name": user.display_name,
            "has_active_token": user.access_token is not None,
        }


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    """Clear the session cookie. Doesn't revoke Spotify tokens server-side."""
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


__all__ = [
    "router",
    "SESSION_COOKIE_NAME",
    "_read_session_cookie",
    "_set_session_cookie",
    "_pkce_pair",
    "SpotifyAuthError",
]
