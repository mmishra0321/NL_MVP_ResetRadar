/**
 * NudgeCard - the system-initiated banner that's the whole point of the MVP.
 *
 * Renders only when there's a pending nudge for the current user.
 * The "Your X mix has narrowed for N weeks" copy is the exact line specified
 * in architecture.md section 9 (Dashboard.jsx -> StuckScoreCard nudge block).
 *
 * Accepting routes to /reset with the suggested scope pre-selected; dismissing
 * marks the nudge dismissed so it stops appearing until the next detection run.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../theme.js';
import { api } from '../api/client.js';

export default function NudgeCard({ nudge, onChange = () => {} }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null);                 // 'accept' | 'dismiss' | null

  if (!nudge) return null;

  const pctRepeat = Math.round(nudge.overall_stuck_score * 100);
  const scope = nudge.suggested_scope;

  const handleAccept = async () => {
    setBusy('accept');
    try {
      await api.respondToNudge(nudge.id, 'accept');
      onChange();
      navigate(
        `/reset?user_id=${encodeURIComponent(nudge.user_id)}` +
        `&scope=${encodeURIComponent(scope)}&nudge_id=${encodeURIComponent(nudge.id)}`,
      );
    } catch (err) {
      console.error('respondToNudge accept failed', err);
      setBusy(null);
    }
  };

  const handleDismiss = async () => {
    setBusy('dismiss');
    try {
      await api.respondToNudge(nudge.id, 'dismiss');
      onChange();
    } catch (err) {
      console.error('respondToNudge dismiss failed', err);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #1a2a1a 0%, #1a1a1a 60%)',
        border: `1px solid ${colors.spotifyGreen}`,
        borderRadius: 12,
        padding: '1.25rem 1.5rem',
        boxShadow: '0 0 0 1px rgba(29,185,84,0.15)',
      }}
    >
      <div style={{
        display: 'inline-block',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '0.72rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: colors.spotifyGreen,
        marginBottom: 8,
      }}>
        Reset Radar nudge · pending
      </div>
      <div style={{ fontSize: '1.15rem', lineHeight: 1.45 }}>
        Your <strong style={{ color: colors.spotifyGreen }}>{scope}</strong> mix
        has repeated <strong>{pctRepeat}%</strong> on the rolling score for{' '}
        <strong>3 weeks</strong>. Try a scoped reset?
      </div>
      <div style={{
        fontSize: '0.85rem',
        color: colors.textSecondary,
        marginTop: 8,
      }}>
        A 20-track playlist, time-boxed for 10 days, only on the {scope} axis.
        Keep or revert at the end. Doesn't touch your saved library unless you Keep.
      </div>
      <div style={{ display: 'flex', gap: '0.65rem', marginTop: '1rem' }}>
        <button
          type="button"
          className="btn-primary"
          onClick={handleAccept}
          disabled={busy !== null}
        >
          {busy === 'accept' ? 'Opening reset...' : `Try a ${scope} reset`}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={handleDismiss}
          disabled={busy !== null}
        >
          {busy === 'dismiss' ? 'Dismissing...' : 'Not now'}
        </button>
      </div>
    </div>
  );
}
