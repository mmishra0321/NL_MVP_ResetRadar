/**
 * Scope picker - choose one of {genre, language, era, mood} to reset.
 * R0 placeholder. R3 wires it to api.createResetSession().
 */
import { useState } from 'react';
import { colors } from '../theme.js';

const SCOPES = [
  { id: 'genre', label: 'Genre', hint: 'Step outside your dominant genres' },
  { id: 'language', label: 'Language', hint: 'Discover a less-played language' },
  { id: 'era', label: 'Era', hint: 'Time-shift to a different decade' },
  { id: 'mood', label: 'Mood', hint: 'Break out of your dominant mood' },
];

export default function ScopePicker({ onSelect = () => {} }) {
  const [selected, setSelected] = useState(null);
  const handlePick = (id) => {
    setSelected(id);
    onSelect(id);
  };

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
        Choose what to reset
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
          return (
            <button
              key={scope.id}
              type="button"
              onClick={() => handlePick(scope.id)}
              style={{
                background: isActive ? colors.spotifyGreen : colors.backgroundCard,
                color: isActive ? colors.spotifyBlack : colors.textPrimary,
                border: `1px solid ${isActive ? colors.spotifyGreen : colors.border}`,
                borderRadius: 8,
                padding: '0.9rem 1rem',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'background 120ms ease, transform 80ms ease',
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>
                {scope.label}
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
    </div>
  );
}
