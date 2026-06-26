"""Nudge endpoints - latest active nudge per user + accept/dismiss.

R1 ships real bodies for `/nudges/latest` and `/nudges/{id}/respond`.
The frontend Dashboard (R3) calls `/nudges/latest` once per page load
and renders the active nudge card if one exists.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import desc

from app.db import db_session
from app.models import (
    Nudge,
    NudgeOut,
    NudgeResponseIn,
    ScopeDimension,
    StuckScore,
    StuckScoresPerDimension,
)


router = APIRouter()


# ============================================================
# Helpers
# ============================================================

def _build_nudge_out(db, nudge: Nudge) -> NudgeOut:
    """Combine a Nudge row + the user's latest StuckScore into a NudgeOut."""
    score = (
        db.query(StuckScore)
        .filter(StuckScore.user_id == nudge.user_id)
        .order_by(desc(StuckScore.iso_week))
        .first()
    )
    per_dim = (
        StuckScoresPerDimension(
            genre=score.genre,
            language=score.language,
            era=score.era,
            mood=score.mood,
        )
        if score is not None
        else StuckScoresPerDimension(genre=0.0, language=0.0, era=0.0, mood=0.0)
    )
    return NudgeOut(
        id=nudge.id,
        user_id=nudge.user_id,
        overall_stuck_score=nudge.overall_stuck_score,
        per_dimension=per_dim,
        suggested_scope=_coerce_scope(nudge.suggested_scope),
        status=nudge.status,
        created_at=nudge.created_at,
    )


def _coerce_scope(value: str) -> ScopeDimension:
    if value in {"genre", "language", "era", "mood"}:
        return value                                              # type: ignore[return-value]
    # Defensive fallback - this should never trigger if jobs.py is the
    # only writer, since `process_user_weeks` always returns a valid
    # dimension. Logged as a warning would be nicer but the route layer
    # stays lean.
    return "genre"                                                # type: ignore[return-value]


# ============================================================
# Endpoints
# ============================================================

@router.get("/latest", response_model=Optional[NudgeOut])
def get_latest_nudge(user_id: str) -> Optional[NudgeOut]:
    """Return the most recent pending nudge for `user_id`, or None.

    "Pending" specifically - accepted and dismissed nudges are filtered
    out so the dashboard doesn't repeatedly surface stale nudges.
    """
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id query parameter is required",
        )
    with db_session() as db:
        nudge = (
            db.query(Nudge)
            .filter(Nudge.user_id == user_id, Nudge.status == "pending")
            .order_by(desc(Nudge.created_at))
            .first()
        )
        if nudge is None:
            return None
        return _build_nudge_out(db, nudge)


@router.post("/{nudge_id}/respond", response_model=NudgeOut)
def respond_to_nudge(nudge_id: str, body: NudgeResponseIn) -> NudgeOut:
    """Mark a nudge as accepted or dismissed.

    R1 just records the decision. R3 (frontend) chains "accept" -> POST
    /reset/sessions to open the reset flow; "dismiss" is a no-op beyond
    closing the nudge card.
    """
    with db_session() as db:
        nudge = db.get(Nudge, nudge_id)
        if nudge is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"nudge {nudge_id} not found",
            )
        if nudge.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"nudge already in status {nudge.status!r}",
            )

        nudge.status = "accepted" if body.action == "accept" else "dismissed"
        nudge.responded_at = datetime.utcnow()
        db.commit()
        db.refresh(nudge)
        return _build_nudge_out(db, nudge)


__all__ = ["router"]
