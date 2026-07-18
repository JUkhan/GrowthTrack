import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
import { apiFetch } from '../api/authClient'
import AuthFormShell from '../components/AuthFormShell'

function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      const response = await apiFetch('/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: newPassword }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }

      navigate('/', {
        replace: true,
        state: {
          message: 'Password reset. Please log in with your new password.',
          severity: 'success',
        },
      })
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <AuthFormShell heading="Reset password" onSubmit={(event) => event.preventDefault()}>
        <Alert severity="error">
          This reset link is invalid or missing. Please request a new one.
        </Alert>
      </AuthFormShell>
    )
  }

  return (
    <AuthFormShell heading="Reset password" onSubmit={handleSubmit}>
      {error && <Alert severity="error">{error}</Alert>}
      <TextField
        label="New password"
        type="password"
        value={newPassword}
        onChange={(event) => setNewPassword(event.target.value)}
        autoFocus
        required
      />
      <TextField
        label="Confirm new password"
        type="password"
        value={confirmPassword}
        onChange={(event) => setConfirmPassword(event.target.value)}
        required
      />
      <Button type="submit" variant="contained" disabled={submitting}>
        Reset password
      </Button>
    </AuthFormShell>
  )
}

export default ResetPasswordPage
