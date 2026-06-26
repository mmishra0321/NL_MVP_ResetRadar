"""Unit tests for backend/app/reset_engine.py + spotify_client.search_candidates.

These tests do NOT call Groq. The LLM is mocked at the
`app.reset_engine.rank_and_explain` boundary so we can deterministically
exercise:
  * scope filtering
  * deduplication
  * the hallucination guard (track_ids not in the pool are dropped)
  * order_index stamping
  * the Spotify /search query builder
  * the mock-candidates fixture (real file shape + scope balance)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app import reset_engine
from app.config import settings
from app.spotify_client import search_candidates


# ============================================================
# Fixtures
# ============================================================

MOCK_FIXTURE = settings.mock_data_dir / "mock_candidates.json"


@pytest.fixture(scope="module")
def candidate_payload() -> dict[str, Any]:
    """Parsed mock_candidates.json (regenerated via scripts/generate_mock_candidates.py)."""
    assert MOCK_FIXTURE.exists(), (
        f"Missing fixture {MOCK_FIXTURE}. "
        f"Run `python scripts/generate_mock_candidates.py` first."
    )
    return json.loads(MOCK_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def small_genre_pool() -> list[dict[str, Any]]:
    """Hand-rolled tiny pool for fast deterministic tests."""
    return [
        {"spotify_track_id": "mock-genre-001", "title": "So What",        "artist": "Miles Davis",   "genres": ["jazz"],       "language": "en", "era": "1950s", "mood": "chill",       "scope_origin": "genre"},
        {"spotify_track_id": "mock-genre-002", "title": "Take Five",      "artist": "Dave Brubeck",  "genres": ["jazz"],       "language": "en", "era": "1950s", "mood": "chill",       "scope_origin": "genre"},
        {"spotify_track_id": "mock-genre-003", "title": "Cranes",         "artist": "Solange",       "genres": ["neo-soul"],   "language": "en", "era": "2010s", "mood": "melancholy",  "scope_origin": "genre"},
        {"spotify_track_id": "mock-lang-001",  "title": "Spring Day",     "artist": "BTS",           "genres": ["k-pop"],      "language": "ko", "era": "2010s", "mood": "melancholy",  "scope_origin": "language"},
    ]


# ============================================================
# build_search_queries
# ============================================================

class TestBuildSearchQueries:
    def test_genre_dimension_produces_quoted_filter(self) -> None:
        q = reset_engine.build_search_queries(
            scope_dimensions=["genre"],
            scope_values={"genre": ["jazz", "neo-soul"]},
        )
        assert 'genre:"jazz"' in q
        assert 'genre:"neo-soul"' in q

    def test_era_dimension_expands_to_year_range(self) -> None:
        q = reset_engine.build_search_queries(
            scope_dimensions=["era"],
            scope_values={"era": ["1990s"]},
        )
        assert q == ["year:1990-1999"]

    def test_era_invalid_input_is_dropped(self) -> None:
        q = reset_engine.build_search_queries(
            scope_dimensions=["era"],
            scope_values={"era": ["", "not-an-era", "2000s"]},
        )
        assert q == ["year:2000-2009"]

    def test_free_text_appended(self) -> None:
        q = reset_engine.build_search_queries(
            scope_dimensions=["mood"],
            scope_values={"mood": ["upbeat"]},
            free_text_intent="something I can walk to",
        )
        assert "something I can walk to" in q

    def test_empty_scope_returns_empty_or_just_intent(self) -> None:
        q = reset_engine.build_search_queries(
            scope_dimensions=["genre"],
            scope_values={"genre": []},                          # no values for the dim
        )
        assert q == []


# ============================================================
# search_candidates (mock-mode reader)
# ============================================================

class TestSearchCandidates:
    def test_mock_mode_reads_envelope_shape(self, candidate_payload: dict[str, Any]) -> None:
        """search_candidates must understand the {candidates: [...]} envelope."""
        result = search_candidates(
            scope_dimensions=["genre"],
            scope_values={},
            target_pool_size=settings.max_candidates_from_search,
        )
        assert len(result) > 0
        assert all(c["scope_origin"] == "genre" for c in result)

    def test_filters_by_scope_before_trimming(self) -> None:
        """Asking for `language` must not return `genre` candidates first."""
        result = search_candidates(
            scope_dimensions=["language"],
            scope_values={},
            target_pool_size=80,
        )
        assert len(result) > 0
        assert all(c["scope_origin"] == "language" for c in result)

    def test_per_scope_count_matches_generator_config(self, candidate_payload: dict[str, Any]) -> None:
        """The fixture should have exactly 60 candidates per scope dimension."""
        from collections import Counter
        counts = Counter(c["scope_origin"] for c in candidate_payload["candidates"])
        for scope in ("genre", "language", "era", "mood"):
            assert counts[scope] == 60, f"{scope}: expected 60, got {counts[scope]}"


# ============================================================
# _filter_candidates_by_scope
# ============================================================

class TestFilterByScope:
    def test_keeps_only_matching_scope_origin(self, small_genre_pool: list[dict[str, Any]]) -> None:
        out = reset_engine._filter_candidates_by_scope(small_genre_pool, ["genre"])
        assert {c["spotify_track_id"] for c in out} == {"mock-genre-001", "mock-genre-002", "mock-genre-003"}

    def test_candidates_without_origin_pass_through(self) -> None:
        """Real-mode candidates have no scope_origin field; they all pass."""
        pool = [{"spotify_track_id": "real-1", "title": "x", "artist": "y", "genres": []}]
        out = reset_engine._filter_candidates_by_scope(pool, ["genre"])
        assert len(out) == 1


# ============================================================
# _dedupe_candidates
# ============================================================

class TestDedupeCandidates:
    def test_keeps_first_occurrence(self) -> None:
        pool = [
            {"spotify_track_id": "a", "title": "X"},
            {"spotify_track_id": "b", "title": "Y"},
            {"spotify_track_id": "a", "title": "X-duplicate"},
        ]
        out = reset_engine._dedupe_candidates(pool)
        assert [c["spotify_track_id"] for c in out] == ["a", "b"]
        assert out[0]["title"] == "X"

    def test_empty_input(self) -> None:
        assert reset_engine._dedupe_candidates([]) == []


# ============================================================
# _validate_picks (THE pitfall-1 hallucination guard)
# ============================================================

class TestValidatePicks:
    def test_drops_hallucinated_track_ids(self, small_genre_pool: list[dict[str, Any]]) -> None:
        picks = [
            {"spotify_track_id": "mock-genre-001", "score": 0.9, "why": "real"},
            {"spotify_track_id": "spotify:fake:track", "score": 0.8, "why": "hallucinated"},
            {"spotify_track_id": "mock-genre-002", "score": 0.7, "why": "also real"},
        ]
        out = reset_engine._validate_picks(candidate_pool=small_genre_pool, llm_picks=picks)
        assert len(out) == 2
        ids = {p["spotify_track_id"] for p in out}
        assert "spotify:fake:track" not in ids

    def test_enriches_with_candidate_metadata(self, small_genre_pool: list[dict[str, Any]]) -> None:
        picks = [{"spotify_track_id": "mock-genre-001", "score": 0.9, "why": "great fit"}]
        out = reset_engine._validate_picks(candidate_pool=small_genre_pool, llm_picks=picks)
        assert out[0]["title"] == "So What"
        assert out[0]["artist"] == "Miles Davis"
        assert out[0]["genres"] == ["jazz"]
        assert out[0]["why"] == "great fit"

    def test_handles_missing_or_invalid_fields(self, small_genre_pool: list[dict[str, Any]]) -> None:
        picks = [
            {"spotify_track_id": "mock-genre-001"},                  # no score, no why
            {"score": 0.5},                                          # no track_id
            {"spotify_track_id": None, "score": 0.5, "why": "x"},    # null id
        ]
        out = reset_engine._validate_picks(candidate_pool=small_genre_pool, llm_picks=picks)
        assert len(out) == 1
        assert out[0]["score"] == 0.0
        assert out[0]["why"] == ""


# ============================================================
# generate_reset_playlist (end-to-end with mocked Groq)
# ============================================================

class TestGenerateResetPlaylist:
    def _fake_llm_picks(self, candidates: list[dict[str, Any]], target_count: int) -> list[dict[str, Any]]:
        """Stand-in for rank_and_explain - picks first N candidates with synthetic scores."""
        return [
            {
                "spotify_track_id": c["spotify_track_id"],
                "score": 0.9 - i * 0.01,
                "why": f"This {c['title']} by {c['artist']} expands your {c.get('scope_origin', '?')} taste.",
            }
            for i, c in enumerate(candidates[:target_count])
        ]

    def test_happy_path_genre_scope(self, small_genre_pool: list[dict[str, Any]]) -> None:
        with patch(
            "app.reset_engine.rank_and_explain",
            side_effect=lambda *, scope_dimensions, free_text_intent, candidates, target_count:
                self._fake_llm_picks(candidates, target_count),
        ):
            picks = reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["genre"],
                free_text_intent=None,
                target_count=3,
                candidates_override=small_genre_pool,
            )
        assert len(picks) == 3
        assert all(p["spotify_track_id"].startswith("mock-genre-") for p in picks)
        assert [p["order_index"] for p in picks] == [0, 1, 2]

    def test_picks_are_sorted_by_score_descending(self, small_genre_pool: list[dict[str, Any]]) -> None:
        def llm_returns_unsorted(*, scope_dimensions, free_text_intent, candidates, target_count):
            return [
                {"spotify_track_id": "mock-genre-001", "score": 0.5, "why": "mid"},
                {"spotify_track_id": "mock-genre-002", "score": 0.9, "why": "best"},
                {"spotify_track_id": "mock-genre-003", "score": 0.1, "why": "worst"},
            ]
        with patch("app.reset_engine.rank_and_explain", side_effect=llm_returns_unsorted):
            picks = reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["genre"],
                free_text_intent=None,
                target_count=3,
                candidates_override=small_genre_pool,
            )
        scores = [p["score"] for p in picks]
        assert scores == sorted(scores, reverse=True)

    def test_hallucinated_picks_are_dropped_end_to_end(self, small_genre_pool: list[dict[str, Any]]) -> None:
        """If the LLM returns a fake ID, the validator drops it without erroring."""
        def llm_with_hallucination(*, scope_dimensions, free_text_intent, candidates, target_count):
            return [
                {"spotify_track_id": "mock-genre-001", "score": 0.9, "why": "real"},
                {"spotify_track_id": "spotify:made:up:id", "score": 0.8, "why": "fake"},
            ]
        with patch("app.reset_engine.rank_and_explain", side_effect=llm_with_hallucination):
            picks = reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["genre"],
                free_text_intent=None,
                target_count=20,
                candidates_override=small_genre_pool,
            )
        assert len(picks) == 1
        assert picks[0]["spotify_track_id"] == "mock-genre-001"

    def test_language_scope_drops_genre_pool_entries(self, small_genre_pool: list[dict[str, Any]]) -> None:
        """The scope filter should exclude items whose scope_origin doesn't match."""
        with patch(
            "app.reset_engine.rank_and_explain",
            side_effect=lambda *, scope_dimensions, free_text_intent, candidates, target_count:
                self._fake_llm_picks(candidates, target_count),
        ):
            picks = reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["language"],
                free_text_intent=None,
                target_count=20,
                candidates_override=small_genre_pool,
            )
        assert len(picks) == 1
        assert picks[0]["spotify_track_id"] == "mock-lang-001"

    def test_empty_scope_raises_value_error(self, small_genre_pool: list[dict[str, Any]]) -> None:
        with pytest.raises(ValueError, match="scope_dimensions"):
            reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=[],
                free_text_intent=None,
                candidates_override=small_genre_pool,
            )

    def test_empty_pool_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Empty candidate pool"):
            reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["genre"],
                free_text_intent=None,
                candidates_override=[],
            )

    def test_full_fixture_pool_yields_20_picks(self, candidate_payload: dict[str, Any]) -> None:
        """Exercise the real fixture (60 candidates per scope) with mocked LLM."""
        with patch(
            "app.reset_engine.rank_and_explain",
            side_effect=lambda *, scope_dimensions, free_text_intent, candidates, target_count:
                self._fake_llm_picks(candidates, target_count),
        ):
            picks = reset_engine.generate_reset_playlist(
                user_id="test-user",
                scope_dimensions=["language"],
                free_text_intent="something to expand my Telugu-only listening",
                target_count=20,
            )
        assert len(picks) == 20
        assert len({p["spotify_track_id"] for p in picks}) == 20         # unique
        assert all(p["spotify_track_id"].startswith("mock-language-") for p in picks)
        assert all(p["why"] for p in picks)                              # non-empty
        assert all(len(p["why"]) <= 200 for p in picks)
