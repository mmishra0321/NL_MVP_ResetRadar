# 02-mvp · Reset Radar

> **Reset Radar** is a system-initiated companion app that passively
> monitors a Spotify Premium user's listening diversity across four
> axes (genre, language, era, mood), detects stagnation using jaccard
> overlap + Shannon entropy, and offers a **scoped, reversible reset**
> when stuck-ness crosses threshold.
>
> Read first: [`doc/problemStatement.md`](doc/problemStatement.md),
> then [`doc/architecture.md`](doc/architecture.md).

---

## Status (2026-06-26)

| Phase | What it does | State |
|---|---|---|
| **R0** Pivot + scaffold | Move old Sonar to `legacy-sonar/`, scaffold `backend/` + `frontend/`, carry over Groq client + config + palette | ✅ |
| **R1** Detection engine (mock-first) | Implement formulas, ship `synthetic_weeks.json` fixture, unit tests | ✅ |
| **R2** Reset engine (mock candidates + Groq) | Build search queries from scope, Groq rank + explain, ship `mock_candidates.json` | ✅ |
| **R3** Frontend (mock-driven end-to-end) | React UI complete on top of mock backend | ✅ |
| **R4** Spotify OAuth + read endpoints | Wire real Spotify Web API reads behind `MOCK_MODE=false` | ✅ |
| **R5** Spotify write endpoints | Real playlist create / follow / save / delete | ✅ |
| **R6** GitHub Action + polish | Lock weekly cron workflow, polish UI, lock demo script | ✅ |
| **R7-local** Capture deck screenshots | 3 frames at 1920×1080 in `assets/mvp-screenshots/`; cloud deploy deferred | ✅ |
| **R8** Real-mode toggle + observability | Mode switcher card (Demo ↔ Connect Spotify), `/jobs/runs/*` API, `LastRunCard`, `/runs` page with 4-step trace per user, hybrid mode (mock + OAuth user folded in same run) | ✅ |
| **R9** Spotify-home UI reframe | OAuth UI removed (backend routes retained, unused). Two-persona user-journey deck slide for Aanya (genre stuck) + Karthik (language stuck). | ✅ |
| **R10** Spotify web-player home as the entry point | `/` is now `HomePage` rendering a **desktop Spotify-web layout** (left sidebar, top bar, "Recently played" grid with album-art-style covers) with the **Reset Radar nudge embedded as a feed card** between greeting and tiles. Chart dashboard moved to `/engine`. Deck slide 9 gains an **"honest gap"** callout (sandbox is UX-level, not backend-enforced; v2 partnership). | ✅ |

> **R3 is the demo-presentable stopping point.** Everything from R0
> to R3 runs against synthetic fixtures with **zero Spotify API calls**.
> R4-R7 are fidelity upgrades from there, not prerequisites.

---

## Folder structure

```
02-mvp/
├── backend/                # FastAPI + SQLite + SQLAlchemy
│   ├── app/
│   │   ├── main.py         # FastAPI entry point
│   │   ├── config.py       # Pydantic Settings (.env reader)
│   │   ├── llm_client.py   # Groq throttled wrapper (carried over)
│   │   ├── db.py           # SQLAlchemy engine + init_db()
│   │   ├── models.py       # 6 ORM tables + Pydantic wire shapes
│   │   ├── spotify_client.py   # Mock-mode-first Spotify wrapper
│   │   ├── detection.py    # Stuck-detection math (R1)
│   │   ├── reset_engine.py # Candidate gen + LLM ranking (R2)
│   │   └── routes/         # FastAPI route modules
│   ├── mock_data/          # synthetic_weeks.json + mock_candidates.json
│   ├── tests/              # pytest unit tests
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                # local secrets (git-ignored)
├── frontend/               # React + Vite + Recharts
│   ├── src/
│   │   ├── main.jsx        # ReactDOM entry
│   │   ├── App.jsx         # Router shell
│   │   ├── theme.js        # Spotify palette tokens (carried over)
│   │   ├── styles.css      # Global CSS + reset
│   │   ├── api/client.js   # Fetch wrapper around the backend
│   │   ├── pages/          # Dashboard.jsx + ResetFlow.jsx
│   │   └── components/     # StuckScoreCard, ScopePicker, ResetPlaylistView, KeepOrRevertCard
│   ├── package.json
│   └── vite.config.js
├── .github/
│   └── workflows/
│       └── weekly-detection.yml   # Monday 09:00 UTC cron (architecture §10)
├── doc/
│   ├── problemStatement.md         # MVP-scoped problem definition
│   └── architecture.md             # Full MVP spec (the source of truth)
├── legacy-sonar/                   # Archived old Sonar code (see README inside)
└── README.md                       # this file
```

---

## How to run (R0 state)

R0 ships the **shell only**. Real route bodies arrive in R1-R5. After
R0, you should be able to:

### Backend

```powershell
# From C:\Users\tiwari.mahima\Mayank\02-mvp
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
python -c "from app.config import settings; print('mock_mode =', settings.mock_mode, '| db =', settings.database_url)"
uvicorn app.main:app --reload --port 8000
# then visit http://127.0.0.1:8000/health
# every other endpoint returns 501 until R1+
```

### Frontend

```powershell
# From C:\Users\tiwari.mahima\Mayank\02-mvp\frontend
npm install
npm run dev
# then visit http://localhost:5173
# you should see the Dashboard placeholder with a demo Recharts chart
# and the ResetFlow placeholder with the four scope buttons
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000`, so
both processes need to be running for end-to-end calls (which start
returning real data in R1).

---

## Three components carried over from old Sonar

| Old file | New home | Why kept |
|---|---|---|
| `legacy-sonar/src/llm/client.py` | `backend/app/llm_client.py` | The throttled-Groq-with-retry pattern is identical between the two MVPs - the only changes are config-source and the three Reset-Radar-specific methods added (stubs in R0) |
| `legacy-sonar/src/config.py` | `backend/app/config.py` | Same idea, refactored to Pydantic Settings + the new variable set |
| `legacy-sonar/.streamlit/config.toml` | `frontend/src/theme.js` | The Spotify palette tokens (`#1DB954`, `#191414`) are the same; the rendering layer changed from Streamlit to React |

See `legacy-sonar/README.md` for the full disposition table.

---

## Mock mode (`MOCK_MODE=true`)

Reset Radar's **live demo runs entirely against synthetic data**.
There is no Spotify call in the R0-R3 path. This is intentional:

- Spotify's Development Mode caps allow-listed users at 25.
- The deck reviewer should be able to run the live URL without
  needing to be allow-listed.
- Mock mode lets the detection math + LLM ranking + the React flow
  be reviewed independently of Spotify availability.

To switch to real Spotify (R4+), set `MOCK_MODE=false` in
`backend/.env` and fill in the Spotify credentials.

---

## Real-mode setup (R4 -- only if you want to leave mock mode)

R4 wires the four Spotify read endpoints (`/me/top/tracks`,
`/me/player/recently-played`, `/me/tracks`, `/artists/{id}`) plus an
OAuth Authorization Code + PKCE flow. To flip a local backend into real
mode you need a Spotify Developer app and an allow-listed Premium
account.

### 1. Create a Spotify Developer app

1. Visit https://developer.spotify.com/dashboard and sign in with the
   Spotify account whose listening Reset Radar will analyse.
2. **Create app** → name it `Reset Radar (local)` (description is
   anything).
3. Open the app → **Settings** → **Edit**:
   - **Redirect URIs**: add `http://127.0.0.1:8000/auth/callback`
   - **Which API/SDKs are you planning to use?**: tick **Web API**
   - Save.
4. Stay on the Settings tab and copy the **Client ID**. The Client
   Secret is *not* required (Reset Radar uses PKCE).

### 2. Allow-list yourself

While the app is in Development Mode, Spotify only honours OAuth from
explicitly allow-listed accounts:

1. Open the app → **User Management**.
2. Add the email associated with the Spotify Premium account you'll use
   to log in. (Up to 25 users without Extended Quota approval.)

### 3. Fill in `backend/.env`

```dotenv
GROQ_API_KEY=...                  # the same key R1+R2 used
MOCK_MODE=false                   # flip OFF
SPOTIFY_CLIENT_ID=<from step 1.4>
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/auth/callback
SESSION_SECRET_KEY=<output of: python -c "import secrets;print(secrets.token_urlsafe(48))">
FRONTEND_ORIGIN=http://127.0.0.1:5173
```

### 4. Walk the flow

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
# In another shell:
start http://127.0.0.1:8000/auth/login
# Spotify consent screen -> callback -> redirected back to localhost:5173
# Cookie `rr_session` is now set in your browser.
curl http://127.0.0.1:8000/auth/me
# Should show authenticated: true + your Spotify display name.
curl -X POST http://127.0.0.1:8000/jobs/run-weekly-detection
# Fetches your top tracks + recently played + saved library, calls
# Groq twice (language + mood batches), appends one WeeklySnapshot
# row, runs detection over your history.
```

> First-time real-mode run will create exactly **one** weekly snapshot,
> so the trigger rule (3-week streak above threshold) will deliberately
> stay quiet. That's the expected acceptance gate per
> `doc/architecture.md` R4 ("either fires a nudge or correctly stays
> quiet"). Build history by re-running each week, or stick with mock
> mode for the demo.

### What R4 does NOT do

- It does NOT switch the frontend default to real mode. The Dashboard
  still calls the same backend; `MOCK_MODE` is the single switch.
- It does NOT replace the deck-day demo. Mock mode remains the live-URL
  default per architecture R7.

---

## Real-mode writes (R5 -- create playlist, follow, save, unfollow)

R5 wires the four write endpoints so that when `MOCK_MODE=false`:

| Endpoint | When | Effect |
|---|---|---|
| `POST /me/playlists` | `POST /reset/sessions` | Creates a private playlist in the user's Spotify account |
| `POST /playlists/{id}/items` | `POST /reset/sessions` | Adds the 20 LLM-ranked tracks (note: `/items`, not the deprecated `/tracks`) |
| `PUT /me/following?type=artist&ids=...` | `POST /reset/sessions/{id}/decide` (Keep) | Follows every unique artist on the reset playlist - satisfies the R5 acceptance gate ("Keep adds 5+ artists to followed list") |
| `PUT /me/tracks?ids=...` | `POST /reset/sessions/{id}/decide` (Keep) | Saves the reset tracks to the user's library so they survive playlist deletion |
| `DELETE /playlists/{id}/followers` | `POST /reset/sessions/{id}/decide` (Revert) | Unfollows (= removes) the playlist - Spotify has no DELETE /playlists endpoint; this is the canonical pattern |

The "Keep" handler additionally calls `GET /tracks?ids=...` once to
resolve unique artist IDs from the reset track IDs - that's the input
to the follow-artists call.

### Architecture deviation note

`02-mvp/doc/architecture.md` describes the Keep action as `PUT /me/library`
(a generic save/follow endpoint). In production Spotify, that endpoint
doesn't exist as a single surface - the canonical paths are per-type:
`PUT /me/following` for artists, `PUT /me/tracks` for songs. R5 uses
both. The architecture wording was a forward-looking simplification.

### What R5 does NOT do (yet)

- It does NOT measure the post-reset stuck score. `after_stuck_score`
  is still the same heuristic projection (`before × 0.6` on keep) used
  in mock mode. A measured `after_stuck_score` requires next Monday's
  cron to land a fresh weekly snapshot - that's R6 territory.

---

## R6 -- Weekly cron + UI polish + demo script

R6 closes the system-is-proactive story (the weekly GitHub Action) and
the demo-readiness story (loading skeletons, mode badge, login CTA,
five-step script).

### GitHub Actions weekly cron

File: [`.github/workflows/weekly-detection.yml`](.github/workflows/weekly-detection.yml)

- Cron: **`0 9 * * 1`** (Mondays 09:00 UTC), per architecture §10.
- Also `workflow_dispatch` so the Actions tab gets a manual "Run
  workflow" button (with a `dry_run` toggle).
- Calls `POST /jobs/run-detection` (the canonical name per
  architecture §6). The legacy `/jobs/run-weekly-detection` is kept as
  an alias so the R3 frontend's existing call point keeps working.
- Auth: optional `Authorization: Bearer <RESET_RADAR_API_TOKEN>`,
  matching the backend's `JOBS_API_TOKEN` env var. When the backend
  leaves `JOBS_API_TOKEN` empty (local dev + the single-tenant demo
  deploy), the workflow can also leave the secret empty and the call
  succeeds unauthenticated.
- Configure two GitHub repo secrets to enable:
  - `RESET_RADAR_API_URL` &mdash; e.g. `https://reset-radar.onrender.com`
  - `RESET_RADAR_API_TOKEN` &mdash; only if you set `JOBS_API_TOKEN` on the backend
- Each run uploads `response.json` as an artefact (30-day retention)
  and writes a per-run summary into the Actions UI.

### Frontend polish

- **Mode badge** in the top-right corner of the Dashboard: a green
  pill when `MOCK_MODE=true`, a blue one when running against live
  Spotify. The pill links the visible mode to the underlying truth so
  nobody has to guess.
- **Login with Spotify CTA**: appears next to the mode badge ONLY in
  live mode AND when `/auth/me` reports `authenticated: false`. In
  mock mode it stays hidden (OAuth is intentionally bypassed in mock
  mode; showing a login button would be a lie).
- **Loading skeletons** for the chart card + the per-dimension grid
  while `GET /scores/history` is in flight. No more blank pane on
  first paint or persona switch.
- **Footer copy** branches on mode &mdash; mock-mode footer points at
  `synthetic_weeks.json`; real-mode footer enumerates the Spotify
  endpoints actually being read and names the LLM model in use.
- Frontend now calls the canonical `/jobs/run-detection` and sends
  `credentials: 'include'` so the R4 session cookie travels with the
  request.

### Demo script

Five steps, **&le; 90 seconds**, cold-open &rarr; Keep outcome. See
[`doc/DEMO_SCRIPT.md`](doc/DEMO_SCRIPT.md). It includes a pre-flight
checklist, on-stage troubleshooting table, and a morning-of smoke
check.

### What R6 does NOT do (yet)

- It does NOT deploy anything. R7-local captures the deck screenshots
  against `localhost` and intentionally defers the cloud deploy.
- It does NOT implement a real measured `after_stuck_score`. That
  arrives naturally on the next weekly cron run after a Keep decision
  in real mode; the frontend already labels the current value as a
  projection.

---

## R8 -- Real-mode toggle + GH Action observability + run trace

R8 is the **observability + onboarding** layer. It doesn't change the
detection math or the reset flow — it makes the existing engine
*legible* to a reviewer who's never read the code. Three reviewer
questions get answered on screen:

| Reviewer question | R8 answer on screen | Backend source |
|---|---|---|
| *"How do I switch from demo personas to my own Spotify data?"* | **Mode Switcher card** at top of Dashboard. `Active data: Demo personas` shows the current state with a `Connect Spotify` CTA. After OAuth, the same card flips to `Live + Demo` (hybrid) or `Live Spotify` (real-only deploy). | `_run_real_mode(allow_empty=True)` in `routes/jobs.py` folds OAuth-authenticated users into the mock-mode pass when `MOCK_MODE=true` |
| *"When did the weekly GitHub Action last fire, and what did it do?"* | **Last Detection Run card** on Dashboard. Shows `Xs/m/h/d ago`, exact timestamp, users processed, snapshots, scores, nudges fired, duration, mode badge (`MOCK` / `HYBRID` / `REAL`), and a link to `/runs`. | `GET /jobs/runs/last` returns the most recent `JobRun` row |
| *"What did the cron decide for each user, step by step?"* | **`/runs` page** with one row per detection call, expandable to a per-user 4-step trace: **1 LOAD** (snapshot count) → **2 FORMULAS** (overall + streak + suggested dimension) → **3 TRIGGER** (`pass / hold` + human-readable reason) → **4 NUDGE?** (`fired` + `nudge_id`). | `GET /jobs/runs` list view + `GET /jobs/runs/{id}` full trace |

### Hybrid mode (the real-mode-toggle implementation)

`MOCK_MODE` stays a backend env flag — flipping it requires restarting
the server, which is the wrong UX. R8's contribution: when
`MOCK_MODE=true` and any user row carries an `access_token`, the
detection job **also runs a real-mode pass for those users** and
merges the results into the same `JobRun`. Result:

- Logged-out reviewer: sees demo personas only (current behaviour).
- Reviewer clicks "Connect Spotify" → OAuth → returns to Dashboard:
  the **next** detection run includes them in a `hybrid` run, with
  their real chart available via the user picker.
- The deck screenshots, the demo script, and the GH Action all keep
  working unchanged — hybrid is purely additive.

### What R8 does NOT do

- It does NOT change the detection math (`detection.py` is untouched).
- It does NOT change the reset flow (`reset_engine.py` is untouched).
- It does NOT add a public surface inside the Spotify app. That
  remains slide 10 bet 4 (Spotify partnership for a native surface).
  Reset Radar is still a standalone companion web app today.
- It does NOT measure `after_stuck_score` from real listening — the
  projection caveat from R6 stands.

### Testing

13 new tests in `backend/tests/test_jobs_runs.py` cover JobRun
persistence (mock + dry_run skip), all 3 query endpoints (last / list /
by-id / 404), and hybrid mode regressions (no-OAuth stays mock, OAuth
present folds in, OAuth fetch error stays non-fatal). Full backend
suite stays green: **170 / 170** after R8 (was 157 / 157 at R7).

---

## R9 + R10 -- Spotify-home UI reframe + honest-gap callout

R9 and R10 collapse together because they share a single insight:
**Reset Radar's discoverability claim is only credible if the demo
itself shows the nudge inside the Spotify surface, not in a separate
companion app**. R8 had built a polished diagnostic dashboard with
charts, mode switcher, last-run card, and `/runs` history — all
useful for reviewers, but all wrong as the *primary* surface a user
would meet.

### What changed

| Area | Before (R8) | After (R10) |
|---|---|---|
| Root route `/` | Diagnostic dashboard: stuck-score chart, per-dimension grid, mode switcher, `LastRunCard`, login CTA | `HomePage` rendering a **desktop Spotify-web layout**: left sidebar with Spotify brand + nav (Home/Search/Your Library) + filler playlists, top bar with nav arrows + avatar pill, "Good evening" greeting, and the **Reset Radar nudge embedded as a feed card** between the greeting and "Recently played" |
| "Recently played" tiles | (didn't exist) | 6 gradient album-art-style covers per persona — Bollywood Hits / Romantic Bollywood / Hindi Pop / Indian Indie / Bollywood Sing-Along / Hindi Hits for Aanya; Telugu Film Hits / Telugu Romance / Carnatic Classical (ॐ) / Latest Telugu / Evergreen Telugu / Devotional South India for Karthik. Each cover is a Spotify-style "PLAYLIST + bold letter symbol + colour gradient" tile. |
| Demo-only persona toggle | `<select>` inside the dashboard | `"Demo only · Viewing as: Aanya | Karthik"` pill row **above** the Spotify frame, with the disclaimer *"In production this row doesn't exist - you are whoever is signed into Spotify."* |
| OAuth UI | "Connect Spotify" CTA + post-auth flip in Mode Switcher card | **Removed entirely.** Backend OAuth routes still exist (and the API client still tracks `me`-equivalent state through the mode switcher in `/engine`) but the home page no longer surfaces them. R10's stance: don't sell capability we haven't shipped. |
| Chart dashboard | `/` (the primary surface) | `/engine` (linked via a faint "Engine diagnostics →" footer at the bottom of the home page). All R8 work — `LastRunCard`, mode switcher, `/runs` page, per-user step trace — remains intact at `/engine`. |
| Deck slide 9 (frames) | 3 screenshots + mock-mode footer | 3 screenshots + **"Honest gap" callout** between the screenshots and the footer: *"the sandbox is a UX-level guarantee, not a backend one … no public API allows separating the underlying signal Spotify's recommender receives … backend-enforced isolation is a v2 partnership conversation with Spotify directly (slide 11 bet 4)."* Amber-striped panel, full slide width, sits on the same slide as the demo screenshots so it reads as principled scoping, not appendix-burying. |
| Deck slide 8 | (didn't exist) | **New 5-step user-journey slide** — Aanya (English-indie / genre-stuck) and Karthik (Telugu+Hindi / language-stuck) side-by-side, six numbered beats each (DISCOVERY → REACTION/WHY-IT-MATTERS → SCOPE → RESET PLAYLIST → TRIAL LISTEN / KEEP-OR-REVERT). Same engine, different decision per user. |
| Deck length | 10 slides | **11 slides** (slide 8 user-journeys is new; slide 9 frames, slide 10 pitfalls, slide 11 future scope renumbered). |

### What R10 does NOT do

- It does NOT remove the diagnostic dashboard — `/engine` still ships
  the full R8 observability suite (mode switcher, last-run card,
  `/runs` history with per-user step traces). The route just isn't
  the front door anymore.
- It does NOT add real Spotify deep-linking from the home page
  tiles — the "Recently played" covers are decorative for the
  discoverability claim, not clickable into Spotify.
- It does NOT make the sandbox backend-enforced. That's the literal
  content of the honest-gap callout: the gap is named, not closed.
- It does NOT change the detection math, the reset engine, the
  candidate generator, the LLM ranking, or the Spotify write
  endpoints. Same backend, repositioned front door.

### Frontend file map (post-R10)

| File | Role |
|---|---|
| `frontend/src/pages/HomePage.jsx` | The new `/` — Spotify-home layout with the embedded nudge card. Loads the latest nudge for the active persona; the persona toggle is the **"Demo only · Viewing as"** row above the Spotify frame. |
| `frontend/src/pages/Dashboard.jsx` | Now mounted at `/engine`. Header renamed to **"Engine diagnostics"** with a link back to home. All R8 observability (mode switcher card, `LastRunCard`, stuck-score chart, per-dimension grid) lives here. |
| `frontend/src/pages/RunsPage.jsx` | Unchanged from R8. Mounted at `/runs`. Per-user 4-step trace (LOAD → FORMULAS → TRIGGER → NUDGE?) for each detection call. |
| `frontend/src/components/LastRunCard.jsx` | Unchanged from R8. Used inside `Dashboard.jsx` (now `/engine`). |
| `frontend/src/App.jsx` | Nav links updated to **Home / Reset / Engine / Runs**. `/` routes to `HomePage`; `/engine` routes to `Dashboard`. |

### Testing (R9 + R10)

No new backend tests — the changes are UI-only and the backend
contract is unchanged from R8. The R8 backend suite (**170 / 170
green**) covers everything the home page consumes (`getLatestNudge`,
`listUsers`, `respondToNudge`). The home page itself was verified via
Playwright screenshots for both demo personas, captured at 1440×950
and copied into the deck assets as
`assets/mvp-screenshots/home-aanya-genre-nudge.png` and
`home-karthik-language-nudge.png`.

---

## R7-local -- 3 deck frames (cloud deploy deferred)

R7's original spec bundled "deploy + capture 3 screenshots". This
round we shipped only the captures against `localhost` and explicitly
deferred the cloud deploy. The reasoning + the resume-path is in
[`doc/architecture.md`](doc/architecture.md) §R7. The actual frames +
their manifest live in
[`../03-research-and-deck/assets/mvp-screenshots/`](../03-research-and-deck/assets/mvp-screenshots/).

The three frames (1920×1080, captured via Playwright against the
running `:8000` + `:5173` servers in mock mode):

| File | Captures |
|---|---|
| `frame-a-dashboard.png` | Dashboard with mock-mode badge, Karthik nudge ("language mix has repeated 86%"), 8-week stuck-score chart + threshold, per-dimension grid, honest mode footer |
| `frame-b-reset-playlist.png` | 19 LLM-ranked tracks across Spanish / French / Portuguese / Korean for a Telugu/Hindi-stuck user, each with a per-language "why" line |
| `frame-c-keep-outcome.png` | Keep outcome: BEFORE 0.86 → AFTER (projected) 0.51 → DROP 0.34 + the honest *"real value gets measured next time detection runs against real Spotify data"* caveat |

To regenerate them at any time:

```powershell
# Start both servers in two terminals (uvicorn :8000 + npm run dev :5173)
# Then in a third:
curl.exe -X POST http://127.0.0.1:8000/jobs/run-detection -H "Content-Type: application/json" -d "{}"
# Walk the flow in DEMO_SCRIPT.md (~90 seconds), screenshot at each step.
```

---

## Enabling the weekly GitHub Action

The workflow file [`.github/workflows/weekly-detection.yml`](.github/workflows/weekly-detection.yml)
is **already committed**. GitHub Actions auto-discovers it the moment
the file lands on the default branch — and on the repo you pushed to
(`mmishra0321/NL_MVP_ResetRadar`) it should already show under the
*Actions* tab.

There are two distinct things to set up:

### 1. Make the schedule runnable (one-time)

By default GitHub Actions on a brand-new public repo are enabled, but
on freshly forked or freshly created repos some accounts default
scheduled workflows to "disabled until first manual run". To force-
enable:

1. Open the repo on GitHub.
2. Click the **Actions** tab.
3. If you see a yellow banner *"Workflows aren't being run on this
   repository"*, click **I understand my workflows, go ahead and
   enable them**.
4. In the left sidebar, click **Reset Radar weekly detection**.
5. Click **Enable workflow** (green button, top-right of the workflow
   page). The Monday 09:00 UTC cron starts ticking from then on.

That's it for the schedule. You can also fire it manually right away:
on the same workflow page, click **Run workflow** (top-right
dropdown), tick *dry_run* if you just want to confirm the wiring, and
click **Run workflow** in the dropdown.

### 2. Tell the action where your backend lives (only matters once you deploy)

Until the backend is on a public URL, the workflow can run but it has
nothing to call. Once you deploy (Render / Railway / Fly), set
**two repo secrets** under *Settings → Secrets and variables →
Actions → New repository secret*:

| Secret name | Value | Notes |
|---|---|---|
| `RESET_RADAR_API_URL` | e.g. `https://reset-radar.onrender.com` | Your deployed backend's public URL. No trailing slash. |
| `RESET_RADAR_API_TOKEN` | (any random string ≥ 32 chars) | Optional. Only required if you set `JOBS_API_TOKEN` to the **same** value on the backend's environment. Leave the secret empty if your backend leaves `JOBS_API_TOKEN` empty (the default, which is fine for a single-tenant demo). |

The workflow already checks `RESET_RADAR_API_URL` is set before it
calls anything — if you leave the secret empty, the workflow logs a
clear *"set RESET_RADAR_API_URL once the MVP is deployed"* message
and skips the curl step instead of failing.

### 3. What runs each Monday

Per [architecture §10](doc/architecture.md):

```
0 9 * * 1   # Mondays 09:00 UTC  →  curl -X POST $RESET_RADAR_API_URL/jobs/run-detection
                                       -H "Content-Type: application/json"
                                       -H "Authorization: Bearer $RESET_RADAR_API_TOKEN"
                                       -d "{}"
```

For each user with an OAuth token, the backend:
1. Fetches this week's listening snapshot from Spotify
2. Appends it to history and recomputes stuck scores
3. Evaluates trigger rules and fires nudges if the streak / threshold
   condition is met

The response JSON is uploaded as a 30-day artefact on the Actions run
and rendered as a Markdown summary in the Actions UI (`users_processed`,
`nudges_fired`, etc.) — so the cron is visibly working even on a
quiet Monday.

### 4. How to verify enable worked (15 seconds)

After step 1 above, on the Actions page click **Run workflow** with
`dry_run: true`. Within ~60 seconds the run should appear, go green,
and the *Summarise the run* step should print `mock_mode: true,
users_processed: 2, nudges_fired: 2` (matching what `curl
/jobs/run-detection` returns locally).

---

## Where the docs live

- **MVP problem statement:** `doc/problemStatement.md`
- **Full MVP architecture:** `doc/architecture.md` (the source of truth)
- **Project-wide problem statement:** `../masterProblemStatement.md`
- **Project-wide architecture:** `../masterArchitecture.md`
- **User research:** `../03-research-and-deck/`
- **Engine (P1):** `../01-ai-review-engine/`
