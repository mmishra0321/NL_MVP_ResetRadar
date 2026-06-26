/**
 * Reset Radar API client - thin fetch wrapper.
 *
 * In dev, calls go to `/api/*` which Vite proxies to the FastAPI
 * backend at http://127.0.0.1:8000 (see vite.config.js).
 */

const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    const err = new Error(`API ${res.status}: ${text || res.statusText}`);
    err.status = res.status;
    err.body = text;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}


export const api = {
  // === Meta ===
  health: () => request('/health'),

  // === Dashboard (users + scores) ===
  listUsers: () => request('/users'),
  getScoreHistory: (userId) =>
    request(`/scores/history?user_id=${encodeURIComponent(userId)}`),

  // === Jobs (manual demo trigger) ===
  runDetection: () =>
    request('/jobs/run-weekly-detection', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  // === Nudges (latest + respond) ===
  getLatestNudge: (userId) =>
    request(`/nudges/latest?user_id=${encodeURIComponent(userId)}`),
  respondToNudge: (nudgeId, action) =>
    request(`/nudges/${nudgeId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),

  // === Reset sessions ===
  createResetSession: ({ userId, scopeDimensions, freeTextIntent = null }) =>
    request('/reset/sessions', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        scope_dimensions: scopeDimensions,
        free_text_intent: freeTextIntent,
      }),
    }),
  getResetSession: (sessionId) =>
    request(`/reset/sessions/${encodeURIComponent(sessionId)}`),
  decideResetSession: (sessionId, decision) =>
    request(`/reset/sessions/${encodeURIComponent(sessionId)}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    }),
};


export default api;
