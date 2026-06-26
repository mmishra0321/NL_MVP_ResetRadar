/**
 * Spotify-aligned dark palette + spacing tokens.
 *
 * Carried over from legacy-sonar/.streamlit/config.toml and the deck's
 * visual design contract (deck/outline.md). Keep these tokens in one
 * place so the React components, the chart, and the deck stay in sync.
 */

export const colors = {
  // === Spotify palette ===
  spotifyGreen: '#1DB954',
  spotifyGreenHover: '#1ed760',
  spotifyBlack: '#191414',
  spotifyDarkGrey: '#232323',

  // === Deck-aligned semantic tones ===
  backgroundDeep: '#0a0a0a',
  backgroundCard: '#141414',
  surfaceElevated: '#1a1a1a',

  // === Text ===
  textPrimary: '#FFFFFF',
  textSecondary: '#b3b3b3',
  textMuted: '#6b7280',

  // === Alerts (colour-blind safe: amber + light-green, no red/green pair) ===
  warningAmber: '#fcd34d',
  successLightGreen: '#6ee7b7',

  // === Borders ===
  border: '#2a2a2a',
  borderStrong: '#3a3a3a',
};

export const spacing = {
  xs: '0.25rem',
  sm: '0.5rem',
  md: '1rem',
  lg: '1.5rem',
  xl: '2rem',
  xxl: '3rem',
};

export const radius = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  xl: '20px',
  pill: '999px',
};

export const fonts = {
  primary:
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
};

export const breakpoints = {
  mobile: '640px',
  tablet: '768px',
  desktop: '1024px',
  wide: '1440px',
};


export default { colors, spacing, radius, fonts, breakpoints };
