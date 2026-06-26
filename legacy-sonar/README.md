# Legacy Sonar code (archived)

> **This folder contains the previous "Sonar" MVP that was archived on
> 2026-06-26 when the MVP pivoted to Reset Radar.** Nothing here runs
> as part of the active product. Preserved for audit + the three
> reusable components that were carried over.

---

## Why the pivot happened

The original Sonar MVP was a **user-initiated** intent box: the user
types a sentence ("upbeat Spanish, not reggaeton, things I haven't
heard"), Sonar parses it into a typed Intent, plans Spotify queries,
calls `/recommendations` + `/audio-features`, and ranks 20 tracks with
per-track explanations.

Three problems with that design surfaced in late-stage review:

1. **It only helps users who already know they're stuck.** The root
   cause analysis in `03-research-and-deck/problem-definition/one-pager.md`
   identifies "no fast correction mechanism" (mechanism 3) as the
   structural gap. A user-initiated tool doesn't address it - the
   stuck user has to think to act.
2. **Spotify shipped AI Playlist (2024-25)** which covers the
   user-initiated case directly. The architectural distinction Sonar
   relied on ("we don't write to your taste profile") was too subtle
   to defend in a 90-second demo.
3. **Spotify removed `/recommendations` and `/audio-features` for new
   apps** in Nov 2024. Sonar's design depended on both. The new MVP
   architecture (Reset Radar) was rebuilt around the post-cut API
   surface from day one.

The new MVP (**Reset Radar**) is **system-initiated**: passive weekly
stuck-detection across 4 dimensions + a scoped, reversible reset
session. See `02-mvp/doc/architecture.md` for the full new spec.

---

## What's in this folder

| Path | What it was | Disposition |
|---|---|---|
| `src/llm/client.py` | Throttled Groq wrapper with tenacity retry | **Carried over** to `backend/app/llm_client.py` (the throttle + retry + JSON helper logic is unchanged; new methods added for `classify_language`, `classify_mood`, `rank_and_explain`) |
| `src/config.py` | Env loading with `python-dotenv` + sensible defaults | **Carried over** to `backend/app/config.py`, refactored to use Pydantic `BaseSettings` + new Reset Radar env variable set |
| `.streamlit/config.toml` | Spotify dark theme tokens (`#1DB954`, `#191414`, `#232323`) | **Carried over** to `frontend/src/theme.js` as JS constants |
| `src/llm/intent.py` | Groq-based intent parser (Sonar's LLM call #1) | **Not carried** - Reset Radar has no intent parser; passive detection replaces it |
| `src/llm/planner.py` | Groq-based query planner (Sonar's LLM call #2) | **Not carried** - Reset Radar's `reset_engine.py` builds Spotify search queries directly from scope, no LLM planning needed |
| `src/llm/reasoner.py` | Groq-based rank + explain | **Logic conceptually inherited** - `reset_engine.py` includes a similar `rank_and_explain` step, but the prompt + input shape are different (now scope-aware, smaller candidate pool, simpler output schema) |
| `src/spotify/client.py` | Mock Spotify catalog + abstract client interface | **Not carried directly** - Reset Radar's `mock_data/mock_candidates.json` is structurally simpler; the catalog-style synthetic data here is a reference for the JSON fixture format |
| `src/schema.py` | Pydantic shapes (Intent, QueryPlan, CandidateTrack, RankedTrack, Playlist) | **Not carried** - Reset Radar's Pydantic shapes are different (WeeklySnapshot, StuckScore, Nudge, ResetSession, ResetTrack); only the candidate-with-explanation pattern is conceptually similar |
| `src/pipeline.py` | End-to-end Sonar orchestrator | **Not carried** - Reset Radar has two separate pipelines (detection job + reset session) instead of one user-flow orchestrator |
| `app/streamlit_app.py` | Streamlit UI for Sonar | **Not carried** - Reset Radar uses React + FastAPI, not Streamlit |
| `scripts/smoke_test.py` | End-to-end smoke test for Sonar pipeline | **Not carried** - Reset Radar's tests live in `backend/tests/` |
| `tests/test_intent_parser.py`, `tests/test_planner.py` | Unit tests for Sonar | **Not carried** - Reset Radar's tests are unit tests for `detection.py` + `reset_engine.py` |
| `data/` | Any cached test data from Sonar runs | **Frozen** - not used by Reset Radar |
| `.env.legacy`, `.env.example.legacy`, `requirements.txt.legacy` | Old env + dependency files | **Frozen** - the working `GROQ_API_KEY` was copied to the new `backend/.env`; backend dependencies are completely different |

---

## If you need to recover something from this folder

1. Read the new spec first in `02-mvp/doc/architecture.md` to confirm
   the component you want is genuinely missing from Reset Radar.
2. If it really is missing, copy the relevant file's body (not the
   imports) into the appropriate `backend/app/` file and adapt the
   imports to the new structure.
3. **Do not** re-add `streamlit`, `intent.py`, `planner.py`, or the
   `Intent` schema - those are architecturally not part of Reset Radar
   and re-introducing them muddies the deck's "system-initiated" claim.

---

## Why we kept this folder instead of deleting it

- **Audit trail** - the pivot decision is documented; the prior work is
  visible.
- **Three reused components** ship from here into the new MVP - keeping
  the originals visible makes the port reviewable.
- **Disk cost is trivial** (~200 KB of code) and the folder is
  git-ignored at the `.venv/` level only.

If at any point the deck submission ships and this folder is no longer
needed, it can be safely deleted in one step:
`Remove-Item -Path "02-mvp/legacy-sonar" -Recurse -Force`.
