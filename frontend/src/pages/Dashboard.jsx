/**
 * Dashboard - the home page of Reset Radar.
 *
 * Composition:
 *   - top row: persona picker + "Run detection now" button
 *   - active nudge (if any) - clicking Try opens /reset
 *   - 4-dimension stuck-score chart
 *   - empty state when no snapshots exist
 *
 * Wires:
 *   - GET /users
 *   - GET /scores/history?user_id=...
 *   - GET /nudges/latest?user_id=...
 *   - POST /jobs/run-weekly-detection
 *
 * State is local to the page; the only persisted bit is the active
 * user id (see useDemoUser).
 */
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { colors } from '../theme.js';
import StuckScoreCard from '../components/StuckScoreCard.jsx';
import NudgeCard from '../components/NudgeCard.jsx';
import useDemoUser from '../hooks/useDemoUser.js';


export default function Dashboard() {
  const { userId, setUser } = useDemoUser();
  const [users, setUsers] = useState([]);
  const [history, setHistory] = useState([]);
  const [nudge, setNudge] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

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

  // Initial user list - one-shot
  useEffect(() => {
    api.listUsers()
      .then((u) => setUsers(Array.isArray(u) ? u : []))
      .catch(() => setUsers([]));
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
          <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Dashboard</h1>
          <div style={{ color: colors.textSecondary, fontSize: '0.95rem', marginTop: 4 }}>
            Reset Radar reads four listening axes weekly. Below is the rolling
            stuck score for the selected user.
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
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
            {running ? 'Running...' : 'Run detection now'}
          </button>
        </div>
      </div>

      {error ? (
        <div style={errorStyle}>{error}</div>
      ) : null}

      {nudge && nudge.status === 'pending' ? (
        <div style={{ margin: '1.5rem 0' }}>
          <NudgeCard nudge={nudge} onChange={() => refresh(userId)} />
        </div>
      ) : null}

      <div style={{ marginTop: '1.5rem' }}>
        {noSnapshots ? (
          <EmptyState onRun={handleRunDetection} running={running} />
        ) : (
          <StuckScoreCard history={history} />
        )}
      </div>

      {latest ? (
        <PerDimensionGrid latest={latest} />
      ) : null}

      <FooterNote />
    </main>
  );
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


function EmptyState({ onRun, running }) {
  return (
    <div style={{
      background: colors.surfaceElevated,
      border: `1px dashed ${colors.borderStrong}`,
      borderRadius: 12,
      padding: '2rem',
      textAlign: 'center',
    }}>
      <h2 style={{ margin: 0 }}>No snapshots yet</h2>
      <p style={{ color: colors.textSecondary, marginTop: 8 }}>
        Click <strong>Run detection now</strong> to seed the demo with two synthetic
        personas across 8 weeks. Both personas will produce nudges that flow
        into the reset experience.
      </p>
      <button
        type="button"
        className="btn-primary"
        onClick={onRun}
        disabled={running}
        style={{ marginTop: 12 }}
      >
        {running ? 'Running...' : 'Run detection now'}
      </button>
    </div>
  );
}


function FooterNote() {
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
      <strong style={{ color: colors.textSecondary }}>Mock mode is on.</strong>{' '}
      No live Spotify calls. The 8-week timeline is generated from
      <code style={{
        margin: '0 0.3em',
        padding: '0.1em 0.4em',
        background: colors.surfaceElevated,
        borderRadius: 3,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '0.78rem',
      }}>backend/mock_data/synthetic_weeks.json</code>.
      The "sandbox" guarantee is UX-level: Spotify still records plays in
      a real reset, so the reset playlist's plays still feed Spotify's
      own model. Documented honestly across README, architecture.md, and
      deck slide 9.
    </div>
  );
}


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
