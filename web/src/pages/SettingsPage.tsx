import { useCallback, useEffect, useState } from 'react'
import { Navigate, Link as RouterLink } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import Link from '@mui/material/Link'
import Snackbar from '@mui/material/Snackbar'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'

type SessionStatus = { kind: 'loading' } | { kind: 'authenticated' } | { kind: 'unauthenticated' }

interface ReportScheduleResponse {
  send_hour: number
  send_minute: number
  updated_at: string
  updated_by_user_id: string | null
}

function toTimeValue(send_hour: number, send_minute: number): string {
  return `${String(send_hour).padStart(2, '0')}:${String(send_minute).padStart(2, '0')}`
}

// No shared nav shell exists yet (TemplatesPage.tsx's own comment flags this
// as unowned by any story) — this page duplicates the session-check pattern
// rather than inventing one.
function SettingsPage() {
  const [session, setSession] = useState<SessionStatus>({ kind: 'loading' })
  const [timeValue, setTimeValue] = useState('')
  const [loadError, setLoadError] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [savedMessageOpen, setSavedMessageOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/me')
      .then((response) => {
        if (!cancelled) {
          setSession({ kind: response.ok ? 'authenticated' : 'unauthenticated' })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSession({ kind: 'unauthenticated' })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const loadSchedule = useCallback(async () => {
    setLoadError(false)
    try {
      const response = await apiFetch('/settings/report-schedule')
      if (!response.ok) {
        setLoadError(true)
        return
      }
      const body = (await response.json()) as ReportScheduleResponse
      setTimeValue(toTimeValue(body.send_hour, body.send_minute))
    } catch {
      setLoadError(true)
    }
  }, [])

  useEffect(() => {
    if (session.kind !== 'authenticated') return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- same fetch-on-mount shape as TemplatesPage.tsx's existing load effects
    loadSchedule()
  }, [session.kind, loadSchedule])

  if (session.kind === 'loading') {
    return null
  }

  if (session.kind === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  async function handleSave() {
    const [hourText, minuteText] = timeValue.split(':')
    const send_hour = Number(hourText)
    const send_minute = Number(minuteText)
    if (!Number.isInteger(send_hour) || !Number.isInteger(send_minute)) {
      setSubmitError('Please enter a complete send time before saving.')
      return
    }

    setSubmitError(null)
    setSubmitting(true)
    try {
      const response = await apiFetch('/settings/report-schedule', {
        method: 'PATCH',
        body: JSON.stringify({ send_hour, send_minute }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setSubmitError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      const body = (await response.json()) as ReportScheduleResponse
      setTimeValue(toTimeValue(body.send_hour, body.send_minute))
      setSavedMessageOpen(true)
    } catch {
      setSubmitError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
          Settings
        </Typography>
        <Link component={RouterLink} to="/dashboard">
          Back to Dashboard
        </Link>
      </Stack>

      {loadError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Couldn't load the Daily Report schedule. Please try again.
        </Alert>
      )}

      {submitError && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setSubmitError(null)}>
          {submitError}
        </Alert>
      )}

      <Stack spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Typography variant="subtitle2">Daily Report Send Time</Typography>
        <TextField
          type="time"
          label="Send time"
          value={timeValue}
          onChange={(event) => setTimeValue(event.target.value)}
          helperText="Time is in Asia/Dhaka (GMT+6)"
          disabled={timeValue === ''}
        />
        <Button
          variant="contained"
          disabled={timeValue === '' || submitting}
          onClick={handleSave}
          startIcon={submitting ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          Save
        </Button>
      </Stack>

      <Snackbar
        open={savedMessageOpen}
        autoHideDuration={4000}
        onClose={() => setSavedMessageOpen(false)}
        message="Schedule updated"
      />
    </Container>
  )
}

export default SettingsPage
