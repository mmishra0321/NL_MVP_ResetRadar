"""Unit tests for app.detection.

R1 acceptance gate: this module must pass `pytest`. Tests cover the
three pure-math primitives (jaccard, weighted_jaccard, shannon_entropy),
the per-week aggregation (compute_weekly_snapshot), the per-week score
(compute_stuck_score) including the no-signal-dimension guard, the
end-to-end orchestration (process_user_weeks), and the trigger rule
(should_trigger_nudge) across all four exit conditions.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.detection import (
    DIMENSIONS,
    OVERLAP_WEIGHT,
    ENTROPY_WEIGHT,
    ROLLING_WINDOW_WEEKS,
    compute_stuck_score,
    compute_weekly_snapshot,
    jaccard_overlap,
    process_user_weeks,
    shannon_entropy,
    should_trigger_nudge,
    top_n_buckets,
    weighted_jaccard,
)


# ============================================================
# Pure math primitives
# ============================================================

class TestJaccardOverlap:
    def test_identical_sets(self):
        assert jaccard_overlap({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_overlap({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        # |intersection| = 1, |union| = 3 -> 1/3
        result = jaccard_overlap({"a", "b"}, {"b", "c"})
        assert result == pytest.approx(1 / 3)

    def test_both_empty(self):
        assert jaccard_overlap(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_overlap(set(), {"a"}) == 0.0


class TestWeightedJaccard:
    def test_identical_distributions(self):
        d = {"a": 5.0, "b": 3.0, "c": 2.0}
        assert weighted_jaccard(d, d) == pytest.approx(1.0)

    def test_disjoint_distributions(self):
        assert weighted_jaccard({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_renormalises_independently(self):
        # Same proportions, different totals -> should still be 1.0
        d1 = {"a": 2.0, "b": 1.0}
        d2 = {"a": 20.0, "b": 10.0}
        assert weighted_jaccard(d1, d2) == pytest.approx(1.0)

    def test_concentration_raises_overlap(self):
        # When one bucket grows more, weighted Jaccard between
        # consecutive distributions should stay HIGH, not drop.
        # (This is the property set Jaccard fails to satisfy.)
        early = {"a": 0.33, "b": 0.33, "c": 0.34}
        late = {"a": 0.90, "b": 0.07, "c": 0.03}
        very_late = {"a": 0.95, "b": 0.04, "c": 0.01}
        early_to_late = weighted_jaccard(early, late)
        late_to_very_late = weighted_jaccard(late, very_late)
        # late->very-late should be HIGHER (more similar) than early->late
        assert late_to_very_late > early_to_late

    def test_empty_returns_zero(self):
        assert weighted_jaccard({}, {"a": 1.0}) == 0.0
        assert weighted_jaccard({"a": 1.0}, {}) == 0.0


class TestShannonEntropy:
    def test_uniform_max(self):
        # Uniform distribution over n buckets has entropy = log(n)
        n = 5
        d = {str(i): 1.0 for i in range(n)}
        h = shannon_entropy(d)
        assert h == pytest.approx(math.log(n))

    def test_concentrated_zero(self):
        # All mass in one bucket -> entropy = 0
        d = {"a": 1.0}
        assert shannon_entropy(d) == 0.0

    def test_empty_zero(self):
        assert shannon_entropy({}) == 0.0

    def test_renormalises_internally(self):
        d_unit = {"a": 0.5, "b": 0.5}
        d_scaled = {"a": 10.0, "b": 10.0}
        assert shannon_entropy(d_unit) == pytest.approx(shannon_entropy(d_scaled))

    def test_two_unequal(self):
        d = {"a": 0.9, "b": 0.1}
        expected = -(0.9 * math.log(0.9) + 0.1 * math.log(0.1))
        assert shannon_entropy(d) == pytest.approx(expected)


# ============================================================
# Per-week aggregation
# ============================================================

class TestComputeWeeklySnapshot:
    def test_basic_aggregation(self):
        tracks = [
            {"genres": ["alt-rock"], "language": "en", "era": "2000s", "mood": "energetic", "play_count": 3},
            {"genres": ["alt-rock"], "language": "en", "era": "2000s", "mood": "energetic", "play_count": 2},
            {"genres": ["jazz"], "language": "en", "era": "1960s", "mood": "chill", "play_count": 5},
        ]
        snap = compute_weekly_snapshot(
            user_id="u1", iso_week="2026-W26", raw_tracks=tracks,
        )
        assert snap["user_id"] == "u1"
        assert snap["iso_week"] == "2026-W26"
        assert snap["track_count"] == 3
        assert snap["play_count_total"] == 10
        assert snap["distributions"]["genre"] == {"alt-rock": 5.0, "jazz": 5.0}
        assert snap["distributions"]["language"] == {"en": 10.0}
        assert snap["distributions"]["era"] == {"2000s": 5.0, "1960s": 5.0}

    def test_handles_missing_tags(self):
        tracks = [
            {"play_count": 1},                                   # no metadata at all
            {"genres": ["pop"], "play_count": 1},                # genre only
        ]
        snap = compute_weekly_snapshot(
            user_id="u1", iso_week="2026-W26", raw_tracks=tracks,
        )
        # Tracks without language/era/mood don't pollute those distributions.
        assert snap["distributions"]["language"] == {}
        assert snap["distributions"]["era"] == {}
        assert snap["distributions"]["genre"] == {"pop": 1.0}

    def test_top_n_buckets_orders_by_count(self):
        dist = {"a": 1.0, "b": 5.0, "c": 3.0}
        top2 = top_n_buckets(dist, n=2)
        assert top2 == {"b", "c"}


# ============================================================
# Compute stuck score
# ============================================================

def _mk_snapshot(iso_week: str, distributions: dict[str, dict[str, float]]) -> dict:
    """Build a snapshot dict in the shape `compute_stuck_score` expects."""
    full = {d: {} for d in DIMENSIONS}
    full.update(distributions)
    return {"user_id": "u1", "iso_week": iso_week, "distributions": full}


class TestComputeStuckScore:
    def test_requires_current_week_in_history(self):
        with pytest.raises(ValueError):
            compute_stuck_score(
                user_id="u1",
                iso_week="2026-W26",
                history=[_mk_snapshot("2026-W25", {"genre": {"a": 1.0}})],
            )

    def test_requires_nonempty_history(self):
        with pytest.raises(ValueError):
            compute_stuck_score(user_id="u1", iso_week="2026-W26", history=[])

    def test_single_bucket_history_marks_no_signal(self):
        # All weeks have only one language bucket -> language is no-signal
        # (think monolingual user). Its stuck_score must be 0 and it cannot
        # be `suggested_scope` for the overall trigger.
        history = [
            _mk_snapshot("2026-W23", {
                "language": {"en": 10.0},
                "genre": {"alt-rock": 5.0, "pop": 5.0},
            }),
            _mk_snapshot("2026-W24", {
                "language": {"en": 10.0},
                "genre": {"alt-rock": 6.0, "pop": 4.0},
            }),
            _mk_snapshot("2026-W25", {
                "language": {"en": 10.0},
                "genre": {"alt-rock": 8.0, "pop": 2.0},
            }),
            _mk_snapshot("2026-W26", {
                "language": {"en": 10.0},
                "genre": {"alt-rock": 9.0, "pop": 1.0},
            }),
        ]
        result = compute_stuck_score(
            user_id="u1", iso_week="2026-W26", history=history,
        )
        assert result["per_dimension"].language == 0.0
        assert result["components"]["language"]["no_signal"] is True
        # Suggested scope can never be language for this user
        assert result["suggested_scope"] != "language"

    def test_rising_concentration_raises_score_monotonically(self):
        # 5 weeks of progressively-concentrating genre distribution
        # The genre stuck_score should rise across weeks.
        weeks = [
            ("2026-W22", {"a": 2.0, "b": 2.0, "c": 2.0, "d": 2.0, "e": 2.0}),
            ("2026-W23", {"a": 5.0, "b": 2.0, "c": 1.0, "d": 1.0, "e": 1.0}),
            ("2026-W24", {"a": 8.0, "b": 1.0, "c": 1.0}),
            ("2026-W25", {"a": 9.0, "b": 1.0}),
            ("2026-W26", {"a": 10.0, "b": 0.5}),
        ]
        history = []
        scores = []
        for iso, genre_dist in weeks:
            history.append(_mk_snapshot(iso, {
                "genre": genre_dist,
                "language": {"en": sum(genre_dist.values())},
            }))
            res = compute_stuck_score(user_id="u1", iso_week=iso, history=history)
            scores.append(res["per_dimension"].genre)
        # First < last; intermediate weeks generally rising.
        assert scores[0] < scores[-1]
        # The final two weeks should both be above 0.5 (well concentrated)
        assert scores[-1] > 0.5
        assert scores[-2] > 0.5

    def test_per_dimension_score_in_range(self):
        history = [
            _mk_snapshot("2026-W26", {
                "genre": {"a": 1.0, "b": 1.0},
                "language": {"en": 1.0, "fr": 1.0},
                "era": {"2010s": 1.0, "2020s": 1.0},
                "mood": {"chill": 1.0, "energetic": 1.0},
            }),
        ]
        result = compute_stuck_score(user_id="u1", iso_week="2026-W26", history=history)
        for d in DIMENSIONS:
            score = getattr(result["per_dimension"], d)
            assert 0.0 <= score <= 1.0, f"{d} score {score} out of [0, 1]"
        assert 0.0 <= result["overall"] <= 1.0


# ============================================================
# End-to-end process_user_weeks against the fixture
# ============================================================

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "mock_data" / "synthetic_weeks.json"


def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(
            f"fixture missing at {FIXTURE_PATH}; "
            f"run `python scripts/generate_synthetic_weeks.py`"
        )
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _user_weekly_rows(fixture: dict, user_id: str):
    weeks = fixture["weeks"]
    for iso_week in sorted(weeks.keys()):
        snap = next(s for s in weeks[iso_week] if s["user_id"] == user_id)
        yield iso_week, snap["tracks"]


class TestSyntheticFixtureTrajectory:
    def test_karthik_triggers_on_language(self):
        fixture = _load_fixture()
        rows = list(_user_weekly_rows(fixture, "demo-karthik-001"))
        result = process_user_weeks(
            user_id="demo-karthik-001", weekly_track_rows=rows,
        )
        # W26 score is the final one in the list
        final = result["scores"][-1]
        assert final["iso_week"] == "2026-W26"
        assert final["suggested_scope"] == "language", (
            f"expected language; got {final['suggested_scope']}; "
            f"per-dim = {final['per_dimension']}"
        )
        assert final["overall"] > settings.stuck_threshold, (
            f"expected overall > {settings.stuck_threshold}; "
            f"got {final['overall']:.3f}"
        )

    def test_aanya_triggers_on_genre(self):
        fixture = _load_fixture()
        rows = list(_user_weekly_rows(fixture, "demo-aanya-002"))
        result = process_user_weeks(
            user_id="demo-aanya-002", weekly_track_rows=rows,
        )
        final = result["scores"][-1]
        assert final["iso_week"] == "2026-W26"
        assert final["suggested_scope"] == "genre"
        assert final["overall"] > settings.stuck_threshold

    def test_aanya_language_marked_no_signal(self):
        fixture = _load_fixture()
        rows = list(_user_weekly_rows(fixture, "demo-aanya-002"))
        result = process_user_weeks(
            user_id="demo-aanya-002", weekly_track_rows=rows,
        )
        for score in result["scores"]:
            # Aanya is monolingual; language must always be no-signal -> 0.0
            assert score["per_dimension"].language == 0.0
            assert score["components"]["language"]["no_signal"] is True

    def test_both_users_streak_satisfies_trigger(self):
        fixture = _load_fixture()
        for user_id in ["demo-karthik-001", "demo-aanya-002"]:
            rows = list(_user_weekly_rows(fixture, user_id))
            result = process_user_weeks(user_id=user_id, weekly_track_rows=rows)
            decision = should_trigger_nudge(
                user_id=user_id,
                recent_scores=result["scores"],
                last_nudge_at=None,
                has_active_session=False,
            )
            assert decision["trigger"] is True, (
                f"{user_id} expected to trigger; reason={decision['reason']}"
            )
            assert decision["stuck_streak_weeks"] >= settings.stuck_streak_weeks


# ============================================================
# Trigger rule
# ============================================================

def _mk_score_row(iso_week: str, overall: float) -> dict:
    return {"user_id": "u1", "iso_week": iso_week, "overall": overall}


class TestShouldTriggerNudge:
    def test_active_session_blocks(self):
        scores = [_mk_score_row(f"2026-W{w}", 0.9) for w in range(20, 27)]
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=None,
            has_active_session=True,
        )
        assert d["trigger"] is False
        assert "active reset session" in d["reason"]

    def test_cooldown_blocks(self):
        scores = [_mk_score_row(f"2026-W{w}", 0.9) for w in range(20, 27)]
        recent = datetime.utcnow() - timedelta(days=7)         # within 4w cooldown
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=recent,
            has_active_session=False,
        )
        assert d["trigger"] is False
        assert "cooldown" in d["reason"]

    def test_cooldown_expired_allows(self):
        scores = [_mk_score_row(f"2026-W{w}", 0.9) for w in range(20, 27)]
        old = datetime.utcnow() - timedelta(weeks=settings.cooldown_weeks + 1)
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=old,
            has_active_session=False,
        )
        assert d["trigger"] is True

    def test_streak_short_blocks(self):
        # Only 2 consecutive weeks above threshold
        scores = [
            _mk_score_row("2026-W23", 0.3),
            _mk_score_row("2026-W24", 0.4),
            _mk_score_row("2026-W25", 0.9),
            _mk_score_row("2026-W26", 0.9),
        ]
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=None,
            has_active_session=False,
        )
        assert d["trigger"] is False
        assert d["stuck_streak_weeks"] == 2

    def test_streak_long_enough_triggers(self):
        scores = [
            _mk_score_row("2026-W23", 0.3),
            _mk_score_row("2026-W24", 0.9),
            _mk_score_row("2026-W25", 0.9),
            _mk_score_row("2026-W26", 0.9),
        ]
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=None,
            has_active_session=False,
        )
        assert d["trigger"] is True
        assert d["stuck_streak_weeks"] == 3

    def test_streak_breaks_then_restarts(self):
        # Once below threshold, the streak resets even if it later rises
        scores = [
            _mk_score_row("2026-W23", 0.9),
            _mk_score_row("2026-W24", 0.9),
            _mk_score_row("2026-W25", 0.4),                       # break
            _mk_score_row("2026-W26", 0.9),
        ]
        d = should_trigger_nudge(
            user_id="u1",
            recent_scores=scores,
            last_nudge_at=None,
            has_active_session=False,
        )
        assert d["stuck_streak_weeks"] == 1
        assert d["trigger"] is False


# ============================================================
# Constants sanity (catch accidental edits to the formula weights)
# ============================================================

def test_overlap_and_entropy_weights_sum_to_one():
    assert OVERLAP_WEIGHT + ENTROPY_WEIGHT == pytest.approx(1.0)


def test_rolling_window_weeks_constant():
    assert ROLLING_WINDOW_WEEKS == 4
