import ScopePicker from '../components/ScopePicker.jsx';
import ResetPlaylistView from '../components/ResetPlaylistView.jsx';
import KeepOrRevertCard from '../components/KeepOrRevertCard.jsx';

export default function ResetFlow() {
  return (
    <main>
      <div className="placeholder-card">
        <span className="tag">R0 placeholder · real flow in R3</span>
        <h2>Reset session</h2>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
          Pick one scope. A 20-track reset playlist is created in a sandboxed
          trial. After {' '}
          <strong style={{ color: 'var(--success-light-green)' }}>10 days</strong>
          {' '}you decide: Keep or Revert.
        </p>
        <div style={{ marginTop: '1.5rem', display: 'grid', gap: '1.5rem' }}>
          <ScopePicker />
          <ResetPlaylistView />
          <KeepOrRevertCard />
        </div>
      </div>
    </main>
  );
}
