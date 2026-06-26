/**
 * LastRunCard - the "GitHub Action is alive" proof-of-life card.
 *
 * Shows when the last detection run completed + a one-line summary
 * (users processed, snapshots created, nudges fired, mode). Links to
 * `/runs` for the full history + per-user step trace.
 *
 * The same JobRun row is written whether the run was triggered by
 * a human clicking "Run detection now" or by the weekly GH Action
 * cron - they're indistinguishable to this card, which is the point.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { colors } from '../theme.js';


function formatRelative(iso) {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.round((now - then) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

function modeBadgeStyle(mode) {
  if (mode === 'hybrid') return { color: '#fcd34d', border: '#fcd34d', label: 'hybrid' };
  if (mode === 'real')   return { color: '#93c5fd', border: '#60a5fa', label: 'real' };
  return                       { color: '#6ee7b7', border: '#1DB954', label: 'mock' };
}


export default function LastRunCard({ refreshKey }) {
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getLastJobRun()
      .then((r) => { if (!cancelled) setRun(r); })
      .catch(() => { if (!cancelled) setRun(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (loading) {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: colors.textMuted, fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Last detection run
          </span>
          <span style={{ color: colors.textMuted, fontSize: '0.78rem' }}>loading{'\u2026'}</span>
        </div>
      </div>
    );
  }

  if (!run || run.found === false) {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={labelStyle}>Last detection run</div>
            <div style={{ color: colors.textPrimary, marginTop: 4 }}>
              No detection runs yet
            </div>
            <div style={{ color: colors.textMuted, fontSize: '0.82rem', marginTop: 2 }}>
              Click <strong>Run detection now</strong> above, or wait until the next Monday 09:00 UTC cron.
            </div>
          </div>
        </div>
      </div>
    );
  }

  const m = modeBadgeStyle(run.mode);
  const trig = run.trigger_source === 'cron' ? 'GH Action cron' : 'manual';

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={labelStyle}>Last detection run</div>
          <div style={{ marginTop: 6, display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ color: colors.textPrimary, fontSize: '1.05rem', fontWeight: 600 }}>
              {formatRelative(run.completed_at)}
            </span>
            <span style={{ color: colors.textMuted, fontSize: '0.8rem' }}>
              ({new Date(run.completed_at).toLocaleString()} {'\u00b7'} {trig})
            </span>
          </div>
          <div style={{ marginTop: 10, display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Stat label="Users" value={run.users_processed} />
            <Stat label="Snapshots" value={run.snapshots_created} />
            <Stat label="Scores" value={run.scores_computed} />
            <Stat label="Nudges fired" value={run.nudges_fired}
                  valueColor={run.nudges_fired > 0 ? colors.spotifyGreen : colors.textPrimary} />
            <Stat label="Duration" value={run.duration_ms == null ? '-' : `${run.duration_ms}ms`} />
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              padding: '0.18rem 0.55rem',
              border: `1px solid ${m.border}`,
              color: m.color,
              borderRadius: 999,
              fontSize: '0.72rem',
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}>
              {m.label}
            </span>
          </div>
        </div>
        <Link
          to="/runs"
          style={{
            color: colors.spotifyGreen, fontSize: '0.85rem',
            textDecoration: 'none', whiteSpace: 'nowrap',
          }}
          title="View full run history with per-user step traces"
        >
          View run history {'\u2192'}
        </Link>
      </div>
    </div>
  );
}


function Stat({ label, value, valueColor }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 60 }}>
      <span style={{
        fontSize: '0.62rem',
        color: colors.textMuted,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>{label}</span>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '0.98rem',
        fontWeight: 600,
        color: valueColor || colors.textPrimary,
      }}>{value}</span>
    </div>
  );
}


const cardStyle = {
  background: colors.surfaceElevated,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: '0.85rem 1.1rem',
  marginTop: '1rem',
};

const labelStyle = {
  fontSize: '0.72rem',
  color: colors.textMuted,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};
