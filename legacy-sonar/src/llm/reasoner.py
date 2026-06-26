"""Result reasoner - rank candidate tracks + attach explanations (LLM call #3).

This is the "Why AI" moneymaker call. Classical recommenders can score, but
they can't defend the pick in natural language tied back to the user's
intent. This module:
  1. Sends the parsed Intent + a compact candidate digest to Groq 70B
  2. Asks the LLM to pick the top N, score them 0-1, and explain each one
  3. Validates every returned track_id against the candidate set (drops hallucinations)
  4. Falls back to a heuristic ranker if Groq fails so the demo never goes blank

The candidate digest is intentionally lean (10 fields per track) so a batch
of 50-100 candidates fits inside the prompt budget.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Iterable

from src.llm.client import GROQ_MODEL_REASONER, GroqError, chat_json
from src.schema import CandidateTrack, Intent, RankedTrack

log = logging.getLogger("mvp.reasoner")


_SYSTEM_PROMPT = """You are the ranking + explanation layer for Spotify Sonar.

You receive (1) the user's parsed Intent and (2) a numbered list of candidate
tracks with audio features. Pick the top N tracks that BEST match the intent.

For each pick you return:
- "track_id": MUST be one of the track_ids from the candidate list (never invent)
- "score": float 0.0-1.0. 1.0 = perfect fit, 0.5 = decent stretch, <0.3 = weak.
- "explanation": ONE sentence, <=160 chars, plain English, addressed to the user.
  Reference WHY this track fits THEIR stated intent (mood, language, novelty, activity, etc).
- "novelty_signal": short label, <=40 chars, like "low-mainstream pick", "deep cut",
  "in your stated language", "matches your activity context", "energetic seed match".

Output:
- Return ONLY a JSON object: {"picks":[{"track_id":..., "score":..., "explanation":..., "novelty_signal":...}, ...]}
- Pick exactly N tracks (N supplied in the user prompt).
- Order picks from best to worst (highest score first).
- Never use a track_id that is not in the candidate list.
- Never include the same track_id twice.
- If intent.novelty_level is high (>=7), prefer popularity<60 candidates.
- If intent.novelty_level is low (<=3), prefer popularity>=60 candidates.
- Match the requested languages strictly if they were provided.
"""


def _digest_candidate(idx: int, c: CandidateTrack) -> dict:
    af = c.audio_features or {}
    return {
        "i": idx,
        "track_id": c.track_id,
        "title": c.title,
        "artist": c.artist,
        "lang": c.language,
        "pop": c.popularity,
        "energy": af.get("energy"),
        "dance": af.get("danceability"),
        "valence": af.get("valence"),
        "acoustic": af.get("acousticness"),
        "genres": c.genres[:2] if c.genres else [],
    }


def _heuristic_rank(intent: Intent, candidates: list[CandidateTrack], n: int) -> list[RankedTrack]:
    """Deterministic fallback ranker. Used if Groq fails entirely."""
    pref_langs = set(intent.languages)
    pref_genres = {g.lower() for g in intent.genres}
    mood_set = {m.lower() for m in intent.mood}
    novelty = intent.novelty_level
    target_pop_window = (60, 100) if novelty <= 3 else (15, 55) if novelty >= 8 else (25, 80)
    exclude_lc = {a.lower() for a in intent.exclude_artists}

    def score(c: CandidateTrack) -> float:
        s = 0.0
        if c.artist.lower() in exclude_lc:
            return -1.0
        if c.language and pref_langs:
            s += 0.35 if c.language in pref_langs else -0.20
        if pref_genres and any(g.lower() in pref_genres for g in c.genres):
            s += 0.25
        af = c.audio_features or {}
        if "energetic" in mood_set:    s += 0.15 * (af.get("energy", 0.5))
        if "calm" in mood_set or "soft" in mood_set:
            s += 0.15 * (1 - af.get("energy", 0.5))
        if "uplifting" in mood_set:    s += 0.10 * (af.get("valence", 0.5))
        if "melancholic" in mood_set:  s += 0.10 * (1 - af.get("valence", 0.5))
        lo, hi = target_pop_window
        if lo <= c.popularity <= hi:   s += 0.20
        return s

    scored = sorted(
        ((score(c), c) for c in candidates),
        key=lambda t: t[0],
        reverse=True,
    )
    out: list[RankedTrack] = []
    for s, c in scored[:n]:
        out.append(RankedTrack(
            **c.model_dump(),
            score=max(0.0, min(1.0, 0.5 + s / 2)),
            explanation=(
                f"Heuristic pick: matches your stated "
                f"{'language' if intent.languages else 'mood'} and novelty level."
            ),
            novelty_signal=(
                "low-mainstream pick" if c.popularity < 50 else "familiar territory"
            ),
        ))
    return out


def _validate_picks(
    raw: dict,
    by_id: dict[str, CandidateTrack],
    n: int,
) -> list[RankedTrack]:
    out: list[RankedTrack] = []
    seen: set[str] = set()
    for pick in (raw.get("picks") or [])[: n * 2]:               # tolerate over-supply
        tid = (pick.get("track_id") or "").strip()
        if not tid or tid in seen or tid not in by_id:
            continue
        seen.add(tid)
        score = float(pick.get("score") or 0.0)
        explanation = (pick.get("explanation") or "").strip()
        novelty_signal = (pick.get("novelty_signal") or "").strip() or "Sonar pick"
        if not explanation:
            continue
        c = by_id[tid]
        out.append(RankedTrack(
            **c.model_dump(),
            score=max(0.0, min(1.0, score)),
            explanation=explanation[:200],
            novelty_signal=novelty_signal[:60],
        ))
        if len(out) >= n:
            break
    return out


def rank_and_explain(
    intent: Intent,
    candidates: Iterable[CandidateTrack],
    *,
    n: int | None = None,
) -> list[RankedTrack]:
    """Rank candidates and attach per-track explanations.

    Always returns at least one RankedTrack as long as `candidates` is
    non-empty - falls back to a deterministic ranker on any LLM failure.
    """
    candidates = list(candidates)
    if not candidates:
        return []
    n = n or intent.target_track_count
    n = max(1, min(50, n))

    by_id = {c.track_id: c for c in candidates}
    # Cap the LLM input - keep top 60 by popularity-weighted heuristic so we
    # don't blow the context window for huge candidate pools.
    if len(candidates) > 60:
        candidates = sorted(candidates, key=lambda c: c.popularity, reverse=True)[:60]

    digest = [_digest_candidate(i, c) for i, c in enumerate(candidates)]

    user_payload = (
        f"INTENT:\n{intent.model_dump_json(indent=0)}\n\n"
        f"N: {n}\n\n"
        f"CANDIDATES (compact JSON list):\n{json.dumps(digest, ensure_ascii=False)}"
    )

    try:
        raw = chat_json(
            system=_SYSTEM_PROMPT,
            user=user_payload,
            model=GROQ_MODEL_REASONER,
            temperature=0.3,
            max_tokens=1400,
        )
    except GroqError as exc:
        log.warning("Reasoner LLM call failed (%s); using heuristic ranker.", exc)
        return _heuristic_rank(intent, candidates, n)

    picks = _validate_picks(raw, by_id, n)
    if not picks:
        log.warning("Reasoner returned no usable picks; falling back to heuristic.")
        return _heuristic_rank(intent, candidates, n)
    if len(picks) < n:
        # Top-up with heuristic picks the LLM didn't include
        log.info("Reasoner returned %d/%d picks; topping up via heuristic.", len(picks), n)
        already = {p.track_id for p in picks}
        extras = [c for c in candidates if c.track_id not in already]
        picks.extend(_heuristic_rank(intent, extras, n - len(picks)))
    return picks[:n]


__all__ = ["rank_and_explain"]
