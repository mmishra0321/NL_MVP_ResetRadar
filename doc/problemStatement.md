# Problem Statement - MVP (Part 4): Reset Radar

> **PIVOT NOTE (2026-06-26):** This file was rewritten when the MVP
> pivoted from "Sonar" (user-initiated intent box) to **Reset Radar**
> (system-initiated stuck-detection + scoped reset). The reasoning for the
> pivot is captured in [`architecture.md`](./architecture.md) §0 (top
> note) and §1.
>
> Companions:
> - [`architecture.md`](./architecture.md) - how Reset Radar is built
> - [`../../03-research-and-deck/problem-definition/one-pager.md`](../../03-research-and-deck/problem-definition/one-pager.md) - the root-cause analysis Reset Radar answers
> - [`../../01-ai-review-engine/doc/problemStatement.md`](../../01-ai-review-engine/doc/problemStatement.md) - the full project brief

---

## 1. What this MVP must do (per the project brief)

From Part 4 of the project brief:

> *Based on your insights, design and build a functional MVP. The MVP
> may take the form of a prototype for a feature within the existing
> product or an agent. You need to deploy these to production. The MVP
> must demonstrate why AI is uniquely suited to solving this problem.*

**Locked decisions (post-pivot, 2026-06-26):**

| Decision | Locked value |
|---|---|
| Product name | **Reset Radar** |
| Form factor | Companion web app (FastAPI backend + React frontend) - **not** an embedded Spotify-shell mock |
| Initiation model | **System-initiated** (passive monitoring, proactive nudge) - **not** user-initiated |
| Backend "AI work" | Statistical detection (jaccard + Shannon entropy) + Groq LLM for language/mood classification + per-track ranking + explanation |
| Deployment | Public URL via Render (backend) + Vercel (frontend); mock mode is the default for the live demo |
| Linked from | Deck slide 5 (Why AI), slide 7 (Solution detail), slide 8 (Live screenshots) |

---

## 2. The problem Reset Radar exists to solve

From `03-research-and-deck/problem-definition/one-pager.md`, the root
cause of the stuck-loop problem is three structural mechanisms in
Spotify's existing recommendation system:

1. **Recency dominance** - one off-pattern session distorts recommendations for 2 weeks to 4 months
2. **Self-reinforcing feedback loop** - each like narrows the radius of future suggestions; no decay; no counter-pressure
3. **No fast correction mechanism** - snooze, hide, thumbs-down, refresh, private session are too narrow or too cosmetic to undo (1) and (2)

The third mechanism is the one **Reset Radar directly addresses**:

> **Spotify's correction surface is entirely reactive and entirely narrow.
> Snooze removes one song. Hide removes one artist. Thumbs-down corrects
> one play. There is no surface that says "your overall diversity has
> collapsed - here is a scoped, reversible way to break out."**
>
> **Reset Radar is that surface.**

Mechanisms (1) and (2) are addressed by **scoping** (you reset *only*
the dimension that collapsed) and **reversibility** (the trial doesn't
permanently rewrite anything until you say "Keep").

---

## 3. The "Why AI" defense the MVP must prove

Reset Radar requires AI for four specific reasons that classical
recommender architectures structurally cannot match:

| Capability | Why a classical recommender cannot do this | Where Reset Radar uses AI |
|---|---|---|
| **Multi-axis statistical detection that decides when to speak up** | Recommenders react to a click; they don't *initiate*. They have no model of "the user is stuck across these specific axes". | `detection.py` computes jaccard + entropy across 4 dimensions weekly; the trigger fires only when statistical stagnation persists, not on any single signal. |
| **Language classification from text alone** | Spotify has no language field in its public API; classical systems treat language as a black-box feature of the embedding. | Groq Llama classifies language from artist name + track titles + genre tags. |
| **Mood inference without audio features** | Spotify's `/audio-features` endpoint was removed for new apps in Nov 2024 - classical recommenders that depended on it are now disabled. | Groq classifies mood from genre + text metadata, treated as an explicit approximation. |
| **Per-track natural-language explanation tied to a scope** | A vector dot-product is not an explanation - it's a rationalisation. | `reset_engine.py` calls Groq to write a one-sentence "why this track fits your reset of dimension X" per track. |

**At least 3 of these 4 must be visibly demonstrable in the live UX.**
(Statistical detection + per-track explanation are non-negotiable;
language and mood classification appear in the dashboard chart and the
reset scope picker.)

---

## 4. Target user (locked from P2 + P3)

**Stuck Heavy Premium Listener** - defined by all five of:

| # | Criterion | Threshold |
|---|---|---|
| 1 | Plan | Spotify Premium (any sub-tier) |
| 2 | Tenure | ≥ 3 years on Premium |
| 3 | Usage | ≥ 5 days/week active |
| 4 | Self-awareness | Recommendations have felt stale in the last 6 months |
| 5 | Intent | Wishes they discovered new music more often |

**Sizing:** ~55M globally (268M Premium × 55% heavy × 37% stuck-staleness;
sensitivity in `business-case.md`).

**Sub-segment:** Stuck Multilingual Premium Listener - same criteria
plus listening regularly in 2+ languages with distinct genre preferences
per language. ~2-4M globally. Suffers all primary pain plus
"language-treated-as-genre" overlay.

**Personas:** Aanya (median Stuck Premium, monolingual) and Karthik
(Stuck Multilingual Premium). Full personas in
[`../../03-research-and-deck/problem-definition/personas.md`](../../03-research-and-deck/problem-definition/personas.md).

---

## 5. The MVP's job-to-be-done (post-pivot)

### Primary JTBD

> **When I have been listening to the same narrow slice of music for
> several weeks without noticing,
> I want Spotify to tell me, suggest a way out that I can try without
> commitment, and then let me decide whether to keep it,
> so I can break out of comfort loops without rebuilding my entire
> profile from scratch.**

### Secondary JTBD (multilingual sub-segment)

> **When my recommendations have collapsed along one language axis,
> I want to reset just that language without touching the others,
> so my Carnatic-in-Telugu listening doesn't get diluted when I try
> something new in English.**

The **scoped** reset (just genre, OR just language, OR just era, OR just
mood) is the structural answer to the second JTBD. It exists because the
sub-segment explicitly asked for it ("don't treat my Telugu listening as
Telugu film music" - Vikram, interview 02).

---

## 6. Functional requirements (locked)

1. **Passive weekly snapshot.** Backend computes a snapshot of the user's
   top tracks, recently played, and saved library every week. No user
   action required.
2. **Four-dimension diversity scoring.** Each snapshot decomposes into
   four dimensions: genre, language, era, mood. Each dimension gets a
   stuck-score 0-1 computed via the formulas in `architecture.md` §2.
3. **Statistical trigger.** A nudge fires only when
   `overall_stuck_score > STUCK_THRESHOLD` (default 0.6) for
   `STUCK_STREAK_WEEKS` (default 3) consecutive weeks, AND no nudge
   shown in the last `COOLDOWN_WEEKS` (default 4), AND no reset session
   currently active.
4. **Suggested scope.** When the nudge fires, the worst-scoring
   dimension is pre-selected as the suggested reset scope; the user can
   override.
5. **Scoped reset.** The reset playlist is built via `GET /search` with
   field filters keyed to the chosen scope (e.g.
   `genre:"carnatic" year:2015-2026`) - **not** via Spotify's own
   `/recommendations` endpoint (which has been removed for new apps).
6. **Optional free-text intent.** Beyond the scope choice, the user can
   add a sentence ("upbeat Spanish, not reggaeton") that further
   constrains the search.
7. **Groq ranking + per-track explanation.** The candidate pool (60-80
   tracks from paginated search) is ranked by Groq Llama 3.x; each of
   the top 20 gets a one-line natural-language "why".
8. **Real Spotify playlist creation.** The reset playlist is created in
   the user's actual Spotify account via `POST /me/playlists` (with the
   `items` endpoint rename from Feb 2026).
9. **Time-boxed trial.** Each reset session has `trial_end_date = now +
   TRIAL_WINDOW_DAYS` (default 10). Until that date, the user is in
   "trial mode".
10. **Keep / Revert decision.** After the trial:
    - **Keep:** follow the top-N promoted artists, save the top tracks
    - **Revert:** delete the Spotify playlist, mark session reverted,
      nothing else changes
11. **Mock mode for the live demo.** `MOCK_MODE=true` runs the entire
    flow against synthetic fixtures with zero live Spotify calls. This
    is the **default configuration for the deck demo**.
12. **Weekly GitHub Action cron.** A scheduled workflow calls
    `POST /jobs/run-detection` weekly, evidence that the system is
    designed proactive even though the live demo triggers manually.
13. **Deployed to production.** Public URL clickable from the deck.

---

## 7. Out of scope (this MVP)

- **Backend-enforced sandboxing of the trial.** No public Spotify API
  allows a third party to exclude listening from the user's internal
  Spotify model. The sandbox is UX-level only. Documented honestly.
- **Production-grade language detection.** LLM classification is an
  approximation, good enough for a demo.
- **More than 25 users.** Spotify Development Mode caps allow-listed
  users at 25.
- **Mobile-native client.** Web only.
- **Real audio playback / streaming licenses.** We link out to Spotify.
- **Replacement for Discover Weekly / Daily Mix / AI DJ.** Reset Radar is
  a *correction layer*, not a primary discovery surface.

---

## 8. Success criteria

- [ ] **Live public URL** clickable in the final deck (both backend +
      frontend reachable)
- [ ] **Mock-mode end-to-end flow works in <90 seconds**: dashboard →
      nudge → scope picker → reset playlist → skip-to-outcome → keep or
      revert
- [ ] **Detection trigger fires on week 6 of the synthetic fixture** with
      `overall_stuck_score > 0.6` and the 3-week streak rule satisfied
- [ ] **20-track reset playlist** with non-empty `why` for every track
- [ ] **Zero hallucinated track IDs** (every track in the playlist
      exists in the candidate pool)
- [ ] **At least 3 of 4 "Why AI" capabilities** visibly demonstrable
      (statistical detection + per-track explanation + at least one of
      language/mood classification)
- [ ] **Honest scoping** copy present in the README and the deck:
      "sandbox is UX-level, not backend-enforced"
- [ ] **GitHub Action workflow file** exists and `workflow_dispatch`
      succeeds against the deployed backend
- [ ] **3 deck screenshots** captured at 1920×1080: Dashboard with
      active nudge / Reset playlist / Keep-or-Revert

---

## 9. Open questions (resolve during R1-R3)

1. **Recharts vs Tremor** for the stuck-score chart - decide by R3 based
   on which gives the dark-theme look with the least styling effort.
2. **Whether the trial window should be visible in mock mode** or
   replaced with a "skip to outcome" button - default is the button, but
   if the chart visualisation is strong enough we may keep the date
   countdown for narrative impact.
3. **How many promoted artists to follow on "Keep"** - placeholder is 5,
   tune during R5.
4. **Whether to show the per-dimension stuck-score breakdown on the
   nudge card** or only on the dashboard - default is the dashboard
   only; nudge card stays minimal.
5. **Backend deployment target** (Render vs Railway vs Fly) - decide at
   R7 based on which has the most painless free tier for FastAPI +
   SQLite.

---

## 10. Acceptance gates (build-order checkpoints)

| Phase | Gate that proves it's done |
|---|---|
| **R0** | New folder structure exists; legacy Sonar code is archived; Groq client carried over |
| **R1** | Unit tests pass; detection fires correctly on the synthetic 8-week fixture |
| **R2** | `POST /reset-sessions` returns 20 tracks + whys against mock candidates |
| **R3** | **Demo is presentable from here.** Full mock-mode flow works in incognito browser |
| **R4** | Real Spotify OAuth completes for the developer's Premium account; detection runs on real top-tracks data |
| **R5** | Real reset session creates a visible playlist in the Spotify app; keep/revert mutate the user's library correctly |
| **R6** | `workflow_dispatch` of the cron file succeeds against the deployed backend |
| **R7** | Live URL works in incognito; three screenshots saved to deck assets folder |

---

## 11. Why this MVP is the right answer to the locked problem

The problem (per P3): three structural mechanisms in Spotify's
recommender compound on one taste vector, and the existing correction
tools are too narrow to undo them.

The MVP (Reset Radar):
- **Acts proactively** - mechanism (3) was "no fast correction"; Reset
  Radar removes the "you have to notice you're stuck" prerequisite.
- **Acts at the right granularity** - mechanisms (1) and (2) compound
  *along specific axes*; Reset Radar lets the user correct **just the
  collapsed axis**, not the whole profile.
- **Acts reversibly** - the trial + Keep/Revert decision means trying a
  reset is **literally free**; this is the missing ingredient that
  unblocks the stuck cohort's behavioural willingness to explore.

Without all three together, the existing Spotify tools (and the closest
existing AI feature, AI Playlist) cannot break the loop architecturally.
Reset Radar can, because its design is causally aligned with the
root-cause analysis from P3 - not bolted on top of an existing surface.
