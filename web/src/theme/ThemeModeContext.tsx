import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import useMediaQuery from '@mui/material/useMediaQuery'
import { apiFetch } from '../api/authClient'

type Preference = 'light' | 'dark' | 'system'

const VALID_PREFERENCES: readonly Preference[] = ['light', 'dark', 'system']

function isPreference(value: unknown): value is Preference {
  return typeof value === 'string' && (VALID_PREFERENCES as readonly string[]).includes(value)
}

interface ThemeModeContextValue {
  mode: 'light' | 'dark'
  preference: Preference
  setPreference: (next: Preference) => void
  // Applies a preference already known to be correct — a login/bootstrap
  // response body — without a redundant PATCH round-trip. Silently ignores
  // an unrecognized value.
  syncPreference: (next: unknown) => void
  // An unauthenticated visitor always sees system preference (AC #6) — call
  // on logout so the previous account's override doesn't linger.
  resetPreference: () => void
}

const ThemeModeContext = createContext<ThemeModeContextValue | null>(null)

export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const systemPrefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [preference, setPreferenceState] = useState<Preference>('system')
  // Flips true the moment login/logout/a manual toggle establishes the real
  // preference — guards the one-time mount fetch below from clobbering it
  // with a stale value if that fetch is still in flight or resolves late.
  const knownRef = useRef(false)

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/me')
      .then(async (response) => {
        if (cancelled || knownRef.current || !response.ok) return
        const body = await response.json().catch(() => null)
        if (!cancelled && !knownRef.current && isPreference(body?.theme_preference)) {
          setPreferenceState(body.theme_preference)
        }
      })
      // On failure (unauthenticated — Login/Bootstrap/Forgot/Reset), leave
      // preference at 'system': there is no account yet to have an override.
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [])

  async function setPreference(next: Preference) {
    const previous = preference
    knownRef.current = true
    setPreferenceState(next)
    try {
      const response = await apiFetch('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({ theme_preference: next }),
      })
      if (!response.ok) {
        setPreferenceState(previous)
      }
    } catch {
      // Network failure — the PATCH never persisted, so the optimistic
      // update must not stick either.
      setPreferenceState(previous)
    }
  }

  function syncPreference(next: unknown) {
    if (!isPreference(next)) return
    knownRef.current = true
    setPreferenceState(next)
  }

  function resetPreference() {
    knownRef.current = true
    setPreferenceState('system')
  }

  const mode = preference === 'system' ? (systemPrefersDark ? 'dark' : 'light') : preference

  return (
    <ThemeModeContext.Provider
      value={{ mode, preference, setPreference, syncPreference, resetPreference }}
    >
      {children}
    </ThemeModeContext.Provider>
  )
}

// The context/provider/hook triad is intentionally one file (story spec) —
// this only affects Fast Refresh granularity in dev, not runtime correctness.
// eslint-disable-next-line react-refresh/only-export-components
export function useThemeMode(): ThemeModeContextValue {
  const context = useContext(ThemeModeContext)
  if (context === null) {
    throw new Error('useThemeMode must be used within a ThemeModeProvider')
  }
  return context
}
