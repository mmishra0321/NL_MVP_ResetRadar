import { NavLink, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard.jsx';
import ResetFlow from './pages/ResetFlow.jsx';

function Header() {
  return (
    <header className="app-header">
      <div className="app-brand">
        <span className="app-brand-dot">●</span> Reset Radar
      </div>
      <nav className="app-nav">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Dashboard
        </NavLink>
        <NavLink to="/reset" className={({ isActive }) => (isActive ? 'active' : '')}>
          Reset
        </NavLink>
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <Header />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/reset" element={<ResetFlow />} />
        <Route path="/reset/:sessionId" element={<ResetFlow />} />
      </Routes>
    </div>
  );
}
