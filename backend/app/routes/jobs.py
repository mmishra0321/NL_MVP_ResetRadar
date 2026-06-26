"""Internal job endpoints - invoked by the weekly GH Action.

R1 ships the real mock-mode body of `/jobs/run-weekly-detection`. It:
1. Loads `mock_data/synthetic_weeks.json`
2. For each user, processes all weeks through `detection.process_user_weeks`
3. Persists snapshots + stuck_scores + (where trigger fires) a Nudge
4. Returns a JSON summary {users_processed, snapshots_created,
   scores_computed, nudges_fired, details: [...]}

Idempotency: in mock mode the endpoint is destructive-by-default. It
clears existing rows for the demo users before rebuilding, so the demo
remains predictable across repeated calls. Real-mode behaviour (R4)
will be append-only.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.db import db_session
from app.detection import process_user_weeks, should_trigger_nudge
from app.models import (
    Nudge,
    ResetSession,
    ResetTrack,
    StuckScore,
    User,
    WeeklySnapshot,
)


router = APIRouter()
log = logging.getLogger("reset_radar.jobs")


# ============================================================
# Fixture loader (mock-mode source of truth)
# ============================================================

FIXTURE_PATH: Path = settings.mock_data_dir / "synthetic_weeks.json"


def _load_synthetic_weeks() -> dict[str, Any]:
    if not FIXTURE_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"synthetic_weeks fixture missing at {FIXTURE_PATH}. "
                f"Run `python scripts/generate_synthetic_weeks.py` first."
            ),
        )
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _user_weekly_rows(fixture: dict[str, Any], user_id: str):
    weeks = fixture["weeks"]
    for iso_week in sorted(weeks.keys()):
        snap = next(
            (s for s in weeks[iso_week] if s["user_id"] == user_id), None,
        )
        if snap is None:
            continue
        yield iso_week, snap["tracks"]


def _ensure_user(db, fixture: dict[str, Any], user_id: str) -> User:
    """Upsert a User row from the fixture's `_personas` metadata."""
    user = db.get(User, user_id)
    persona = (fixture.get("_personas") or {}).get(user_id, {})
    display_name = persona.get("display_name", user_id)
    if user is None:
        user = User(
            id=user_id,
            spotify_user_id=None,
            display_name=display_name,
            created_at=datetime.utcnow(),
        )
        db.add(user)
    else:
        user.display_name = display_name
    return user


def _wipe_user_history(db, user_id: str) -> None:
    """Idempotency: clear ALL prior demo data for a user in mock mode.

    Wipes snapshots, scores, nudges, AND reset sessions (incl. their
    tracks). This is mock-mode demo behaviour: every detection run is
    designed to be a fresh start so a presenter can re-run the loop
    repeatedly without state from prior runs blocking the trigger
    (e.g. a half-finished reset session marking `has_active_session=True`
    and silently suppressing nudges).

    Real-mode (R4+) will replace this with append-only weekly snapshots
    and will NOT wipe reset sessions, which represent real user history.
    """
    db.query(WeeklySnapshot).filter(WeeklySnapshot.user_id == user_id).delete()
    db.query(StuckScore).filter(StuckScore.user_id == user_id).delete()
    db.query(Nudge).filter(Nudge.user_id == user_id).delete()
    user_session_ids = [
        s.id for s in db.query(ResetSession).filter(ResetSession.user_id == user_id).all()
    ]
    if user_session_ids:
        db.query(ResetTrack).filter(
            ResetTrack.reset_session_id.in_(user_session_ids)
        ).delete(synchronize_session=False)
        db.query(ResetSession).filter(ResetSession.user_id == user_id).delete()


def _has_active_session(db, user_id: str) -> bool:
    """A reset session is active if it exists with no `decision` yet."""
    return (
        db.query(ResetSession)
        .filter(
            ResetSession.user_id == user_id,
            ResetSession.decision.is_(None),
        )
        .first()
        is not None
    )


# ============================================================
# The endpoint
# ============================================================

@router.post("/run-weekly-detection")
def run_weekly_detection(dry_run: bool = False) -> dict[str, Any]:
    """Recompute stuck scores + fire nudges for every user.

    In mock mode (the R1 default), iterates the synthetic fixture's users
    and replaces their history end-to-end. In real mode (R4+, not yet
    implemented), this endpoint will fetch THIS week's Spotify data for
    every authenticated user and append to existing history.
    """
    if not settings.mock_mode:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Real-Spotify weekly detection lands in R4.",
        )

    fixture = _load_synthetic_weeks()
    user_ids = sorted({
        snap["user_id"]
        for week_snaps in fixture["weeks"].values()
        for snap in week_snaps
    })

    summary: dict[str, Any] = {
        "mock_mode": True,
        "dry_run": dry_run,
        "users_processed": 0,
        "snapshots_created": 0,
        "scores_computed": 0,
        "nudges_fired": 0,
        "details": [],
    }

    with db_session() as db:
        for user_id in user_ids:
            user = _ensure_user(db, fixture, user_id)               # noqa: F841 (registered on session)

            if not dry_run:
                _wipe_user_history(db, user_id)

            rows = list(_user_weekly_rows(fixture, user_id))
            result = process_user_weeks(user_id=user_id, weekly_track_rows=rows)
            snapshots = result["snapshots"]
            scores = result["scores"]

            if not dry_run:
                for snap in snapshots:
                    db.add(WeeklySnapshot(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        iso_week=snap["iso_week"],
                        payload_json=snap,
                        computed_at=datetime.utcnow(),
                    ))
                for score in scores:
                    pd = score["per_dimension"]
                    db.add(StuckScore(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        iso_week=score["iso_week"],
                        genre=pd.genre,
                        language=pd.language,
                        era=pd.era,
                        mood=pd.mood,
                        overall=score["overall"],
                        suggested_scope=score["suggested_scope"],
                        computed_at=datetime.utcnow(),
                    ))

            decision = should_trigger_nudge(
                user_id=user_id,
                recent_scores=scores,
                last_nudge_at=None,                            # fresh-rebuild in mock mode
                has_active_session=_has_active_session(db, user_id),
            )

            nudge_id: str | None = None
            if decision["trigger"] and not dry_run:
                latest = scores[-1]
                pd = latest["per_dimension"]
                nudge_id = str(uuid.uuid4())
                db.add(Nudge(
                    id=nudge_id,
                    user_id=user_id,
                    overall_stuck_score=latest["overall"],
                    suggested_scope=latest["suggested_scope"],
                    status="pending",
                    created_at=datetime.utcnow(),
                ))
                summary["nudges_fired"] += 1

            summary["users_processed"] += 1
            summary["snapshots_created"] += len(snapshots)
            summary["scores_computed"] += len(scores)
            summary["details"].append({
                "user_id": user_id,
                "snapshots": len(snapshots),
                "scores": len(scores),
                "trigger": decision["trigger"],
                "reason": decision["reason"],
                "stuck_streak_weeks": decision["stuck_streak_weeks"],
                "latest_overall": scores[-1]["overall"] if scores else None,
                "latest_suggested_scope": scores[-1]["suggested_scope"] if scores else None,
                "nudge_id": nudge_id,
            })

        if not dry_run:
            db.commit()

    log.info(
        "weekly detection complete | users=%d snapshots=%d scores=%d nudges=%d (dry=%s)",
        summary["users_processed"],
        summary["snapshots_created"],
        summary["scores_computed"],
        summary["nudges_fired"],
        dry_run,
    )
    return summary


__all__ = ["router"]
