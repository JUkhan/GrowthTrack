import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'

function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

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
