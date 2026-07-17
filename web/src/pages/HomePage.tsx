import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'

type Status =
  | { kind: 'loading' }
  | { kind: 'authenticated' }
  | { kind: 'unauthenticated'; message?: string }

// Bare authenticated placeholder — Epic 2 (Story 2.2) builds the real
// Dashboard. This exists only to prove the session/route-guard works
// (AC #3), gated behind whether GET /auth/me succeeds. The "Log out"
// button below is a provisional placement (Story 1.4) — EXPERIENCE.md's
// eventual home for it is an avatar-menu/Settings screen that Story 1.6's
// nav shell doesn't exist yet to host.
function HomePage() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/me')
      .then(async (response) => {
        if (cancelled) return
        if (response.ok) {
          setStatus({ kind: 'authenticated' })
          return
        }
        const body = await response.json().catch(() => null)
        setStatus({
          kind: 'unauthenticated',
          message: body?.error?.code === 'account_deactivated' ? body.error.message : undefined,
        })
      })
      .catch(() => {
        if (!cancelled) {
          setStatus({ kind: 'unauthenticated' })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleLogout() {
    setSubmitting(true)
    try {
      const response = await apiFetch('/auth/logout', { method: 'POST' })
      if (response.ok) {
        navigate('/', { replace: true })
      }
    } catch {
      // Network failure — stay put; the button re-enables so the user can retry.
    } finally {
      setSubmitting(false)
    }
  }

  if (status.kind === 'loading') {
    return null
  }

  if (status.kind === 'unauthenticated') {
    return (
      <Navigate to="/" replace state={status.message ? { message: status.message } : undefined} />
    )
  }

  return (
    <Container maxWidth="sm" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Logged in
      </Typography>
      <Button variant="outlined" disabled={submitting} onClick={handleLogout}>
        Log out
      </Button>
    </Container>
  )
}

export default HomePage
