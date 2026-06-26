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

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import asc, desc

from app.config import settings
from app.db import db_session
from app.detection import process_user_weeks, should_trigger_nudge
from app.models import (
    JobRun,
    Nudge,
    ResetSession,
    ResetTrack,
    StuckScore,
    User,
    WeeklySnapshot,
)
from app.spotify_client import SpotifyAuthError, fetch_recent_snapshot


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
# Auth dependency (used by the GH Action workflow in R6+)
# ============================================================

def require_jobs_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Enforce `Authorization: Bearer <JOBS_API_TOKEN>` when JOBS_API_TOKEN is set.

    When `settings.jobs_api_token` is empty (the default for local dev
    and the live mock-mode demo), this dependency passes through with
    no enforcement, so the Dashboard's "Run detection now" button keeps
    working without any token.

    When the env var IS set (production deploys behind a public URL),
    requests without a matching Bearer token receive a 401. The GitHub
    Actions workflow (`.github/workflows/weekly-detection.yml`) sends
    the matching token from `secrets.RESET_RADAR_API_TOKEN`.
    """
    expected = settings.jobs_api_token
    if not expected:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.split(None, 1)[1].strip()
    if presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid jobs API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================
# Endpoints
#
# `/run-detection` is the canonical name per architecture §6 + §10
# (the workflow file). `/run-weekly-detection` is kept as a backward-
# compat alias so the R3 frontend's existing "Run detection now"
# button keeps working without any client-side change.
# ============================================================

@router.post(
    "/run-detection",
    dependencies=[Depends(require_jobs_token)],
)
@router.post(
    "/run-weekly-detection",
    dependencies=[Depends(require_jobs_token)],
)
def run_weekly_detection(
    dry_run: bool = False,
    trigger_source: str = "manual",
) -> dict[str, Any]:
    """Recompute stuck scores + fire nudges for every user.

    Mock mode: iterates the synthetic fixture's users, wipes any prior
    demo state, replays 8 weeks of data through detection. **R8 hybrid
    extension:** if there are also OAuth-authenticated users in the DB,
    each one is appended to the same run in real-mode (`fetch + persist
    + score + maybe-nudge`), so the dashboard transitions cleanly when
    a user logs in without flipping the backend's MOCK_MODE flag.

    Real mode (R4+): iterates users with valid Spotify access tokens,
    appends THIS week's snapshot, recomputes stuck scores across the
    user's accumulated history, fires a nudge if the trigger rule passes
    (respecting cooldown).

    Every run is persisted as a `JobRun` row (R8) so the frontend can
    render a transparent run history with per-user step traces.
    """
    started_at = datetime.utcnow()

    if not settings.mock_mode:
        summary = _run_real_mode(dry_run=dry_run)
        _record_job_run(summary, mode="real",
                        trigger_source=trigger_source, started_at=started_at)
        return summary

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

    # === R8 hybrid extension =====================================
    # If we're nominally in mock mode but real OAuth users exist, run
    # the real-mode loop for them too and fold the results into the
    # same summary. The dashboard sees one unified run.
    hybrid_real_summary: dict[str, Any] | None = None
    try:
        hybrid_real_summary = _run_real_mode(dry_run=dry_run, allow_empty=True)
    except Exception as exc:                                            # noqa: BLE001
        log.warning("hybrid real-mode pass failed (non-fatal): %s", exc)
        hybrid_real_summary = None

    real_details = (hybrid_real_summary or {}).get("details", [])
    real_users_seen = sum(1 for d in real_details if d.get("user_id"))
    if hybrid_real_summary and real_users_seen > 0:
        # Some OAuth users were considered (successful OR errored).
        # Fold their traces into the summary so the run-detail view
        # can show what happened for each of them.
        summary["mode"] = "hybrid"
        summary["users_processed"] += hybrid_real_summary["users_processed"]
        summary["snapshots_created"] += hybrid_real_summary["snapshots_created"]
        summary["scores_computed"] += hybrid_real_summary["scores_computed"]
        summary["nudges_fired"] += hybrid_real_summary["nudges_fired"]
        summary["details"].extend(real_details)
        summary["real_users_in_hybrid"] = real_users_seen
    else:
        summary["mode"] = "mock"

    log.info(
        "weekly detection complete | mode=%s users=%d snapshots=%d scores=%d nudges=%d (dry=%s)",
        summary["mode"],
        summary["users_processed"],
        summary["snapshots_created"],
        summary["scores_computed"],
        summary["nudges_fired"],
        dry_run,
    )

    _record_job_run(summary, mode=summary["mode"],
                    trigger_source=trigger_source, started_at=started_at)
    return summary


# ============================================================
# JobRun persistence (R8)
# ============================================================

def _record_job_run(
    summary: dict[str, Any],
    *,
    mode: str,
    trigger_source: str,
    started_at: datetime,
) -> str | None:
    """Persist one row capturing this detection call's full trace.

    Returns the job_run id (UUID) on success, or None if dry_run was
    set (we still want dry runs to come back successfully but we
    don't want them polluting the run history).
    """
    if summary.get("dry_run"):
        return None
    job_id = str(uuid.uuid4())
    try:
        with db_session() as db:
            db.add(JobRun(
                id=job_id,
                mode=mode,
                dry_run=0,
                trigger_source=trigger_source,
                users_processed=int(summary.get("users_processed", 0)),
                snapshots_created=int(summary.get("snapshots_created", 0)),
                scores_computed=int(summary.get("scores_computed", 0)),
                nudges_fired=int(summary.get("nudges_fired", 0)),
                details_json=summary.get("details", []),
                started_at=started_at,
                completed_at=datetime.utcnow(),
            ))
            db.commit()
    except Exception as exc:                                            # noqa: BLE001
        log.warning("failed to persist JobRun (non-fatal): %s", exc)
        return None
    return job_id


# ============================================================
# Real-mode runner (R4)
# ============================================================

def _run_real_mode(*, dry_run: bool, allow_empty: bool = False) -> dict[str, Any]:
    """Per-user real-Spotify weekly snapshot + detection.

    For each user with a non-null `access_token`:
      1. Determine the current ISO week.
      2. Skip if a snapshot for that week already exists (idempotent
         re-runs by the cron).
      3. Fetch a fresh snapshot via spotify_client.fetch_recent_snapshot.
      4. Persist WeeklySnapshot.
      5. Load the user's full snapshot history.
      6. Recompute StuckScore rows for every week (cheap; ensures the
         normalisation against trailing history stays accurate as new
         weeks land).
      7. Evaluate the trigger rule; fire a Nudge if it passes AND the
         cooldown is over AND no active reset session exists.
    """
    summary: dict[str, Any] = {
        "mock_mode": False,
        "dry_run": dry_run,
        "users_processed": 0,
        "snapshots_created": 0,
        "scores_computed": 0,
        "nudges_fired": 0,
        "details": [],
    }
    now = datetime.utcnow()
    this_week = _iso_week(now)

    with db_session() as db:
        users = db.query(User).filter(User.access_token.isnot(None)).all()
        if not users:
            if allow_empty:
                # R8 hybrid call: silently return an empty summary so the
                # caller can detect "no OAuth users to fold in" without
                # the mock-mode summary getting a noisy `reason` row.
                return summary
            summary["details"].append({
                "reason": "no authenticated users; complete /auth/login first.",
            })
            return summary

        for user in users:
            entry: dict[str, Any] = {"user_id": user.id, "this_week": this_week}

            # 2) Skip if this week is already recorded.
            existing = (
                db.query(WeeklySnapshot)
                .filter(
                    WeeklySnapshot.user_id == user.id,
                    WeeklySnapshot.iso_week == this_week,
                )
                .first()
            )
            if existing and not dry_run:
                entry["skipped"] = "snapshot for this week already exists"
                # Still recompute scores below in case detection logic changed.
            else:
                # 3-4) Fetch + persist this week's snapshot.
                try:
                    snap = fetch_recent_snapshot(
                        user_id=user.id,
                        iso_week=this_week,
                        user_record=user,
                    )
                except SpotifyAuthError as exc:
                    entry["error"] = f"auth: {exc}"
                    summary["details"].append(entry)
                    continue
                except Exception as exc:                                   # noqa: BLE001
                    log.exception("fetch_recent_snapshot failed for %s", user.id)
                    entry["error"] = f"fetch failed: {exc}"
                    summary["details"].append(entry)
                    continue

                if not dry_run:
                    db.add(WeeklySnapshot(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        iso_week=this_week,
                        payload_json=snap,
                        computed_at=now,
                    ))
                    db.flush()                                              # so step 5 sees the new row
                    summary["snapshots_created"] += 1

            # 5) Load full history (oldest -> newest).
            rows = (
                db.query(WeeklySnapshot)
                .filter(WeeklySnapshot.user_id == user.id)
                .order_by(asc(WeeklySnapshot.iso_week))
                .all()
            )
            weekly_track_rows = [
                (r.iso_week, (r.payload_json or {}).get("tracks") or [])
                for r in rows
            ]
            if not weekly_track_rows:
                entry["note"] = "no history yet; trigger evaluation skipped."
                summary["details"].append(entry)
                continue

            # 6) Recompute stuck scores for all weeks.
            result = process_user_weeks(
                user_id=user.id, weekly_track_rows=weekly_track_rows,
            )
            scores = result["scores"]
            if not dry_run:
                db.query(StuckScore).filter(StuckScore.user_id == user.id).delete()
                for s in scores:
                    pd = s["per_dimension"]
                    db.add(StuckScore(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        iso_week=s["iso_week"],
                        genre=pd.genre, language=pd.language,
                        era=pd.era, mood=pd.mood,
                        overall=s["overall"],
                        suggested_scope=s["suggested_scope"],
                        computed_at=now,
                    ))
                summary["scores_computed"] += len(scores)

            # 7) Trigger evaluation (with real cooldown lookup).
            last_nudge = (
                db.query(Nudge)
                .filter(Nudge.user_id == user.id)
                .order_by(desc(Nudge.created_at))
                .first()
            )
            decision = should_trigger_nudge(
                user_id=user.id,
                recent_scores=scores,
                last_nudge_at=last_nudge.created_at if last_nudge else None,
                has_active_session=_has_active_session(db, user.id),
            )
            entry["trigger"] = decision["trigger"]
            entry["reason"] = decision["reason"]
            entry["stuck_streak_weeks"] = decision["stuck_streak_weeks"]
            entry["latest_overall"] = scores[-1]["overall"] if scores else None
            entry["latest_suggested_scope"] = scores[-1]["suggested_scope"] if scores else None

            if decision["trigger"] and not dry_run:
                latest = scores[-1]
                nudge_id = str(uuid.uuid4())
                db.add(Nudge(
                    id=nudge_id,
                    user_id=user.id,
                    overall_stuck_score=latest["overall"],
                    suggested_scope=latest["suggested_scope"],
                    status="pending",
                    created_at=now,
                ))
                summary["nudges_fired"] += 1
                entry["nudge_id"] = nudge_id

            summary["users_processed"] += 1
            summary["details"].append(entry)

        if not dry_run:
            db.commit()

    log.info(
        "[real-mode] weekly detection complete | users=%d snapshots=%d scores=%d nudges=%d (dry=%s)",
        summary["users_processed"],
        summary["snapshots_created"],
        summary["scores_computed"],
        summary["nudges_fired"],
        dry_run,
    )
    return summary


def _iso_week(dt: datetime) -> str:
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


# ============================================================
# JobRun query endpoints (R8) - public, read-only
# ============================================================


def _utc_iso(dt: datetime | None) -> str | None:
    """Serialise a naive-UTC datetime as a Z-suffixed ISO 8601 string.

    SQLite + SQLAlchemy give us back naive datetimes from `_utcnow()`
    (which is `datetime.utcnow()`). Browsers parse naive ISO strings
    as local time, which manifests on the frontend as an N-hour skew
    in 'X ago' labels. Appending the Z removes the ambiguity.
    """
    if dt is None:
        return None
    return dt.isoformat() + "Z"


def _job_run_to_dict(jr: JobRun) -> dict[str, Any]:
    return {
        "id": jr.id,
        "mode": jr.mode,
        "dry_run": bool(jr.dry_run),
        "trigger_source": jr.trigger_source,
        "users_processed": jr.users_processed,
        "snapshots_created": jr.snapshots_created,
        "scores_computed": jr.scores_computed,
        "nudges_fired": jr.nudges_fired,
        "details": jr.details_json or [],
        "started_at": _utc_iso(jr.started_at),
        "completed_at": _utc_iso(jr.completed_at),
        "duration_ms": (
            int((jr.completed_at - jr.started_at).total_seconds() * 1000)
            if jr.started_at and jr.completed_at
            else None
        ),
    }


@router.get("/runs")
def list_job_runs(limit: int = 20) -> dict[str, Any]:
    """List the most recent JobRun rows for the run-history view."""
    limit = max(1, min(limit, 100))
    with db_session() as db:
        rows = (
            db.query(JobRun)
            .order_by(desc(JobRun.completed_at))
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "runs": [
                {
                    # list view = summary only, no full details_json
                    "id": r.id,
                    "mode": r.mode,
                    "trigger_source": r.trigger_source,
                    "users_processed": r.users_processed,
                    "snapshots_created": r.snapshots_created,
                    "scores_computed": r.scores_computed,
                    "nudges_fired": r.nudges_fired,
                    "started_at": _utc_iso(r.started_at),
                    "completed_at": _utc_iso(r.completed_at),
                    "duration_ms": (
                        int((r.completed_at - r.started_at).total_seconds() * 1000)
                        if r.started_at and r.completed_at
                        else None
                    ),
                }
                for r in rows
            ],
        }


@router.get("/runs/last")
def last_job_run() -> dict[str, Any] | None:
    """Compact summary of the most recent JobRun (Dashboard card)."""
    with db_session() as db:
        jr = (
            db.query(JobRun)
            .order_by(desc(JobRun.completed_at))
            .first()
        )
        if jr is None:
            return {"found": False}
        d = _job_run_to_dict(jr)
        d["found"] = True
        return d


@router.get("/runs/{run_id}")
def get_job_run(run_id: str) -> dict[str, Any]:
    """Full structured trace for one JobRun (run-detail expandable view).

    The `details` array carries one entry per processed user with
    `reason`, `stuck_streak_weeks`, `latest_overall`,
    `latest_suggested_scope`, and (if fired) `nudge_id`. The frontend
    renders this as the 4-step trace: load -> formulas -> trigger -> nudge.
    """
    with db_session() as db:
        jr = db.get(JobRun, run_id)
        if jr is None:
            raise HTTPException(status_code=404, detail="job run not found")
        return _job_run_to_dict(jr)


__all__ = ["router"]
