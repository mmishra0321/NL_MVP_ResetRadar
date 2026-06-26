/**
 * KeepOrRevertCard - the trial's terminal action + before/after score readout.
 *
 * Two modes:
 *   - pre-decision: shows the Keep / Revert buttons + the honest
 *     "sandbox is UX-level" copy from architecture.md section 6
 *   - post-decision: shows the before/after stuck-score comparison
 *     plus a confirmation message tied to the decision
 *
 * IMPORTANT: the on-screen copy says "sandbox is UX-level" honestly
 * (per deck slide 9 pitfall 3 + architecture.md section 6). This is
 * non-negotiable.
 */
import { useState } from 'react';
import { colors } from '../theme.js';


export default function KeepOrRevertCard({
  outcome = null,                          // { before_stuck_score, after_stuck_score, decision } | null
  beforeScore = null,                      // shown pre-decision only
  trialDaysRemaining = 10,
  onKeep = () => {},
  onRevert = () => {},
}) {
  const [busy, setBusy] = useState(null);  // 'keep' | 'revert' | null

  const wrapped = async (fn, kind) => {
    setBusy(kind);
    try { await fn(); } finally { setBusy(null); }
  };

  // ----- post-decision: show the outcome -----
  if (outcome && outcome.decision) {
    const before = outcome.before_stuck_score ?? beforeScore ?? null;
    const after = outcome.after_stuck_score ?? null;
    const delta = (before != null && after != null) ? before - after : null;
    const isKeep = outcome.decision === 'keep';

    return (
      <div style={{ ...cardStyle, borderColor: isKeep ? colors.spotifyGreen : colors.warningAmber }}>
        <div style={{
          display: 'inline-block',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '0.72rem',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: isKeep ? colors.spotifyGreen : colors.warningAmber,
          marginBottom: 8,
        }}>
          Outcome · decision recorded
        </div>

        <div style={{ fontSize: '1.05rem' }}>
          {isKeep ? (
            <>You <strong style={{ color: colors.spotifyGreen }}>kept</strong> the reset.
              {' '}The 20 tracks were saved to your library.</>
          ) : (
            <>You <strong style={{ color: colors.warningAmber }}>reverted</strong> the reset.
              {' '}The playlist was removed; nothing else changed.</>
          )}
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '1rem',
          marginTop: '1rem',
          padding: '1rem',
          background: colors.backgroundCard,
          borderRadius: 8,
          border: `1px solid ${colors.border}`,
        }}>
          <ScorePane label="Before" value={before} colour={colors.warningAmber} />
          <ScorePane
            label={isKeep ? 'After (projected)' : 'After'}
            value={after}
            colour={isKeep ? colors.successLightGreen : colors.warningAmber}
          />
          <ScorePane
            label={isKeep ? 'Drop on the scope' : 'No change'}
            value={delta != null ? Math.max(0, delta).toFixed(2) : '—'}
            colour={isKeep ? colors.successLightGreen : colors.textMuted}
            isDelta
          />
        </div>

        {isKeep ? (
          <div style={{ fontSize: '0.8rem', color: colors.textMuted, marginTop: 12 }}>
            The "after" score is a projection assuming even listening across the 20 reset
            tracks; the real value gets measured next time detection runs against real
            Spotify data. Mock mode shows the heuristic.
          </div>
        ) : null}
      </div>
    );
  }

  // ----- pre-decision: show the Keep / Revert buttons -----
  return (
    <div style={cardStyle}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>
        After the trial: Keep or Revert
      </div>
      <p
        style={{
          color: colors.textSecondary,
          fontSize: '0.92rem',
          marginTop: 0,
          lineHeight: 1.5,
        }}
      >
        {trialDaysRemaining} days remaining in the trial window. The reset playlist
        is a separate, explicitly labelled trial — but Spotify still tracks plays
        on its own backend, so the sandbox is a UX guarantee, not backend isolation.
        Keep to save the 20 tracks to your library; Revert to delete the playlist
        and leave everything else untouched.
      </p>
      {beforeScore != null ? (
        <div style={{
          fontSize: '0.85rem',
          color: colors.textSecondary,
          marginTop: '0.6rem',
        }}>
          Stuck score going in: <strong style={{ color: colors.warningAmber }}>{beforeScore.toFixed(2)}</strong>
        </div>
      ) : null}
      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
        <button
          type="button"
          className="btn-primary"
          onClick={() => wrapped(onKeep, 'keep')}
          disabled={busy !== null}
        >
          {busy === 'keep' ? 'Saving...' : 'Keep'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => wrapped(onRevert, 'revert')}
          disabled={busy !== null}
        >
          {busy === 'revert' ? 'Reverting...' : 'Revert'}
        </button>
      </div>
    </div>
  );
}


function ScorePane({ label, value, colour, isDelta = false }) {
  const display = typeof value === 'number' ? value.toFixed(2) : (value ?? '—');
  return (
    <div>
      <div style={{ fontSize: '0.72rem', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '1.5rem',
        fontWeight: 700,
        color: colour,
        marginTop: 2,
      }}>
        {isDelta && typeof value === 'string' && value !== '—' ? '↓ ' : ''}
        {display}
      </div>
    </div>
  );
}


const cardStyle = {
  background: colors.surfaceElevated,
  border: `1px solid ${colors.border}`,
  borderRadius: 12,
  padding: '1.25rem',
};
