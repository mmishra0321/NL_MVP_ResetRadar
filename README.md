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
| **R7** Deploy + capture deck screenshots | Render (backend) + Vercel (frontend), capture 3 frames | ⏳ next |

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
│       └── weekly-detection.yml   # Monday 06:00 UTC cron
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

- It does NOT deploy anything. R7 lands Render (backend) + Vercel
  (frontend) and captures the deck screenshots.
- It does NOT implement a real measured `after_stuck_score`. That
  arrives naturally on the next weekly cron run after a Keep decision
  in real mode; the frontend already labels the current value as a
  projection.

---

## Where the docs live

- **MVP problem statement:** `doc/problemStatement.md`
- **Full MVP architecture:** `doc/architecture.md` (the source of truth)
- **Project-wide problem statement:** `../masterProblemStatement.md`
- **Project-wide architecture:** `../masterArchitecture.md`
- **User research:** `../03-research-and-deck/`
- **Engine (P1):** `../01-ai-review-engine/`
