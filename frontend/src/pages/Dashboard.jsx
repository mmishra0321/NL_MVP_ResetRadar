import StuckScoreCard from '../components/StuckScoreCard.jsx';

export default function Dashboard() {
  return (
    <main>
      <div className="placeholder-card">
        <span className="tag">R0 placeholder · real page in R3</span>
        <h2>Your diversity over the last 8 weeks</h2>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
          Reset Radar reads four listening axes - genre, language, era, mood -
          weekly. When stagnation crosses the threshold for three consecutive
          weeks, an active nudge appears here.
        </p>
        <div style={{ marginTop: '1.5rem' }}>
          <StuckScoreCard />
        </div>
      </div>
    </main>
  );
}
