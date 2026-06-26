/**
 * Reset playlist view - shows the 20 ranked tracks with per-track "why".
 * R0 placeholder rendering a few demo rows so the layout is real.
 * R3 wires this to api.getResetSession().
 */
import { colors } from '../theme.js';

const DEMO_TRACKS = [
  {
    id: 't1',
    title: 'Demo track placeholder',
    artist: 'Artist name',
    why: 'R3 will replace this with the LLM-generated explanation tied to your chosen scope.',
  },
  {
    id: 't2',
    title: 'Another demo track',
    artist: 'Another artist',
    why: 'Each track gets a one-line "why" referencing the reset dimension you picked.',
  },
];

export default function ResetPlaylistView({ tracks = DEMO_TRACKS }) {
  return (
    <div
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '1rem' }}>
        Your reset playlist <span style={{ color: colors.textSecondary, fontWeight: 400 }}>(20 tracks, sandboxed trial)</span>
      </div>
      <ol style={{ listStyle: 'decimal', padding: 0, margin: 0, color: colors.textSecondary }}>
        {tracks.map((t, idx) => (
          <li
            key={t.id}
            style={{
              listStylePosition: 'inside',
              padding: '0.85rem 0',
              borderBottom:
                idx < tracks.length - 1 ? `1px solid ${colors.border}` : 'none',
            }}
          >
            <div style={{ color: colors.textPrimary, fontWeight: 600 }}>
              {t.title} <span style={{ color: colors.textSecondary, fontWeight: 400 }}>· {t.artist}</span>
            </div>
            <div style={{ fontSize: '0.88rem', marginTop: '0.25rem' }}>
              {t.why}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
