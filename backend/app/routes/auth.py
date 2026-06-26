"""Spotify OAuth (PKCE) routes - R0 stub; real impl in R4.

Per architecture.md section 6, this uses the Authorization Code Flow
with PKCE because Reset Radar is a public client (the browser holds
the access token, not a confidential server secret).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status


router = APIRouter()


@router.get("/login")
def login() -> dict[str, str]:
    """Begin the PKCE OAuth flow. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Spotify OAuth login lands in R4.",
    )


@router.get("/callback")
def callback() -> dict[str, str]:
    """Spotify redirects here with the authorization code. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Spotify OAuth callback lands in R4.",
    )


@router.get("/me")
def whoami() -> dict[str, str]:
    """Return the currently authenticated user. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User-session lookup lands in R4.",
    )


__all__ = ["router"]
