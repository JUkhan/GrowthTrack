import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import TextField from '@mui/material/TextField'
import { apiFetch } from '../api/authClient'
import AuthFormShell from '../components/AuthFormShell'

function ForgotPasswordPage() {
  const [username, setUsername] = useState('')
  const [confirmation, setConfirmation] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ username }),
      })

      if (!response.ok) {
        setError('Something went wrong. Please try again.')
        return
      }

      // Always the same confirmation regardless of whether the account
      // exists — no existence oracle, on the frontend either (AC #3).
      const body = await response.json().catch(() => null)
      setConfirmation(
        body?.message ??
          'If an account with that username exists, password reset instructions have been generated.',
      )
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthFormShell heading="Forgot password" onSubmit={handleSubmit}>
      {confirmation && <Alert severity="info">{confirmation}</Alert>}
      {error && <Alert severity="error">{error}</Alert>}
      <TextField
        label="Username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        autoFocus
        required
      />
      <Button type="submit" variant="contained" disabled={submitting}>
        Send reset instructions
      </Button>
      <Link component={RouterLink} to="/">
        Back to login
      </Link>
    </AuthFormShell>
  )
}

export default ForgotPasswordPage
