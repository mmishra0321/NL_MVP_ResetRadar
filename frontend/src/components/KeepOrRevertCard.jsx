/**
 * Keep / Revert decision card - the trial's terminal action.
 * R0 placeholder. R3 wires the buttons to api.decideResetSession().
 *
 * IMPORTANT: the on-screen copy must say "sandbox is UX-level" honestly
 * (per deck slide 9 pitfall 3 + architecture.md section 6). The
 * placeholder copy below is final - R3 only wires the buttons.
 */
import { colors } from '../theme.js';

export default function KeepOrRevertCard({
  trialDaysRemaining = 10,
  onKeep = () => {},
  onRevert = () => {},
}) {
  return (
    <div
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>
        After the trial: Keep or Revert
      </div>
      <p
        style={{
          color: colors.textSecondary,
          fontSize: '0.92rem',
          marginTop: 0,
        }}
      >
        {trialDaysRemaining} days remaining. The reset playlist is a separate,
        explicitly-labelled trial - Spotify still tracks plays internally, so
        the sandbox is a UX guarantee, not a backend isolation. Keep to add the
        tracks to your library; Revert to delete the playlist and the library
        adds.
      </p>
      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
        <button type="button" className="btn-primary" onClick={onKeep}>
          Keep
        </button>
        <button type="button" className="btn-secondary" onClick={onRevert}>
          Revert
        </button>
      </div>
    </div>
  );
}
