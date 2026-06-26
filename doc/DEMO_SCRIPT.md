# Reset Radar — Live Demo Script

> **Target runtime: ≤ 90 seconds, cold open → Keep outcome.**
> **Mode**: `MOCK_MODE=true` (the live demo never touches Spotify).
> **Pre-flight**: backend on `:8000` and frontend on `:5173` already running.

If any of the pre-flight steps below are not done, the demo will derail
in the first 10 seconds. **Do them once, the day before**, and confirm
with the smoke-check at the bottom.

---

## Pre-flight checklist (do once, day-before)

1. **Backend** is running:
   ```powershell
   cd 02-mvp\backend
   ..\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --port 8000
   ```
2. **Frontend** is running:
   ```powershell
   cd 02-mvp\frontend
   npm run dev
   ```
3. Open **http://localhost:5173/** in Chrome (incognito is fine).
4. `02-mvp\backend\.env` has `MOCK_MODE=true` and a valid `GROQ_API_KEY`.
5. Click **"Run detection now"** once → expect 2 personas seeded, 2 nudges fired. **Reload the page.** Both personas should show
   the "language reset" (Karthik) or "genre reset" (Aanya) nudge card.

If step 5 fails, see *Troubleshooting* below before going on stage.

---

## The 5-step script (live, ≤ 90 s)

| Step | Time | What presenter does | What presenter says |
|---|---|---|---|
| **1. Open Dashboard** | 0:00 → 0:10 | Land on `/` with **Karthik** selected (default). Point at the chart and the amber threshold line. | *"This is a Spotify Premium user we've been watching for 8 weeks. Each line is one of four diversity axes — genre, language, era, mood. The dashed line at 0.6 is when Reset Radar declares them stuck."* |
| **2. Read the nudge** | 0:10 → 0:25 | Point at the green-outlined nudge banner at the top. Read the body text aloud. | *"This isn't a settings page — Reset Radar fires this nudge by itself once the language stuck score crosses threshold for 3 consecutive weeks. The text names the exact dimension and the exact percent, because vague nudges feel like spam."* |
| **3. Accept → Scope picker** | 0:25 → 0:35 | Click **"Try a language reset"** on the nudge. Land on `/reset?scope=language`. Type *"expand beyond Telugu without losing the melodic feel"* into the intent field. Click **"Generate reset playlist"**. | *"One scope at a time, by design — resetting all four axes at once is just shuffle. The free-text box is optional intent that the LLM uses to refine ranking."* |
| **4. Show the playlist** | 0:35 → 1:05 | Wait ~5–15 s for Groq. Scroll through the first 3-4 tracks; let the **per-track "why"** be visible. Hover one explanation. | *"20 tracks, filtered by the chosen scope, ranked by Groq with a one-line honest reason for each. The LLM was told this is a bridge from the user's current pattern — not a marketing pitch."* |
| **5. Skip → Keep outcome** | 1:05 → 1:25 | Click **"Skip to outcome"** at the bottom. Click **"Keep"**. Land on the before/after card. | *"In a real reset this would have been 10 days of listening. The before/after numbers are mock-projected here (heuristic 0.6×) — in real Spotify mode, next Monday's cron measures the actual delta. That gap is documented honestly on the screen."* |

**End state at 1:25**: Outcome card visible with `before 0.86 → after 0.51`,
the "approximation" caveat, and the *Back to dashboard* button.
~5 s of buffer before 90 s.

---

## Variations (pick one if asked)

### "Show me the revert path"  (≈ 30 s detour)

From step 5, instead of *Keep*, click *Revert*. The card shows
`before 0.86 → after 0.86`, no listening change, playlist removed.
This is the path for users who feel the trial didn't help.

### "Switch personas"  (≈ 20 s)

In the top-right dropdown switch from **Karthik (multilingual)** to
**Aanya (English indie)**. Same chart, same nudge structure — but the
suggested scope is *genre*, not *language*. The detection rule is
dimension-agnostic; the suggested scope is just whichever axis is
hottest this week.

### "What happens in real Spotify mode?"  (≈ 30 s)

Open `02-mvp/README.md` → *"Real-mode setup (R4 / R5)"*. Walk through
the 4 steps: developer-app creation, allow-list, `.env` flip,
`/auth/login`. Don't actually log in on stage — first real run only
creates **one** weekly snapshot, so the trigger stays quiet by design.

---

## Troubleshooting (if something dies on stage)

| Symptom | Likely cause | Fix in ≤ 15 s |
|---|---|---|
| "Connection failed" on every API call | Backend not running | `uvicorn app.main:app --port 8000` in `02-mvp/backend` |
| No personas in the dropdown | Detection never ran | Click **Run detection now** once |
| Nudge doesn't appear | Last R2/R3 test left an active reset session blocking new nudges | Click **Run detection now** — it wipes prior demo state in mock mode |
| Playlist generation 502s | Groq quota / rate-limit / key missing | Check `backend/.env` has `GROQ_API_KEY`; wait 15 s and retry |
| Chart shows just one persona's data | Persona dropdown was changed mid-flow | Switch back; data is cached in `localStorage.reset_radar.demo_user_id` |
| Stale outcome card after multiple runs | Session already decided | Click **Start a new reset** at the bottom of the outcome screen |

---

## Smoke-check (run the morning of the demo)

```powershell
# Both servers running already? If not, see Pre-flight.
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:5173/api/health        # tests the Vite proxy too
curl -X POST http://127.0.0.1:8000/jobs/run-detection -H "Content-Type: application/json" -d "{}"
```

All three should return `200`. The third should report
`mock_mode: true`, `users_processed: 2`, `nudges_fired: 2`.

---

## What this script intentionally does NOT show

- The 8-week cron history accumulating in real time (R4-R7 fidelity
  upgrade; mock mode collapses 8 weeks into one click).
- The GitHub Action firing on schedule (lives in
  `.github/workflows/weekly-detection.yml`; mention in passing if asked).
- Reviewing the underlying SQLite tables (they exist — the architecture
  doc has the full schema — but live DB inspection isn't the demo).
- Audio playback (deliberately punted: ranking + framing is the
  product, not the music itself).

Everything in this list has a one-line explanation ready in the deck;
none of it warrants stage time.
