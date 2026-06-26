/**
 * RunsPage - the GitHub-Action proof-of-life history.
 *
 * Lists the most recent JobRun rows newest-first, each one expandable
 * to show the 4-step trace per processed user:
 *   1. LOAD     - which snapshot was read
 *   2. FORMULAS - stuck_streak_weeks + latest_overall + per-dim hint
 *   3. TRIGGER  - did the rule pass? what's the human-readable reason?
 *   4. NUDGE    - was a nudge actually fired? (id linked to the nudge)
 *
 * This is the slide-7 architectural-property *transparency* in screen
 * form. A reviewer who clicks any run sees exactly what the cron did
 * and why.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { colors } from '../theme.js';


function formatRelative(iso) {
  if (!iso) return 'never';
  const sec = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

function modeTone(mode) {
  if (mode === 'hybrid') return { color: '#fcd34d', border: '#fcd34d' };
  if (mode === 'real')   return { color: '#93c5fd', border: '#60a5fa' };
  return                       { color: '#6ee7b7', border: '#1DB954' };
}


export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});                       // run_id -> full row

  const loadList = () => {
    setLoading(true);
    api.listJobRuns(20)
      .then((resp) => setRuns(resp.runs || []))
      .catch((e) => setError(e.message || String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadList(); }, []);

  const toggleExpand = async (id) => {
    if (expanded[id]) {
      const next = { ...expanded };
      delete next[id];
      setExpanded(next);
      return;
    }
    try {
      const full = await api.getJobRun(id);
      setExpanded((cur) => ({ ...cur, [id]: full }));
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  return (
    <main>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Detection run history</h1>
          <div style={{ color: colors.textSecondary, fontSize: '0.95rem', marginTop: 4 }}>
            Every <code style={inlineCode}>POST /jobs/run-detection</code> call - manual or
            from the Monday 09:00 UTC GitHub Action - lands here with its full step trace.
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button type="button" className="btn-secondary" onClick={loadList} disabled={loading}>
            {loading ? 'Refreshing\u2026' : 'Refresh'}
          </button>
          <Link to="/" style={{ color: colors.spotifyGreen, fontSize: '0.9rem', textDecoration: 'none' }}>
            {'\u2190'} Back to dashboard
          </Link>
        </div>
      </div>

      {error ? (
        <div style={errorStyle}>{error}</div>
      ) : null}

      {!loading && runs.length === 0 ? (
        <div style={emptyStyle}>
          <p>No detection runs recorded yet.</p>
          <p style={{ color: colors.textMuted, fontSize: '0.88rem' }}>
            Click <strong>Run detection now</strong> on the dashboard, or wait for the next
            Monday 09:00 UTC GitHub Action cron.
          </p>
        </div>
      ) : null}

      <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {runs.map((r) => {
          const tone = modeTone(r.mode);
          const isOpen = !!expanded[r.id];
          return (
            <div
              key={r.id}
              style={{
                background: colors.surfaceElevated,
                border: `1px solid ${colors.border}`,
                borderRadius: 10,
                overflow: 'hidden',
              }}
            >
              <button
                type="button"
                onClick={() => toggleExpand(r.id)}
                style={rowHeaderBtn}
                title={isOpen ? 'Collapse this run' : 'Expand the step trace'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span style={{
                    color: colors.textPrimary, fontSize: '0.95rem', fontWeight: 600,
                    minWidth: 110, textAlign: 'left',
                  }}>
                    {formatRelative(r.completed_at)}
                  </span>
                  <span style={{ color: colors.textMuted, fontSize: '0.82rem' }}>
                    {new Date(r.completed_at).toLocaleString()}
                  </span>
                  <span style={{
                    padding: '0.15rem 0.5rem',
                    border: `1px solid ${tone.border}`,
                    color: tone.color,
                    borderRadius: 999,
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}>
                    {r.mode}
                  </span>
                  <span style={smallChip}>{r.trigger_source}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  <Stat label="Users"     value={r.users_processed} />
                  <Stat label="Snapshots" value={r.snapshots_created} />
                  <Stat label="Scores"    value={r.scores_computed} />
                  <Stat label="Nudges"    value={r.nudges_fired}
                        emphasis={r.nudges_fired > 0} />
                  <Stat label="Took"      value={r.duration_ms == null ? '-' : `${r.duration_ms}ms`} />
                  <span style={{ color: colors.textMuted, fontSize: '1.1rem', marginLeft: 4 }}>
                    {isOpen ? '\u25BE' : '\u25B8'}
                  </span>
                </div>
              </button>

              {isOpen && expanded[r.id] ? (
                <ExpandedTrace run={expanded[r.id]} />
              ) : null}
            </div>
          );
        })}
      </div>
    </main>
  );
}


function ExpandedTrace({ run }) {
  const details = run.details || [];
  if (details.length === 0) {
    return (
      <div style={{ padding: '0.75rem 1.1rem', color: colors.textMuted, fontSize: '0.85rem' }}>
        No per-user trace was recorded for this run.
      </div>
    );
  }
  return (
    <div style={{ borderTop: `1px solid ${colors.border}`, background: colors.backgroundCard }}>
      {details.map((d, i) => (
        <UserTraceRow key={`${run.id}-${i}`} detail={d} />
      ))}
    </div>
  );
}


function UserTraceRow({ detail }) {
  const userId = detail.user_id || '(unknown)';
  const trig   = detail.trigger === true;
  const reason = detail.reason || (detail.error ? `error: ${detail.error}` : '-');
  const overall = detail.latest_overall;
  const streak  = detail.stuck_streak_weeks;
  const scope   = detail.latest_suggested_scope;
  const nudge   = detail.nudge_id;
  const fetched = (detail.snapshots != null) || (detail.this_week != null);

  return (
    <div style={{
      padding: '0.7rem 1.1rem',
      borderBottom: `1px solid ${colors.border}`,
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 6 }}>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontWeight: 600,
          color: colors.textPrimary,
        }}>{userId}</span>
        {trig ? (
          <span style={{ ...pill, background: '#1a2a1a', borderColor: colors.spotifyGreen, color: colors.spotifyGreen }}>
            NUDGE FIRED
          </span>
        ) : detail.error ? (
          <span style={{ ...pill, background: '#2a1212', borderColor: '#fca5a5', color: '#fca5a5' }}>
            FETCH ERROR
          </span>
        ) : (
          <span style={{ ...pill, background: '#1a1a1a', borderColor: colors.border, color: colors.textMuted }}>
            no nudge
          </span>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 14, rowGap: 4, fontSize: '0.85rem' }}>
        <Step n={1} label="LOAD">
          {fetched
            ? <>read history {detail.this_week ? `(this week ${detail.this_week})` : `(${detail.snapshots ?? '?'} snapshots)`}</>
            : detail.error
              ? <span style={{ color: '#fca5a5' }}>{detail.error}</span>
              : <>history loaded</>}
        </Step>
        <Step n={2} label="FORMULAS">
          {overall != null
            ? <>overall <code style={inlineCode}>{Number(overall).toFixed(3)}</code> {'\u00b7'} streak <code style={inlineCode}>{streak ?? '-'}</code> wk {'\u00b7'} hint <code style={inlineCode}>{scope ?? '-'}</code></>
            : <span style={{ color: colors.textMuted }}>not computed</span>}
        </Step>
        <Step n={3} label="TRIGGER">
          <span style={{ color: trig ? colors.spotifyGreen : colors.textSecondary }}>
            {trig ? '\u2713 pass' : '\u2717 hold'}
          </span>
          <span style={{ color: colors.textMuted, marginLeft: 8 }}>{reason}</span>
        </Step>
        <Step n={4} label="NUDGE">
          {trig
            ? <span style={{ color: colors.spotifyGreen }}>fired {'\u00b7'} nudge_id <code style={inlineCode}>{nudge?.slice(0, 8) ?? '-'}</code></span>
            : <span style={{ color: colors.textMuted }}>not fired</span>}
        </Step>
      </div>
    </div>
  );
}


function Step({ n, label, children }) {
  return (
    <>
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        fontSize: '0.7rem',
        color: colors.textMuted,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}>
        <span style={{
          width: 18, height: 18, borderRadius: '50%',
          background: '#1a1a1a',
          border: `1px solid ${colors.border}`,
          color: colors.spotifyGreen,
          fontWeight: 700,
          fontSize: '0.7rem',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>{n}</span>
        {label}
      </span>
      <span>{children}</span>
    </>
  );
}


function Stat({ label, value, emphasis }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 56 }}>
      <span style={{
        fontSize: '0.6rem',
        color: colors.textMuted,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>{label}</span>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 600,
        fontSize: '0.9rem',
        color: emphasis ? colors.spotifyGreen : colors.textPrimary,
      }}>{value}</span>
    </div>
  );
}


const rowHeaderBtn = {
  width: '100%',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  padding: '0.7rem 1.1rem',
  background: 'transparent',
  border: 'none',
  color: 'inherit',
  cursor: 'pointer',
  textAlign: 'left',
  flexWrap: 'wrap',
};

const smallChip = {
  padding: '0.1rem 0.45rem',
  background: '#1a1a1a',
  border: `1px solid ${colors.border}`,
  color: colors.textMuted,
  borderRadius: 6,
  fontSize: '0.7rem',
  letterSpacing: '0.04em',
  textTransform: 'lowercase',
};

const pill = {
  padding: '0.12rem 0.55rem',
  border: '1px solid',
  borderRadius: 999,
  fontSize: '0.65rem',
  fontWeight: 700,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
};

const inlineCode = {
  margin: '0 0.15em',
  padding: '0.08em 0.35em',
  background: '#0a0a0a',
  border: `1px solid ${colors.border}`,
  borderRadius: 3,
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: '0.78em',
  color: colors.textPrimary,
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

const emptyStyle = {
  marginTop: '1.25rem',
  padding: '1.5rem',
  background: colors.surfaceElevated,
  border: `1px dashed ${colors.borderStrong}`,
  borderRadius: 12,
  textAlign: 'center',
};
