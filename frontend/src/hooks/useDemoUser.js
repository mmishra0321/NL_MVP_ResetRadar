/**
 * useDemoUser - the current "active user" for the demo, persisted to localStorage.
 *
 * Reset Radar is built around two demo personas (Karthik, Aanya) seeded
 * by `POST /jobs/run-weekly-detection`. This hook is the single source of
 * truth for which persona the UI is currently viewing.
 *
 * It also exposes `setUser(id)` so the persona picker on the Dashboard
 * can write the choice back to localStorage; subsequent reloads
 * remember it.
 */
import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'reset_radar.demo_user_id';
const DEFAULT_USER = 'demo-karthik-001';


export function useDemoUser() {
  const [userId, setUserIdState] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_USER;
    } catch {
      return DEFAULT_USER;
    }
  });

  const setUser = useCallback((id) => {
    setUserIdState(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch { /* ignore quota / private-mode errors */ }
  }, []);

  // Listen to storage events so multiple tabs stay in sync.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === STORAGE_KEY && typeof e.newValue === 'string') {
        setUserIdState(e.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return { userId, setUser };
}


export default useDemoUser;
