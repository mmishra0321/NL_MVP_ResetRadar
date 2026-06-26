/**
 * ScopePicker - choose exactly one of {genre, language, era, mood} to reset,
 * plus an optional free-text intent. When mounted from a nudge, the suggested
 * scope is pre-selected.
 *
 * Calls `onGenerate({scope, intent})` when the user clicks the primary button.
 */
import { useEffect, useState } from 'react';
import { colors } from '../theme.js';

const SCOPES = [
  { id: 'genre',    label: 'Genre',    hint: 'Step outside your dominant genres' },
  { id: 'language', label: 'Language', hint: 'Discover a less-played language' },
  { id: 'era',      label: 'Era',      hint: 'Time-shift to a different decade' },
  { id: 'mood',     label: 'Mood',     hint: 'Break out of your dominant mood' },
];

export default function ScopePicker({
  suggestedScope = null,
  initialScope = null,
  disabled = false,
  onGenerate = () => {},
}) {
  const [selected, setSelected] = useState(initialScope || suggestedScope || null);
  const [intent, setIntent] = useState('');

  useEffect(() => {
    if (!selected && suggestedScope) setSelected(suggestedScope);
  }, [suggestedScope, selected]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!selected) return;
    onGenerate({ scope: selected, intent: intent.trim() || null });
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
        Step 1 · Choose what to reset
      </div>
      <div style={{ fontSize: '0.85rem', color: colors.textSecondary, marginBottom: '1rem' }}>
        One axis at a time. The other three stay as you have them.
        {suggestedScope ? (
          <>
            {' '}Suggested:{' '}
            <strong style={{ color: colors.spotifyGreen }}>{suggestedScope}</strong>
          </>
        ) : null}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '0.75rem',
        }}
      >
        {SCOPES.map((scope) => {
          const isActive = selected === scope.id;
          const isSuggested = suggestedScope === scope.id;
          return (
            <button
              key={scope.id}
              type="button"
              onClick={() => setSelected(scope.id)}
              disabled={disabled}
              style={{
                background: isActive ? colors.spotifyGreen : colors.backgroundCard,
                color: isActive ? colors.spotifyBlack : colors.textPrimary,
                border: `1px solid ${
                  isActive ? colors.spotifyGreen
                    : isSuggested ? colors.spotifyGreen
                    : colors.border
                }`,
                borderRadius: 8,
                padding: '0.9rem 1rem',
                textAlign: 'left',
                cursor: disabled ? 'not-allowed' : 'pointer',
                transition: 'background 120ms ease, transform 80ms ease',
                position: 'relative',
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>
                {scope.label}
                {isSuggested && !isActive ? (
                  <span style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.65rem',
                    marginLeft: 6,
                    padding: '1px 6px',
                    background: colors.spotifyGreen,
                    color: colors.spotifyBlack,
                    borderRadius: 3,
                    verticalAlign: 'middle',
                  }}>
                    SUGGESTED
                  </span>
                ) : null}
              </div>
              <div
                style={{
                  fontSize: '0.85rem',
                  color: isActive ? colors.spotifyBlack : colors.textSecondary,
                }}
              >
                {scope.hint}
              </div>
            </button>
          );
        })}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <label
          htmlFor="reset-intent"
          style={{ display: 'block', fontWeight: 600, marginBottom: '0.25rem' }}
        >
          Step 2 · Optional steering (free text)
        </label>
        <div style={{ fontSize: '0.82rem', color: colors.textMuted, marginBottom: '0.5rem' }}>
          e.g. "upbeat Spanish, not reggaeton" or "something jazzy or neo-soul to break out of dream-pop"
        </div>
        <input
          id="reset-intent"
          type="text"
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          disabled={disabled}
          maxLength={400}
          placeholder="(optional)"
          style={{
            width: '100%',
            background: colors.backgroundCard,
            border: `1px solid ${colors.border}`,
            borderRadius: 8,
            color: colors.textPrimary,
            padding: '0.75rem 0.9rem',
            fontSize: '0.95rem',
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
      </div>

      <div style={{ marginTop: '1.25rem' }}>
        <button
          type="submit"
          className="btn-primary"
          disabled={disabled || !selected}
        >
          Generate reset playlist
        </button>
      </div>
    </form>
  );
}
