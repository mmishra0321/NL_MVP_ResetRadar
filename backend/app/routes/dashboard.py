"""Read-only dashboard endpoints consumed by the frontend.

Adds the two endpoints R3 needs to populate the dashboard:
  GET /users                          - list known users for the persona picker
  GET /scores/history?user_id=...     - per-dimension weekly score timeline

These are derived views over data already produced by `routes/jobs.py`.
They never mutate state.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import asc

from app.db import db_session
from app.models import StuckScore, User


router = APIRouter()


# ============================================================
# Response shapes
# ============================================================

class UserOut(BaseModel):
    id: str
    display_name: Optional[str] = None


class ScoreHistoryRow(BaseModel):
    iso_week: str
    genre: float
    language: float
    era: float
    mood: float
    overall: float
    suggested_scope: str


class ScoreHistoryOut(BaseModel):
    user_id: str
    weeks: list[ScoreHistoryRow]


# ============================================================
# Endpoints
# ============================================================

@router.get("/users", response_model=list[UserOut], tags=["dashboard"])
def list_users() -> list[UserOut]:
    """List all seeded users, alphabetised by display_name then id.

    In mock mode, the demo personas (`demo-karthik-001`, `demo-aanya-002`)
    show up after `/jobs/run-weekly-detection` has been called once.
    """
    with db_session() as db:
        rows = db.query(User).all()
        users = [
            UserOut(id=u.id, display_name=u.display_name or u.id)
            for u in rows
        ]
        users.sort(key=lambda u: (u.display_name or "", u.id))
        return users


@router.get("/scores/history", response_model=ScoreHistoryOut, tags=["dashboard"])
def get_score_history(user_id: str) -> ScoreHistoryOut:
    """Return the per-dimension weekly stuck-score timeline for a user.

    Ordered ascending by ISO week so the frontend chart can plot
    left-to-right without re-sorting. Returns an empty `weeks` list if
    the user has no scores yet (the frontend shows the empty-state).
    """
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id query parameter is required",
        )
    with db_session() as db:
        if db.get(User, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"user {user_id!r} not found",
            )
        rows = (
            db.query(StuckScore)
            .filter(StuckScore.user_id == user_id)
            .order_by(asc(StuckScore.iso_week))
            .all()
        )
        return ScoreHistoryOut(
            user_id=user_id,
            weeks=[
                ScoreHistoryRow(
                    iso_week=r.iso_week,
                    genre=r.genre,
                    language=r.language,
                    era=r.era,
                    mood=r.mood,
                    overall=r.overall,
                    suggested_scope=r.suggested_scope,
                )
                for r in rows
            ],
        )


__all__ = ["router"]
