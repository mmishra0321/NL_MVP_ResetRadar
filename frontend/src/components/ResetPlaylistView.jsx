/**
 * ResetPlaylistView - render the 20 ranked tracks with their per-track "why".
 * The "why" string is what makes this AI-native; it ties each pick back to
 * the chosen scope (and to the free-text intent if one was provided).
 */
import { colors } from '../theme.js';


export default function ResetPlaylistView({
  session,
  onSkipToOutcome = null,
}) {
  if (!session) return null;
  const { tracks, scope_dimensions: scopes, free_text_intent: intent, playlist_url } = session;

  return (
    <div
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: '1rem',
        marginBottom: '0.85rem',
      }}>
        <div>
          <div style={{ fontWeight: 600 }}>
            Your reset playlist
            <span style={{ color: colors.textSecondary, fontWeight: 400 }}>
              {' '}· {tracks.length} tracks, sandboxed trial
            </span>
          </div>
          <div style={{
            fontSize: '0.85rem',
            color: colors.textSecondary,
            marginTop: 4,
          }}>
            Scope: <strong style={{ color: colors.spotifyGreen }}>{scopes.join(', ')}</strong>
            {intent ? <> · steering: <em>"{intent}"</em></> : null}
          </div>
        </div>
        {playlist_url ? (
          <a
            href={playlist_url}
            target="_blank"
            rel="noreferrer"
            style={{
              alignSelf: 'flex-start',
              padding: '0.45em 0.95em',
              borderRadius: 999,
              border: `1px solid ${colors.border}`,
              fontSize: '0.85rem',
              whiteSpace: 'nowrap',
            }}
          >
            Open in Spotify <span aria-hidden>&rarr;</span>
          </a>
        ) : null}
      </div>

      <ol
        style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          counterReset: 'tracknum',
        }}
      >
        {tracks.map((t, idx) => (
          <li
            key={t.spotify_track_id || idx}
            style={{
              counterIncrement: 'tracknum',
              padding: '0.85rem 0',
              borderBottom:
                idx < tracks.length - 1 ? `1px solid ${colors.border}` : 'none',
              display: 'grid',
              gridTemplateColumns: '2.25rem 1fr',
              gap: '0.85rem',
              alignItems: 'baseline',
            }}
          >
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              color: colors.textMuted,
              fontSize: '0.85rem',
              textAlign: 'right',
            }}>
              {String(idx + 1).padStart(2, '0')}
            </div>
            <div>
              <div style={{ color: colors.textPrimary, fontWeight: 600 }}>
                {t.title}
                {' '}
                <span style={{ color: colors.textSecondary, fontWeight: 400 }}>
                  · {t.artist}
                </span>
              </div>
              {t.why ? (
                <div style={{
                  fontSize: '0.88rem',
                  color: colors.textSecondary,
                  marginTop: 4,
                  lineHeight: 1.45,
                }}>
                  {t.why}
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {onSkipToOutcome ? (
        <div style={{
          marginTop: '1.25rem',
          padding: '0.85rem 1rem',
          background: colors.backgroundCard,
          border: `1px dashed ${colors.borderStrong}`,
          borderRadius: 8,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
        }}>
          <div style={{ fontSize: '0.85rem', color: colors.textSecondary }}>
            In production this card appears <strong>after the 10-day trial</strong>.
            For the demo, skip ahead to the Keep / Revert outcome.
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={onSkipToOutcome}
            style={{ whiteSpace: 'nowrap' }}
          >
            Skip to outcome
          </button>
        </div>
      ) : null}
    </div>
  );
}
