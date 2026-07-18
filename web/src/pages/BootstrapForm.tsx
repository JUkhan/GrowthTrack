import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import TextField from '@mui/material/TextField'
import { apiFetch } from '../api/authClient'
import AuthFormShell from '../components/AuthFormShell'

interface BootstrapFormProps {
  onAdministratorExists: () => void
}

function BootstrapForm({ onAdministratorExists }: BootstrapFormProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [administratorExists, setAdministratorExists] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setAdministratorExists(false)
    setSubmitting(true)

    try {
      const response = await apiFetch('/auth/bootstrap', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setError(body?.error?.message ?? 'Something went wrong. Please try again.')
        setAdministratorExists(response.status === 409)
        return
      }

      navigate('/home')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthFormShell heading="Create the first Administrator account" onSubmit={handleSubmit}>
      {error && (
        <Alert severity="error">
          {error}
          {administratorExists && (
            <>
              {' '}
              <Link component="button" type="button" onClick={onAdministratorExists}>
                Back to login
              </Link>
            </>
          )}
        </Alert>
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
      <Button type="submit" variant="contained" disabled={submitting}>
        Create account
      </Button>
    </AuthFormShell>
  )
}

export default BootstrapForm
