/**
 * Reset Radar API client - thin fetch wrapper.
 *
 * In dev, calls go to `/api/*` which Vite proxies to the FastAPI
 * backend at http://127.0.0.1:8000 (see vite.config.js).
 */

const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',                                           // R4 session cookie travels with the request
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

  // === Auth (R4 OAuth removed from UI in R10; backend routes still
  //     exist but are not surfaced in the frontend at this time.) ===

  // === Dashboard (users + scores) ===
  listUsers: () => request('/users'),
  getScoreHistory: (userId) =>
    request(`/scores/history?user_id=${encodeURIComponent(userId)}`),

  // === Jobs (manual demo trigger + R8 run history) ===
  runDetection: () =>
    request('/jobs/run-detection', {                                  // canonical name per architecture §6
      method: 'POST',
      body: JSON.stringify({}),
    }),
  getLastJobRun: () => request('/jobs/runs/last'),
  listJobRuns: (limit = 20) => request(`/jobs/runs?limit=${limit}`),
  getJobRun: (runId) => request(`/jobs/runs/${encodeURIComponent(runId)}`),

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
