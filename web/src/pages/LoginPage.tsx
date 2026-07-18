import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import TextField from '@mui/material/TextField'
import { apiFetch } from '../api/authClient'
import AuthFormShell from '../components/AuthFormShell'
import BootstrapForm from './BootstrapForm'

interface LocationState {
  message?: string
  severity?: 'warning' | 'success'
}

function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [bootstrapRequired, setBootstrapRequired] = useState<boolean | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const [deactivationMessage, setDeactivationMessage] = useState<string | null>(null)
  const [deactivationSeverity, setDeactivationSeverity] = useState<'warning' | 'success'>(
    'warning',
  )
  const [lockoutSeconds, setLockoutSeconds] = useState<number | null>(null)

  useEffect(() => {
    const state = location.state as LocationState | null
    if (state?.message) {
      setDeactivationMessage(state.message)
      setDeactivationSeverity(state.severity ?? 'warning')
      // Consume the router-state message once so a later back-navigation
      // to this same history entry doesn't re-show a stale notice.
      navigate(location.pathname, { replace: true, state: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!lockoutSeconds || lockoutSeconds <= 0) {
      return
    }
    const interval = setInterval(() => {
      setLockoutSeconds((current) => {
        if (current === null || current <= 1) {
          return null
        }
        return current - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [lockoutSeconds])

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/bootstrap-status')
      .then(async (response) => {
        if (cancelled) return
        if (!response.ok) {
          setBootstrapRequired(false)
          return
        }
        const body = await response.json().catch(() => null)
        setBootstrapRequired(body?.bootstrap_required === true)
      })
      .catch(() => {
        if (!cancelled) {
          setBootstrapRequired(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        if (body?.error?.code === 'account_locked') {
          setLockoutSeconds(body.error.details?.retry_after_seconds ?? null)
        } else {
          setError(body?.error?.message ?? 'Invalid username or password')
        }
        return
      }

      navigate('/home')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (bootstrapRequired === null) {
    return null
  }

  if (bootstrapRequired) {
    return <BootstrapForm onAdministratorExists={() => setBootstrapRequired(false)} />
  }

  return (
    <AuthFormShell heading="GrowthTrack" onSubmit={handleSubmit}>
      {deactivationMessage && (
        <Alert severity={deactivationSeverity}>{deactivationMessage}</Alert>
      )}
      {lockoutSeconds !== null ? (
        <Alert severity="warning">
          Too many failed attempts. Try again in {lockoutSeconds}s.
        </Alert>
      ) : (
        error && <Alert severity="error">{error}</Alert>
      )}
      <TextField
        label="Username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        autoFocus
        required
      />
      <TextField
        label="Password"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      <Button
        type="submit"
        variant="contained"
        disabled={submitting || lockoutSeconds !== null}
      >
        Log in
      </Button>
      <Link component={RouterLink} to="/forgot-password">
        Forgot password?
      </Link>
    </AuthFormShell>
  )
}

export default LoginPage
