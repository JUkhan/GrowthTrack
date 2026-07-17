import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'
import BootstrapForm from './BootstrapForm'

function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [bootstrapRequired, setBootstrapRequired] = useState<boolean | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const [deactivationMessage, setDeactivationMessage] = useState<string | null>(null)

  useEffect(() => {
    const message = (location.state as { message?: string } | null)?.message
    if (message) {
      setDeactivationMessage(message)
      // Consume the router-state message once so a later back-navigation
      // to this same history entry doesn't re-show a stale notice.
      navigate(location.pathname, { replace: true, state: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
        setError(body?.error?.message ?? 'Invalid username or password')
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
    <Container maxWidth="xs" sx={{ py: 8 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        GrowthTrack
      </Typography>
      <Box
        component="form"
        onSubmit={handleSubmit}
        noValidate
        sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
      >
        {deactivationMessage && <Alert severity="warning">{deactivationMessage}</Alert>}
        {error && <Alert severity="error">{error}</Alert>}
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
        <Button type="submit" variant="contained" disabled={submitting}>
          Log in
        </Button>
      </Box>
    </Container>
  )
}

export default LoginPage
