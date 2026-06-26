/**
 * Stuck-score chart - 8 weeks of overall_stuck_score with the
 * threshold line at STUCK_THRESHOLD=0.6.
 *
 * R0 placeholder - renders a static demo chart so the layout is real
 * even before backend data exists. R3 swaps the data prop with
 * `api.health()` plus a per-user stuck-score endpoint.
 */
import { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { colors } from '../theme.js';

const DEMO_DATA = [
  { week: 'W19', score: 0.41 },
  { week: 'W20', score: 0.45 },
  { week: 'W21', score: 0.48 },
  { week: 'W22', score: 0.52 },
  { week: 'W23', score: 0.58 },
  { week: 'W24', score: 0.63 },
  { week: 'W25', score: 0.65 },
  { week: 'W26', score: 0.68 },
];

export default function StuckScoreCard({ data = DEMO_DATA, threshold = 0.6 }) {
  const lastScore = useMemo(() => data[data.length - 1]?.score ?? 0, [data]);
  const isTriggered = lastScore > threshold;

  return (
    <div
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '1.25rem',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '0.5rem',
        }}
      >
        <div style={{ fontWeight: 600 }}>Overall stuck score</div>
        <div
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            color: isTriggered ? colors.warningAmber : colors.successLightGreen,
          }}
        >
          {lastScore.toFixed(2)} {isTriggered ? '(over threshold)' : '(within range)'}
        </div>
      </div>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
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
              }}
              labelStyle={{ color: colors.textSecondary }}
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
            <Line
              type="monotone"
              dataKey="score"
              stroke={colors.spotifyGreen}
              strokeWidth={2.5}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
