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
| **R1** Detection engine (mock-first) | Implement formulas, ship `synthetic_weeks.json` fixture, unit tests | ⏳ next |
| **R2** Reset engine (mock candidates + Groq) | Build search queries from scope, Groq rank + explain, ship `mock_candidates.json` | ⏳ |
| **R3** Frontend (mock-driven end-to-end) | React UI complete on top of mock backend | ⏳ |
| **R4** Spotify OAuth + read endpoints | Wire real Spotify Web API reads behind `MOCK_MODE=false` | ⏳ |
| **R5** Spotify write endpoints | Real playlist create / follow / save / delete | ⏳ |
| **R6** GitHub Action + polish | Lock weekly cron workflow, polish UI, lock demo script | ⏳ |
| **R7** Deploy + capture deck screenshots | Render (backend) + Vercel (frontend), capture 3 frames | ⏳ |

> **R3 is the demo-presentable stopping point.** Everything from R0
> to R3 runs against synthetic fixtures with **zero Spotify API calls**.
> R4-R7 are upgrades from there, not prerequisites.

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

## Where the docs live

- **MVP problem statement:** `doc/problemStatement.md`
- **Full MVP architecture:** `doc/architecture.md` (the source of truth)
- **Project-wide problem statement:** `../masterProblemStatement.md`
- **Project-wide architecture:** `../masterArchitecture.md`
- **User research:** `../03-research-and-deck/`
- **Engine (P1):** `../01-ai-review-engine/`
