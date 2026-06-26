/**
 * Dashboard - the home page of Reset Radar.
 *
 * Composition:
 *   - top row: persona picker + "Run detection now" button + optional
 *              "Login with Spotify" CTA (real mode only)
 *   - mode badge: clearly states whether the page is running on
 *                 synthetic data or live Spotify reads (R6 honesty)
 *   - active nudge (if any) - clicking Try opens /reset
 *   - 4-dimension stuck-score chart (skeleton placeholder while loading)
 *   - per-dimension grid (skeleton while loading)
 *   - empty state when no snapshots exist
 *
 * Wires:
 *   - GET /health        (mock_mode flag + LLM models)
 *   - GET /auth/me       (R4 session cookie)
 *   - GET /users
 *   - GET /scores/history?user_id=...
 *   - GET /nudges/latest?user_id=...
 *   - POST /jobs/run-detection
 *
 * State is local to the page; the only persisted bit is the active
 * user id (see useDemoUser).
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { colors } from '../theme.js';
import StuckScoreCard from '../components/StuckScoreCard.jsx';
import NudgeCard from '../components/NudgeCard.jsx';
import LastRunCard from '../components/LastRunCard.jsx';
import useDemoUser from '../hooks/useDemoUser.js';


export default function Dashboard() {
  const { userId, setUser } = useDemoUser();
  const [users, setUsers] = useState([]);
  const [history, setHistory] = useState([]);
  const [nudge, setNudge] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const [runKey, setRunKey] = useState(0);                            // bumps LastRunCard refresh

  // R10: mock-mode-only now; OAuth UI was removed per user direction.
  // Backend MOCK_MODE flag is still surfaced for the badge, but no
  // login / Connect-Spotify path is exposed in the UI.
  const [meta, setMeta] = useState({ mockMode: true });

  const refresh = useCallback(async (uid) => {
    if (!uid) return;
    setLoading(true);
    setError(null);
    try {
      const [historyResp, nudgeResp] = await Promise.all([
        api.getScoreHistory(uid).catch((e) => {
          if (e.status === 404) return { weeks: [] };
          throw e;
        }),
        api.getLatestNudge(uid).catch(() => null),
      ]);
      setHistory(historyResp.weeks || []);
      setNudge(nudgeResp);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial bootstrap - users + backend health.
  useEffect(() => {
    Promise.all([
      api.listUsers().catch(() => []),
      api.health().catch(() => null),
    ]).then(([users, health]) => {
      setUsers(Array.isArray(users) ? users : []);
      if (health && typeof health === 'object') {
        setMeta({
          mockMode: !!health.mock_mode,
          reasonerModel: health.reasoner_model,
          fastModel: health.fast_model,
        });
      }
    });
  }, []);

  // Refresh on userId change
  useEffect(() => { refresh(userId); }, [userId, refresh]);

  const handleRunDetection = async () => {
    setRunning(true);
    setError(null);
    try {
      await api.runDetection();
      const updated = await api.listUsers().catch(() => []);
      setUsers(Array.isArray(updated) ? updated : []);
      await refresh(userId);
      setRunKey((k) => k + 1);                                        // refresh LastRunCard
    } catch (e) {
      setError(`Run detection failed: ${e.message || e}`);
    } finally {
      setRunning(false);
    }
  };

  const latest = history.length ? history[history.length - 1] : null;
  const noSnapshots = !loading && history.length === 0;

  return (
    <main>
      <div style={topRow}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Engine diagnostics</h1>
          <div style={{ color: colors.textSecondary, fontSize: '0.95rem', marginTop: 4 }}>
            Behind-the-scenes view: stuck-score timeline, per-dimension grid,
            and the proactive-cron history. <Link to="/" style={{ color: colors.spotifyGreen }}>
            {'\u2190'} Back to home</Link>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <ModeBadge mock={meta.mockMode} />
          <label
            htmlFor="user-picker"
            style={{ fontSize: '0.82rem', color: colors.textMuted }}
          >
            Demo user
          </label>
          <select
            id="user-picker"
            value={userId}
            onChange={(e) => setUser(e.target.value)}
            style={selectStyle}
          >
            {users.length === 0 ? (
              <option value={userId}>{userId} (not yet seeded)</option>
            ) : null}
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name || u.id}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-primary"
            onClick={handleRunDetection}
            disabled={running}
            title="Wipes prior mock-mode state for the demo personas and recomputes 8 weeks of stuck scores."
          >
            {running ? 'Running\u2026' : 'Run detection now'}
          </button>
        </div>
      </div>

      {error ? (
        <div style={errorStyle}>{error}</div>
      ) : null}

      <LastRunCard refreshKey={runKey} />

      {nudge && nudge.status === 'pending' ? (
        <div style={{ margin: '1.5rem 0' }}>
          <NudgeCard nudge={nudge} onChange={() => refresh(userId)} />
        </div>
      ) : null}

      <div style={{ marginTop: '1.5rem' }}>
        {loading ? (
          <ChartSkeleton />
        ) : noSnapshots ? (
          <EmptyState onRun={handleRunDetection} running={running} mockMode={meta.mockMode} />
        ) : (
          <StuckScoreCard history={history} />
        )}
      </div>

      {loading ? (
        <DimensionGridSkeleton />
      ) : latest ? (
        <PerDimensionGrid latest={latest} />
      ) : null}

      <FooterNote mockMode={meta.mockMode} reasonerModel={meta.reasonerModel} />
    </main>
  );
}


// ============================================================
// Small UI primitives (mode badge, auth control, skeletons)
// ============================================================

function ModeBadge({ mock }) {
  const tone = mock
    ? { bg: '#1a2a1a', border: colors.spotifyGreen, fg: colors.successLightGreen, label: 'Mock mode' }
    : { bg: '#1a1f2a', border: '#60a5fa',            fg: '#93c5fd',               label: 'Live Spotify' };
  return (
    <span
      title={mock
        ? 'No live Spotify calls. Data flows from backend/mock_data/.'
        : 'Talking to the real Spotify Web API.'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        background: tone.bg,
        border: `1px solid ${tone.border}`,
        color: tone.fg,
        borderRadius: 999,
        padding: '0.25rem 0.65rem',
        fontSize: '0.78rem',
        fontWeight: 600,
        letterSpacing: '0.04em',
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%',
        background: tone.fg, boxShadow: `0 0 8px ${tone.fg}`,
      }} />
      {tone.label}
    </span>
  );
}

// R10: AuthControl + ModeSwitcherCard removed entirely. The /engine
// page no longer surfaces any "Connect Spotify" / "Login" CTA; the
// demo is mock-only by design. The backend's /auth/* routes still
// exist for future real-mode work but the frontend no longer calls
// them. See HomePage.jsx for the primary user-facing entry point.

function ChartSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading stuck-score chart"
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
        height: 360,
      }}
    >
      <div style={skelLine(180, 14)} />
      <div style={{ ...skelLine(260, 10), marginTop: 6 }} />
      <div style={{
        marginTop: 18,
        height: 240,
        background: `repeating-linear-gradient(
          135deg,
          ${colors.backgroundCard},
          ${colors.backgroundCard} 10px,
          ${colors.surfaceElevated} 10px,
          ${colors.surfaceElevated} 20px
        )`,
        borderRadius: 8,
        opacity: 0.55,
      }} />
    </div>
  );
}

function DimensionGridSkeleton() {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: '0.85rem',
      marginTop: '1rem',
    }}>
      {[0,1,2,3].map((i) => (
        <div
          key={i}
          style={{
            background: colors.surfaceElevated,
            border: `1px solid ${colors.border}`,
            borderRadius: 10,
            padding: '0.9rem',
            height: 88,
          }}
        >
          <div style={skelLine(60, 8)} />
          <div style={{ ...skelLine(80, 18), marginTop: 10 }} />
          <div style={{ ...skelLine(50, 8),  marginTop: 6  }} />
        </div>
      ))}
    </div>
  );
}

function skelLine(width, height) {
  return {
    width, height,
    background: colors.backgroundCard,
    borderRadius: 4,
    opacity: 0.7,
  };
}


function PerDimensionGrid({ latest }) {
  const dims = ['genre', 'language', 'era', 'mood'];
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: '0.85rem',
      marginTop: '1rem',
    }}>
      {dims.map((d) => {
        const v = latest[d] ?? 0;
        const overThreshold = v > 0.6;
        return (
          <div
            key={d}
            style={{
              background: colors.surfaceElevated,
              border: `1px solid ${overThreshold ? colors.warningAmber : colors.border}`,
              borderRadius: 10,
              padding: '0.9rem',
            }}
          >
            <div style={{
              fontSize: '0.72rem',
              color: colors.textMuted,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}>{d}</div>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '1.4rem',
              fontWeight: 700,
              color: overThreshold ? colors.warningAmber : colors.textPrimary,
              marginTop: 4,
            }}>
              {Number(v).toFixed(2)}
            </div>
            <div style={{ fontSize: '0.78rem', color: colors.textMuted, marginTop: 2 }}>
              {latest.suggested_scope === d ? 'suggested scope' : (overThreshold ? 'over threshold' : '\u00A0')}
            </div>
          </div>
        );
      })}
    </div>
  );
}


function EmptyState({ onRun, running, mockMode }) {
  return (
    <div style={{
      background: colors.surfaceElevated,
      border: `1px dashed ${colors.borderStrong}`,
      borderRadius: 12,
      padding: '2rem',
      textAlign: 'center',
    }}>
      <h2 style={{ margin: 0 }}>You have no snapshots yet</h2>
      <p style={{ color: colors.textSecondary, marginTop: 8 }}>
        {mockMode ? (
          <>
            Click <strong>Run detection now</strong> to seed the demo with two
            synthetic personas across 8 weeks. Both personas produce nudges that
            flow into the reset experience.
          </>
        ) : (
          <>
            Click <strong>Run detection now</strong> to append this
            week&rsquo;s Spotify snapshot. Reset Radar needs about 8 weeks of
            history before it can fire a nudge - the first run just establishes
            the baseline.
          </>
        )}
      </p>
      <button
        type="button"
        className="btn-primary"
        onClick={onRun}
        disabled={running}
        style={{ marginTop: 12 }}
      >
        {running ? 'Running\u2026' : 'Run detection now'}
      </button>
    </div>
  );
}


function FooterNote({ mockMode, reasonerModel }) {
  return (
    <div style={{
      marginTop: '2rem',
      padding: '1rem 1.25rem',
      background: colors.backgroundCard,
      border: `1px solid ${colors.border}`,
      borderRadius: 10,
      fontSize: '0.82rem',
      color: colors.textMuted,
      lineHeight: 1.55,
    }}>
      {mockMode ? (
        <>
          <strong style={{ color: colors.textSecondary }}>Mock mode is on.</strong>{' '}
          No live Spotify calls. The 8-week timeline is generated from
          <code style={inlineCode}>backend/mock_data/synthetic_weeks.json</code>.
          The &ldquo;sandbox&rdquo; guarantee is UX-level: Spotify still records plays in
          a real reset, so the reset playlist&rsquo;s plays still feed Spotify&rsquo;s
          own model. Documented honestly across README, architecture.md, and
          deck slide 9.
        </>
      ) : (
        <>
          <strong style={{ color: '#93c5fd' }}>Live Spotify mode.</strong>{' '}
          Detection reads <code style={inlineCode}>/me/top/tracks</code> +
          <code style={inlineCode}>/me/player/recently-played</code> +
          <code style={inlineCode}>/me/tracks</code>, classifies language &amp;
          mood via {reasonerModel || 'Groq'}, and appends one snapshot per run.
          A weekly GitHub Action runs the same job every Monday at 09:00 UTC.
        </>
      )}
    </div>
  );
}


const inlineCode = {
  margin: '0 0.3em',
  padding: '0.1em 0.4em',
  background: colors.surfaceElevated,
  borderRadius: 3,
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: '0.78rem',
};


const topRow = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-end',
  gap: '1rem',
  flexWrap: 'wrap',
};

const selectStyle = {
  background: colors.backgroundCard,
  color: colors.textPrimary,
  border: `1px solid ${colors.border}`,
  borderRadius: 8,
  padding: '0.5rem 0.75rem',
  fontSize: '0.92rem',
  fontFamily: 'inherit',
  cursor: 'pointer',
};

const errorStyle = {
  marginTop: '1rem',
  padding: '0.75rem 1rem',
  background: '#2a1212',
  border: '1px solid #5a2020',
  borderRadius: 8,
  color: '#fecaca',
  fontSize: '0.9rem',
};
