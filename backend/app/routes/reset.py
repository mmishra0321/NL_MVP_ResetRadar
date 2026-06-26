"""Reset session endpoints - create, fetch, decide.

R0 stub - real impl in R2 (generation) + R5 (real Spotify playlist write).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models import (
    ResetDecisionIn,
    ResetOutcomeOut,
    ResetSessionIn,
    ResetSessionOut,
)


router = APIRouter()


@router.post("/sessions", response_model=ResetSessionOut)
def create_reset_session(body: ResetSessionIn) -> ResetSessionOut:
    """Begin a reset session: build playlist, persist, return tracks. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Reset session creation lands in R2.",
    )


@router.get("/sessions/{session_id}", response_model=ResetSessionOut)
def get_reset_session(session_id: str) -> ResetSessionOut:
    """Fetch an active reset session. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Reset session fetch lands in R2.",
    )


@router.post("/sessions/{session_id}/decide", response_model=ResetOutcomeOut)
def decide_reset_session(session_id: str, body: ResetDecisionIn) -> ResetOutcomeOut:
    """Apply the Keep / Revert decision after the trial. R0 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Keep/Revert handler lands in R5.",
    )


__all__ = ["router"]
