"""Stuck-detection engine - pure functions over weekly snapshots.

Per architecture.md section 2 (Core mechanism):

    distribution(d, w) = {bucket_value: play_count_normalised}
    top10(d, w)        = the 10 most-played buckets in week w
    overlap(d, w)      = |top10(d,w) intersect top10(d,w-1)| / |union|     (Jaccard)
    entropy(d, w)      = -sum(p_i * log(p_i))                              (Shannon, nats)
    stuck_score(d, w)  = 0.6 * mean_rolling(overlap, 4w)
                       + 0.4 * (1 - mean_rolling(entropy, 4w) / log(max_buckets))
    overall_stuck_score(w) = max(stuck_score(genre, w), stuck_score(language, w))

Trigger:
    overall > STUCK_THRESHOLD for STUCK_STREAK_WEEKS in a row
    AND no nudge in the last COOLDOWN_WEEKS
    AND no active reset session
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Iterable

from app.config import settings
from app.models import ScopeDimension, StuckScoresPerDimension


# ============================================================
# Constants
# ============================================================

DIMENSIONS: tuple[ScopeDimension, ...] = ("genre", "language", "era", "mood")

# Only genre + language can fire the overall trigger; era + mood are
# noisier and serve as suggested_scope candidates only.
TRIGGER_DIMENSIONS: tuple[ScopeDimension, ...] = ("genre", "language")

ROLLING_WINDOW_WEEKS = 4
TOP_N_FOR_OVERLAP = 10

# Weight split in stuck_score (see formula above)
OVERLAP_WEIGHT = 0.6
ENTROPY_WEIGHT = 0.4


# ============================================================
# Pure math primitives
# ============================================================

def jaccard_overlap(set_a: set[str], set_b: set[str]) -> float:
    """Set Jaccard - kept for reference + tests.

    Returns |A intersect B| / |A union B|. Empty sets return 0.0.
    Used directly only in unit tests; the stuck-detection math uses the
    weighted variant below (`weighted_jaccard`) because set Jaccard
    breaks when buckets drop out as the user gets stuck.
    """
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    intersection = set_a & set_b
    return len(intersection) / len(union)


def weighted_jaccard(
    distribution_a: dict[str, float],
    distribution_b: dict[str, float],
) -> float:
    """Weighted Jaccard (a.k.a. Ruzicka) similarity of two distributions.

    Defined as sum_b min(p_a[b], p_b[b]) / sum_b max(p_a[b], p_b[b])
    where p_a, p_b are the renormalised probability distributions.

    Property: returns 1.0 when both distributions are identical; 0.0 when
    they have no shared support. Robust to bucket dropout - the score
    stays high (or rises) when one bucket grows to dominate, even if
    smaller buckets disappear. This is the right signal for stuck-ness.
    """
    if not distribution_a or not distribution_b:
        return 0.0
    total_a = sum(distribution_a.values())
    total_b = sum(distribution_b.values())
    if total_a <= 0 or total_b <= 0:
        return 0.0
    p_a = {k: v / total_a for k, v in distribution_a.items()}
    p_b = {k: v / total_b for k, v in distribution_b.items()}
    keys = set(p_a) | set(p_b)
    num = 0.0
    den = 0.0
    for k in keys:
        a = p_a.get(k, 0.0)
        b = p_b.get(k, 0.0)
        num += min(a, b)
        den += max(a, b)
    if den <= 0:
        return 0.0
    return num / den


def shannon_entropy(distribution: dict[str, float]) -> float:
    """Shannon entropy (nats) of a non-negative weight distribution.

    The distribution is renormalised internally so callers can pass raw
    play counts. Returns 0.0 for an empty or all-zero distribution.
    """
    if not distribution:
        return 0.0
    total = sum(distribution.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for w in distribution.values():
        if w <= 0:
            continue
        p = w / total
        h -= p * math.log(p)
    return h


def max_entropy(num_buckets: int) -> float:
    """Upper bound on Shannon entropy for `num_buckets` symbols."""
    return math.log(num_buckets) if num_buckets > 1 else 1.0


# ============================================================
# Per-track -> per-dimension distribution
# ============================================================

def _bucket_value(track: dict[str, Any], dimension: ScopeDimension) -> str | None:
    """Extract the bucket value for a single (track, dimension) pair.

    Returns None when the track is missing the relevant tag.
    """
    if dimension == "genre":
        genres = track.get("genres") or []
        return genres[0] if genres else None
    if dimension == "language":
        return track.get("language")
    if dimension == "era":
        return track.get("era")
    if dimension == "mood":
        return track.get("mood")
    return None


def compute_weekly_snapshot(
    *,
    user_id: str,
    iso_week: str,
    raw_tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate raw track rows into per-dimension play-count distributions.

    Returns a dict shaped:
        {
            "user_id": str,
            "iso_week": str,
            "distributions": {
                "genre":    {bucket: play_count, ...},
                "language": {bucket: play_count, ...},
                "era":      {bucket: play_count, ...},
                "mood":     {bucket: play_count, ...},
            },
            "track_count": int,
            "play_count_total": int,
        }
    """
    distributions: dict[str, dict[str, float]] = {d: {} for d in DIMENSIONS}
    total_plays = 0
    for track in raw_tracks:
        plays = float(track.get("play_count", 1))
        total_plays += int(plays)
        for d in DIMENSIONS:
            bucket = _bucket_value(track, d)
            if bucket is None:
                continue
            distributions[d][bucket] = distributions[d].get(bucket, 0.0) + plays
    return {
        "user_id": user_id,
        "iso_week": iso_week,
        "distributions": distributions,
        "track_count": len(raw_tracks),
        "play_count_total": total_plays,
    }


def top_n_buckets(distribution: dict[str, float], n: int = TOP_N_FOR_OVERLAP) -> set[str]:
    """Return the top-N most-played bucket names as a set."""
    if not distribution:
        return set()
    ordered = sorted(distribution.items(), key=lambda kv: -kv[1])
    return {k for k, _ in ordered[:n]}


# ============================================================
# Per-week, per-dimension stuck_score computation
# ============================================================

def _rolling_mean(values: list[float]) -> float:
    """Mean of the (already-windowed) list, or 0.0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalised_entropy(
    distribution: dict[str, float],
    num_reference_buckets: int,
) -> float:
    """Entropy / log(num_reference_buckets) in [0, 1].

    The reference bucket count is fixed across the rolling window (see
    `compute_stuck_score`) so the normalisation does not change just
    because the user dropped a language/genre this week - which would
    perversely cancel the very stuck-ness signal we are measuring.
    """
    if not distribution or num_reference_buckets < 2:
        return 0.0
    h = shannon_entropy(distribution)
    h_max = math.log(num_reference_buckets)
    if h_max <= 0:
        return 0.0
    return min(1.0, h / h_max)


def compute_stuck_score(
    *,
    user_id: str,
    iso_week: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute per-dimension + overall stuck scores given the user's history.

    `history` must be a list of weekly-snapshot dicts (output of
    `compute_weekly_snapshot`), sorted by `iso_week` ascending, including
    the current week's snapshot at the end. The function uses the last
    `ROLLING_WINDOW_WEEKS` of history.

    Returns a dict shaped:
        {
            "user_id": str,
            "iso_week": str,
            "per_dimension": StuckScoresPerDimension,
            "overall": float,
            "suggested_scope": ScopeDimension,
            "components": {dimension: {"mean_overlap", "mean_norm_entropy"}, ...},
        }
    """
    if not history:
        raise ValueError("history must contain at least the current week.")
    if history[-1]["iso_week"] != iso_week:
        raise ValueError(
            f"history[-1] must be the current week ({iso_week}); "
            f"got {history[-1]['iso_week']} instead."
        )

    window = history[-ROLLING_WINDOW_WEEKS:]
    per_dim: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    # `no_signal_dimensions` are dimensions where the user's history has
    # never shown more than 1 bucket - e.g. Aanya's `language` is
    # always "en". Those dimensions are excluded from the trigger and
    # from `suggested_scope` selection.
    no_signal_dimensions: set[str] = set()

    for dim in DIMENSIONS:
        # Reference bucket count: union of buckets observed across ALL of
        # the user's history (not just the rolling window). Using a stable,
        # only-growing reference prevents the perverse effect of
        # normalisation shrinking just as the user gets stuck (e.g. dropping
        # one of three languages would otherwise make the user look LESS
        # stuck, not more).
        ref_buckets: set[str] = set()
        for snap in history:
            ref_buckets.update(snap["distributions"][dim].keys())
        num_ref = len(ref_buckets)

        if num_ref < 2:
            no_signal_dimensions.add(dim)
            per_dim[dim] = 0.0
            components[dim] = {
                "mean_overlap": 0.0,
                "mean_norm_entropy": 0.0,
                "num_reference_buckets": num_ref,
                "no_signal": True,
            }
            continue

        # ----- Overlap series: weighted Jaccard of full distributions
        # between consecutive weeks. Weighted Jaccard handles bucket
        # dropout correctly (set Jaccard does not).
        overlap_series: list[float] = []
        for i in range(1, len(window)):
            overlap_series.append(
                weighted_jaccard(
                    window[i - 1]["distributions"][dim],
                    window[i]["distributions"][dim],
                )
            )

        mean_overlap = _rolling_mean(overlap_series) if overlap_series else 0.0

        # ----- Entropy series: normalised in-week entropy with FIXED reference
        entropy_series: list[float] = [
            _normalised_entropy(snap["distributions"][dim], num_ref)
            for snap in window
        ]
        mean_norm_entropy = _rolling_mean(entropy_series)

        score = (
            OVERLAP_WEIGHT * mean_overlap
            + ENTROPY_WEIGHT * (1.0 - mean_norm_entropy)
        )
        per_dim[dim] = max(0.0, min(1.0, score))
        components[dim] = {
            "mean_overlap": mean_overlap,
            "mean_norm_entropy": mean_norm_entropy,
            "num_reference_buckets": num_ref,
            "no_signal": False,
        }

    # Overall trigger: only the genre + language dimensions that have signal.
    trigger_candidates = [
        per_dim[d] for d in TRIGGER_DIMENSIONS if d not in no_signal_dimensions
    ]
    overall = max(trigger_candidates) if trigger_candidates else 0.0

    # Suggested scope: highest stuck dimension excluding no-signal ones.
    eligible = {d: s for d, s in per_dim.items() if d not in no_signal_dimensions}
    if eligible:
        suggested_scope = max(eligible.items(), key=lambda kv: kv[1])[0]
    else:
        # Pathological case: every dimension is no-signal. Fall back to
        # the user's strongest dimension overall (won't be a useful nudge,
        # but the API must return something).
        suggested_scope = max(per_dim.items(), key=lambda kv: kv[1])[0]

    per_dim_model = StuckScoresPerDimension(
        genre=per_dim["genre"],
        language=per_dim["language"],
        era=per_dim["era"],
        mood=per_dim["mood"],
    )

    return {
        "user_id": user_id,
        "iso_week": iso_week,
        "per_dimension": per_dim_model,
        "overall": overall,
        "suggested_scope": suggested_scope,
        "components": components,
    }


# ============================================================
# Trigger rule
# ============================================================

def should_trigger_nudge(
    *,
    user_id: str,
    recent_scores: list[dict[str, Any] | Any],
    last_nudge_at: datetime | None,
    has_active_session: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide whether to fire a nudge for this user right now.

    `recent_scores` is a list of recent stuck-score records sorted by
    iso_week ASCENDING; each record must expose an `.overall` float
    (works for both ORM rows and plain dicts via `_score_of`).

    Returns a dict shaped:
        {
            "trigger": bool,
            "reason": str,                       # explains why or why not
            "stuck_streak_weeks": int,           # consecutive weeks above threshold (right-aligned)
        }
    """
    now = now or datetime.utcnow()

    def _score_of(rec: Any) -> float:
        if isinstance(rec, dict):
            return float(rec["overall"])
        return float(getattr(rec, "overall"))

    if has_active_session:
        return {
            "trigger": False,
            "reason": "active reset session exists",
            "stuck_streak_weeks": 0,
        }

    if last_nudge_at is not None:
        cooldown_end = last_nudge_at + timedelta(weeks=settings.cooldown_weeks)
        if now < cooldown_end:
            days_remaining = max(0, (cooldown_end - now).days)
            return {
                "trigger": False,
                "reason": f"cooldown active ({days_remaining}d remaining)",
                "stuck_streak_weeks": 0,
            }

    # Count the right-aligned streak of consecutive weeks above threshold.
    streak = 0
    for rec in reversed(recent_scores):
        if _score_of(rec) > settings.stuck_threshold:
            streak += 1
        else:
            break

    if streak >= settings.stuck_streak_weeks:
        return {
            "trigger": True,
            "reason": f"{streak}-week streak above {settings.stuck_threshold}",
            "stuck_streak_weeks": streak,
        }
    return {
        "trigger": False,
        "reason": (
            f"only {streak} consecutive week(s) above threshold; "
            f"need {settings.stuck_streak_weeks}"
        ),
        "stuck_streak_weeks": streak,
    }


# ============================================================
# Convenience: end-to-end one-user job (used by the route)
# ============================================================

def process_user_weeks(
    *,
    user_id: str,
    weekly_track_rows: Iterable[tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """Walk one user's weekly raw tracks and compute the full score history.

    `weekly_track_rows` is an iterable of (iso_week, raw_tracks) tuples,
    sorted by iso_week ascending.

    Returns a dict shaped:
        {
            "user_id": str,
            "snapshots": [{user_id, iso_week, distributions, ...}, ...],
            "scores":    [{user_id, iso_week, per_dimension, overall, suggested_scope, components}, ...],
        }

    This is a pure orchestration helper - no DB IO. The route writes the
    DB rows; this function just produces the data shapes.
    """
    snapshots: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    for iso_week, raw_tracks in weekly_track_rows:
        snap = compute_weekly_snapshot(
            user_id=user_id, iso_week=iso_week, raw_tracks=raw_tracks,
        )
        snapshots.append(snap)
        score = compute_stuck_score(
            user_id=user_id, iso_week=iso_week, history=snapshots,
        )
        scores.append(score)
    return {"user_id": user_id, "snapshots": snapshots, "scores": scores}


__all__ = [
    "DIMENSIONS",
    "TRIGGER_DIMENSIONS",
    "ROLLING_WINDOW_WEEKS",
    "TOP_N_FOR_OVERLAP",
    "OVERLAP_WEIGHT",
    "ENTROPY_WEIGHT",
    "jaccard_overlap",
    "weighted_jaccard",
    "shannon_entropy",
    "max_entropy",
    "compute_weekly_snapshot",
    "top_n_buckets",
    "compute_stuck_score",
    "should_trigger_nudge",
    "process_user_weeks",
]
