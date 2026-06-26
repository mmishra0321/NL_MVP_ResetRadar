/**
 * StuckScoreCard - the 4-dimension stuck-score chart over time.
 *
 * Renders an 8-week (or however-many-weeks-the-user-has) line chart with:
 *   - one line per dimension (genre, language, era, mood)
 *   - a bolder "overall" line on top
 *   - a dashed reference line at STUCK_THRESHOLD = 0.6
 *   - a header row showing the current overall score + suggested scope
 *
 * Acceptance criterion (b) is satisfied here: "chart renders all 4
 * dimensions over 8 weeks".
 */
import { useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { colors } from '../theme.js';

const STUCK_THRESHOLD = 0.6;

const DIMENSION_LINES = [
  { key: 'genre',    label: 'Genre',    stroke: '#1DB954', width: 1.5 },
  { key: 'language', label: 'Language', stroke: '#fcd34d', width: 1.5 },
  { key: 'era',      label: 'Era',      stroke: '#a78bfa', width: 1.5 },
  { key: 'mood',     label: 'Mood',     stroke: '#60a5fa', width: 1.5 },
  { key: 'overall',  label: 'Overall',  stroke: '#FFFFFF', width: 3.0 },
];

function shortenWeek(iso) {
  // "2026-W19" -> "W19"
  const m = /W(\d+)$/i.exec(iso || '');
  return m ? `W${m[1]}` : iso;
}

export default function StuckScoreCard({ history = [], threshold = STUCK_THRESHOLD }) {
  const data = useMemo(
    () => history.map((row) => ({ ...row, week: shortenWeek(row.iso_week) })),
    [history],
  );
  const latest = data.length > 0 ? data[data.length - 1] : null;
  const isTriggered = latest ? latest.overall > threshold : false;

  if (!data.length) {
    return (
      <div style={cardStyle}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Stuck-score timeline</div>
        <div style={{ color: colors.textSecondary, fontSize: '0.92rem' }}>
          No snapshots yet. Click <strong>Run detection now</strong> at the top of
          this page to seed the demo with 8 weeks of synthetic listening data.
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <div style={headerRow}>
        <div>
          <div style={{ fontWeight: 600 }}>Stuck-score timeline · last {data.length} weeks</div>
          <div style={{ fontSize: '0.82rem', color: colors.textMuted, marginTop: 2 }}>
            weighted Jaccard overlap + Shannon entropy across four listening axes
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '1.6rem',
              fontWeight: 700,
              color: isTriggered ? colors.warningAmber : colors.successLightGreen,
              lineHeight: 1,
            }}
          >
            {latest.overall.toFixed(2)}
          </div>
          <div style={{ fontSize: '0.78rem', color: colors.textMuted, marginTop: 4 }}>
            {isTriggered ? 'over threshold' : 'within range'} ·
            {' '}suggested scope:{' '}
            <strong style={{ color: colors.textPrimary }}>{latest.suggested_scope}</strong>
          </div>
        </div>
      </div>

      <div style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
            <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
            <XAxis dataKey="week" stroke={colors.textSecondary} fontSize={12} />
            <YAxis
              stroke={colors.textSecondary}
              fontSize={12}
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
            />
            <Tooltip
              contentStyle={{
                background: colors.backgroundCard,
                border: `1px solid ${colors.border}`,
                borderRadius: 8,
                fontSize: '0.85rem',
              }}
              labelStyle={{ color: colors.textSecondary }}
              formatter={(value) => Number(value).toFixed(2)}
            />
            <Legend
              wrapperStyle={{ fontSize: '0.82rem', paddingTop: 6 }}
              iconType="plainline"
            />
            <ReferenceLine
              y={threshold}
              stroke={colors.warningAmber}
              strokeDasharray="4 4"
              label={{
                value: `threshold ${threshold}`,
                position: 'right',
                fill: colors.warningAmber,
                fontSize: 11,
              }}
            />
            {DIMENSION_LINES.map((d) => (
              <Line
                key={d.key}
                type="monotone"
                dataKey={d.key}
                name={d.label}
                stroke={d.stroke}
                strokeWidth={d.width}
                dot={d.key === 'overall' ? { r: 3 } : false}
                activeDot={d.key === 'overall' ? { r: 5 } : { r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
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

const headerRow = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  marginBottom: '0.75rem',
  gap: '1rem',
};
