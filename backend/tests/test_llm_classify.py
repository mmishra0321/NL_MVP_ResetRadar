"""Unit tests for llm_client.classify_languages / classify_moods.

Groq is mocked at the `app.llm_client.chat_json` boundary so these
tests don't burn quota.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app import llm_client


# ============================================================
# Tests: classify_languages
# ============================================================

class TestClassifyLanguages:
    def test_returns_one_label_per_input(self):
        tracks = [
            {"title": "Hey Jude",     "artist": "The Beatles",   "genres": ["rock"]},
            {"title": "Despacito",    "artist": "Luis Fonsi",    "genres": ["reggaeton"]},
            {"title": "Tum Hi Ho",    "artist": "Arijit Singh",  "genres": ["bollywood"]},
        ]
        fake_response = {
            "classifications": [
                {"index": 0, "language": "en"},
                {"index": 1, "language": "es"},
                {"index": 2, "language": "hi"},
            ]
        }
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_languages(tracks)
        assert out == ["en", "es", "hi"]

    def test_falls_back_to_other_on_unknown_label(self):
        tracks = [{"title": "Song", "artist": "Artist", "genres": []}]
        fake_response = {"classifications": [{"index": 0, "language": "klingon"}]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_languages(tracks)
        assert out == ["other"]

    def test_handles_out_of_order_response(self):
        tracks = [
            {"title": "T0", "artist": "A0", "genres": []},
            {"title": "T1", "artist": "A1", "genres": []},
            {"title": "T2", "artist": "A2", "genres": []},
        ]
        fake_response = {"classifications": [
            {"index": 2, "language": "fr"},
            {"index": 0, "language": "en"},
            {"index": 1, "language": "es"},
        ]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_languages(tracks)
        assert out == ["en", "es", "fr"]

    def test_skips_invalid_entries_but_keeps_default(self):
        tracks = [
            {"title": "T0", "artist": "A0", "genres": []},
            {"title": "T1", "artist": "A1", "genres": []},
        ]
        fake_response = {"classifications": [
            {"index": 0, "language": "en"},
            {"language": "fr"},                                          # missing index -> ignored
            {"index": 5, "language": "es"},                              # out-of-range -> ignored
        ]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_languages(tracks)
        assert out == ["en", "other"]

    def test_empty_input_short_circuits(self):
        with patch.object(llm_client, "chat_json") as mock:
            out = llm_client.classify_languages([])
        assert out == []
        assert mock.call_count == 0

    def test_per_track_shim_delegates_to_batch(self):
        fake_response = {"classifications": [{"index": 0, "language": "te"}]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_language(
                track_title="Inkem Inkem", artist_name="Naga Chaitanya", genres=[],
            )
        assert out == "te"


# ============================================================
# Tests: classify_moods
# ============================================================

class TestClassifyMoods:
    def test_returns_one_label_per_input(self):
        tracks = [
            {"title": "Walking on Sunshine", "artist": "Katrina", "genres": ["pop"]},
            {"title": "Mad World", "artist": "Gary Jules", "genres": ["alt"]},
        ]
        fake_response = {"classifications": [
            {"index": 0, "mood": "energetic"},
            {"index": 1, "mood": "melancholy"},
        ]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_moods(tracks)
        assert out == ["energetic", "melancholy"]

    def test_falls_back_to_chill_on_unknown_label(self):
        tracks = [{"title": "T", "artist": "A", "genres": []}]
        fake_response = {"classifications": [{"index": 0, "mood": "spicy"}]}
        with patch.object(llm_client, "chat_json", return_value=fake_response):
            out = llm_client.classify_moods(tracks)
        assert out == ["chill"]

    def test_empty_input_short_circuits(self):
        with patch.object(llm_client, "chat_json") as mock:
            out = llm_client.classify_moods([])
        assert out == []
        assert mock.call_count == 0


# ============================================================
# Tests: prompt structure (sanity - no exhaustive prompt-engineering tests)
# ============================================================

class TestPromptShape:
    def test_lang_prompt_describes_allowed_codes(self):
        assert "en" in llm_client._LANG_SYSTEM_PROMPT
        assert "instrumental" in llm_client._LANG_SYSTEM_PROMPT
        assert "other" in llm_client._LANG_SYSTEM_PROMPT

    def test_mood_prompt_describes_5_labels(self):
        for mood in ("chill", "melancholy", "energetic", "nostalgic", "focus"):
            assert mood in llm_client._MOOD_SYSTEM_PROMPT
