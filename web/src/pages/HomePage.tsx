import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import Container from '@mui/material/Container'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'

// Bare authenticated placeholder — Epic 2 (Story 2.2) builds the real
// Dashboard. This exists only to prove the session/route-guard works
// (AC #3), gated behind whether GET /auth/me succeeds.
function HomePage() {
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'unauthenticated'>('loading')

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/me')
      .then((response) => {
        if (!cancelled) {
          setStatus(response.ok ? 'authenticated' : 'unauthenticated')
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus('unauthenticated')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  if (status === 'loading') {
    return null
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  return (
    <Container maxWidth="sm" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1">
        Logged in
      </Typography>
    </Container>
  )
}

export default HomePage
