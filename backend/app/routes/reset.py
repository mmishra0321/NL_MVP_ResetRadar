"""Reset session endpoints - create, fetch, decide.

R2 ships real `POST /reset/sessions` + `GET /reset/sessions/{id}`.
R5 (later) wires real Spotify playlist write + Keep/Revert handling;
for now `POST /sessions/{id}/decide` remains a 501 stub.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.db import db_session
from app.models import (
    ResetDecisionIn,
    ResetOutcomeOut,
    ResetSession,
    ResetSessionIn,
    ResetSessionOut,
    ResetTrack,
    ResetTrackOut,
    ScopeDimension,
    User,
)
from app.reset_engine import generate_reset_playlist
from app.spotify_client import add_tracks_to_playlist, create_playlist


log = logging.getLogger("reset_radar.routes.reset")
router = APIRouter()


# ============================================================
# Helpers
# ============================================================

def _coerce_scope_list(values: list[str]) -> list[ScopeDimension]:
    """Coerce stored JSON list back into typed ScopeDimensions for response."""
    out: list[ScopeDimension] = []
    for v in values:
        if v in {"genre", "language", "era", "mood"}:
            out.append(v)                                            # type: ignore[arg-type]
    return out


def _serialise_session(session: ResetSession) -> ResetSessionOut:
    """SQLAlchemy ResetSession -> Pydantic ResetSessionOut."""
    return ResetSessionOut(
        id=session.id,
        user_id=session.user_id,
        scope_dimensions=_coerce_scope_list(session.scope_dimensions_json or []),
        free_text_intent=session.free_text_intent,
        playlist_url=(
            f"https://open.spotify.com/playlist/{session.spotify_playlist_id}"
            if session.spotify_playlist_id else None
        ),
        trial_end_date=session.trial_end_date,
        decision=session.decision,                                   # type: ignore[arg-type]
        created_at=session.created_at,
        tracks=[
            ResetTrackOut(
                spotify_track_id=t.spotify_track_id,
                title=t.title,
                artist=t.artist,
                album=t.album,
                why=t.llm_explanation,
                order_index=t.order_index,
            )
            for t in sorted(session.tracks, key=lambda t: t.order_index)
        ],
    )


# ============================================================
# Endpoints
# ============================================================

@router.post("/sessions", response_model=ResetSessionOut)
def create_reset_session(body: ResetSessionIn) -> ResetSessionOut:
    """Begin a reset session.

    Pipeline:
      1. Validate user exists (created by /jobs/run-weekly-detection in mock mode).
      2. Call reset_engine.generate_reset_playlist (filter -> Groq -> validate).
      3. In mock mode: synthesize a playlist URL via create_playlist (no-op write).
      4. Persist ResetSession + ResetTrack rows.
      5. Return ResetSessionOut.
    """
    with db_session() as db:
        user = db.get(User, body.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"user {body.user_id!r} not found. "
                    f"Run POST /jobs/run-weekly-detection first to seed users."
                ),
            )

        try:
            tracks = generate_reset_playlist(
                user_id=body.user_id,
                scope_dimensions=list(body.scope_dimensions),
                free_text_intent=body.free_text_intent,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        except NotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(exc),
            )
        except Exception as exc:
            log.exception("Reset playlist generation failed.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Reset playlist generation failed: {exc}",
            )

        if not tracks:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Groq returned 0 validated tracks. Likely all picks were "
                    "hallucinated track_ids - check backend logs."
                ),
            )

        playlist = create_playlist(
            user_id=body.user_id,
            name=f"Reset Radar - {'/'.join(body.scope_dimensions)}",
            description=(
                "Sandboxed " + str(settings.trial_window_days) + "-day reset trial. "
                "Keep or revert at the end."
            ),
        )
        add_tracks_to_playlist(
            playlist_id=playlist["id"],
            track_ids=[t["spotify_track_id"] for t in tracks],
        )

        now = datetime.utcnow()
        session_row = ResetSession(
            id=str(uuid.uuid4()),
            user_id=body.user_id,
            nudge_id=None,
            scope_dimensions_json=list(body.scope_dimensions),
            free_text_intent=body.free_text_intent,
            spotify_playlist_id=playlist["id"],
            trial_end_date=now + timedelta(days=settings.trial_window_days),
            created_at=now,
        )
        db.add(session_row)

        for track in tracks:
            db.add(ResetTrack(
                id=str(uuid.uuid4()),
                reset_session_id=session_row.id,
                spotify_track_id=track["spotify_track_id"],
                title=track["title"],
                artist=track["artist"],
                album=track.get("album"),
                genre=(track.get("genres") or [None])[0],
                language=track.get("language"),
                era=track.get("era"),
                mood=track.get("mood"),
                llm_score=track["score"],
                llm_explanation=track["why"],
                order_index=track["order_index"],
            ))
        db.commit()
        db.refresh(session_row)
        return _serialise_session(session_row)


@router.get("/sessions/{session_id}", response_model=ResetSessionOut)
def get_reset_session(session_id: str) -> ResetSessionOut:
    """Fetch an existing reset session with its tracks."""
    with db_session() as db:
        session_row = db.get(ResetSession, session_id)
        if session_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"reset session {session_id} not found",
            )
        return _serialise_session(session_row)


@router.post("/sessions/{session_id}/decide", response_model=ResetOutcomeOut)
def decide_reset_session(session_id: str, body: ResetDecisionIn) -> ResetOutcomeOut:
    """Apply the Keep / Revert decision after the trial. R5 stub."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Keep/Revert handler lands in R5.",
    )


__all__ = ["router"]
