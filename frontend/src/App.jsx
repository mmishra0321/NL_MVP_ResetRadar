import { NavLink, Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage.jsx';
import Dashboard from './pages/Dashboard.jsx';
import ResetFlow from './pages/ResetFlow.jsx';
import RunsPage from './pages/RunsPage.jsx';

function Header() {
  return (
    <header className="app-header">
      <div className="app-brand">
        <span className="app-brand-dot">●</span> Reset Radar
      </div>
      <nav className="app-nav">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Home
        </NavLink>
        <NavLink to="/reset" className={({ isActive }) => (isActive ? 'active' : '')}>
          Reset
        </NavLink>
        <NavLink to="/engine" className={({ isActive }) => (isActive ? 'active' : '')}>
          Engine
        </NavLink>
        <NavLink to="/runs" className={({ isActive }) => (isActive ? 'active' : '')}>
          Runs
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
        <Route path="/" element={<HomePage />} />
        <Route path="/engine" element={<Dashboard />} />
        <Route path="/reset" element={<ResetFlow />} />
        <Route path="/reset/:sessionId" element={<ResetFlow />} />
        <Route path="/runs" element={<RunsPage />} />
      </Routes>
    </div>
  );
}
