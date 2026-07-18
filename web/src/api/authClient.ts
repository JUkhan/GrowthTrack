// Relative paths only (never an absolute http://localhost:8000 URL) — the
// Vite dev proxy (vite.config.ts) and Nginx's /auth/ location block both
// forward this same-origin, so the httpOnly session cookie stays same-origin
// in every environment.
function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
}

// Two independent mount effects (e.g. ThemeModeProvider and a page's own
// auth check) commonly ask the same GET question on the same initial render
// — collapse concurrent identical GETs into one network round-trip. Each
// caller still gets its own Response to read via clone().
const inFlightGets = new Map<string, Promise<Response>>()

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase()
  if (method !== 'GET') {
    return rawFetch(path, init)
  }

  const existing = inFlightGets.get(path)
  if (existing) {
    return existing.then((response) => response.clone())
  }

  const request = rawFetch(path, init).finally(() => {
    inFlightGets.delete(path)
  })
  inFlightGets.set(path, request)
  return request.then((response) => response.clone())
}
