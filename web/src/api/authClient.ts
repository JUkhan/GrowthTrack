// Relative paths only (never an absolute http://localhost:8000 URL) — the
// Vite dev proxy (vite.config.ts) and Nginx's /auth/ location block both
// forward this same-origin, so the httpOnly session cookie stays same-origin
// in every environment.
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
}
