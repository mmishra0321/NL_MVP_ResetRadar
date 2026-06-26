"""Database models + Pydantic shapes for the Reset Radar backend.

This file defines BOTH:
1. SQLAlchemy ORM models (the persisted shape) - inherit from `Base`
2. Pydantic models (the wire shape used by FastAPI routes)

Per architecture.md section 7 (Database tables) - 6 tables total:
users, weekly_snapshots, stuck_scores, nudges, reset_sessions, reset_tracks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# ============================================================
# Type aliases for clarity
# ============================================================

NudgeStatus = Literal["pending", "accepted", "dismissed", "expired"]
ResetDecision = Literal["keep", "revert"]
ScopeDimension = Literal["genre", "language", "era", "mood"]


# ============================================================
# SQLAlchemy ORM models (persistence layer)
# ============================================================

def _utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    spotify_user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class WeeklySnapshot(Base):
    __tablename__ = "weekly_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    iso_week: Mapped[str] = mapped_column(String, nullable=False)       # "2026-W26"
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)    # per-dimension distributions
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class StuckScore(Base):
    __tablename__ = "stuck_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    iso_week: Mapped[str] = mapped_column(String, nullable=False)
    genre: Mapped[float] = mapped_column(Float, nullable=False)
    language: Mapped[float] = mapped_column(Float, nullable=False)
    era: Mapped[float] = mapped_column(Float, nullable=False)
    mood: Mapped[float] = mapped_column(Float, nullable=False)
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_scope: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class Nudge(Base):
    __tablename__ = "nudges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    overall_stuck_score: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_scope: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ResetSession(Base):
    __tablename__ = "reset_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    nudge_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("nudges.id"), nullable=True)
    scope_dimensions_json: Mapped[list] = mapped_column(JSON, nullable=False)
    free_text_intent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    spotify_playlist_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trial_end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    before_stuck_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    after_stuck_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tracks: Mapped[list["ResetTrack"]] = relationship(
        "ResetTrack", back_populates="reset_session", cascade="all, delete-orphan",
    )


class JobRun(Base):
    """One row per `POST /jobs/run-detection` call (R8).

    Captures the full structured summary the detection job already
    returns, so the frontend can show a transparent timeline of
    "what the cron did on Monday".

    `details_json` mirrors the existing `summary["details"]` shape
    exactly - per-user reason / stuck_streak_weeks / latest_overall /
    latest_suggested_scope / nudge_id / (real-mode) any fetch errors.
    """
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)            # "mock" | "real" | "hybrid"
    dry_run: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger_source: Mapped[str] = mapped_column(String, default="manual", nullable=False)  # "manual" | "cron"
    users_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshots_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scores_computed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nudges_fired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[list] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ResetTrack(Base):
    __tablename__ = "reset_tracks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    reset_session_id: Mapped[str] = mapped_column(
        String, ForeignKey("reset_sessions.id"), nullable=False,
    )
    spotify_track_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    artist: Mapped[str] = mapped_column(String, nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    era: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    llm_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    llm_explanation: Mapped[str] = mapped_column(String, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    reset_session: Mapped[ResetSession] = relationship("ResetSession", back_populates="tracks")


# ============================================================
# Pydantic models (wire shapes - API request/response bodies)
# ============================================================

class StuckScoresPerDimension(BaseModel):
    genre: float = Field(ge=0.0, le=1.0)
    language: float = Field(ge=0.0, le=1.0)
    era: float = Field(ge=0.0, le=1.0)
    mood: float = Field(ge=0.0, le=1.0)


class NudgeOut(BaseModel):
    id: str
    user_id: str
    overall_stuck_score: float = Field(ge=0.0, le=1.0)
    per_dimension: StuckScoresPerDimension
    suggested_scope: ScopeDimension
    status: NudgeStatus
    created_at: datetime


class NudgeResponseIn(BaseModel):
    action: Literal["dismiss", "accept"]


class ResetSessionIn(BaseModel):
    user_id: str
    scope_dimensions: list[ScopeDimension] = Field(min_length=1)
    free_text_intent: Optional[str] = Field(default=None, max_length=400)


class ResetTrackOut(BaseModel):
    spotify_track_id: str
    title: str
    artist: str
    album: Optional[str] = None
    why: str = Field(max_length=200)
    order_index: int


class ResetSessionOut(BaseModel):
    id: str
    user_id: str
    scope_dimensions: list[ScopeDimension]
    free_text_intent: Optional[str] = None
    playlist_url: Optional[str] = None
    trial_end_date: datetime
    decision: Optional[ResetDecision] = None
    tracks: list[ResetTrackOut]
    created_at: datetime


class ResetDecisionIn(BaseModel):
    decision: ResetDecision


class ResetOutcomeOut(BaseModel):
    session_id: str
    before_stuck_score: Optional[float] = None
    after_stuck_score: Optional[float] = None
    decision: Optional[ResetDecision] = None


__all__ = [
    "User",
    "WeeklySnapshot",
    "StuckScore",
    "Nudge",
    "JobRun",
    "ResetSession",
    "ResetTrack",
    "StuckScoresPerDimension",
    "NudgeOut",
    "NudgeResponseIn",
    "ResetSessionIn",
    "ResetTrackOut",
    "ResetSessionOut",
    "ResetDecisionIn",
    "ResetOutcomeOut",
    "NudgeStatus",
    "ResetDecision",
    "ScopeDimension",
]
