import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import MarkChatReadIcon from '@mui/icons-material/MarkChatRead'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ConfirmationDialog from '../components/ConfirmationDialog'
import StatusBadge from '../components/StatusBadge'
import { apiFetch } from '../api/authClient'

export interface UserFormValues {
  id: string
  name: string
  mobile: string
  role: 'sales_user' | 'manager'
  teamId: string
  consentStatus: 'opted_in' | 'not_opted_in'
  consentRecordedAt: string | null
}

export interface TeamOption {
  id: string
  name: string
}

interface UserFormDialogProps {
  open: boolean
  user: UserFormValues | null
  teams: TeamOption[]
  onClose: () => void
  onSaved: () => void
  onConsentChanged?: () => void
}

const ROLE_OPTIONS: Array<{ value: 'sales_user' | 'manager'; label: string }> = [
  { value: 'sales_user', label: 'Sales User' },
  { value: 'manager', label: 'Manager' },
]

// One component for create + edit (`user === null` means create). Role is
// never shown in edit mode — immutable after creation (Story 3.1 Dev
// Notes' Role-Handling Matrix), and Administrator is never a selectable
// option here (AC #5) — Administrator accounts are bootstrap-only.
function UserFormDialog({
  open,
  user,
  teams,
  onClose,
  onSaved,
  onConsentChanged,
}: UserFormDialogProps) {
  const [name, setName] = useState('')
  const [mobile, setMobile] = useState('')
  const [role, setRole] = useState<'sales_user' | 'manager'>('sales_user')
  const [teamId, setTeamId] = useState('')
  const [mobileAvailable, setMobileAvailable] = useState(true)
  const [checkingMobile, setCheckingMobile] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Local copy of consent state — what the Consent section renders and what
  // grant/revoke actions update directly from their own response. Not
  // re-derived from the `user` prop after a grant/revoke, since the
  // parent's `editingUser` object isn't refreshed while the dialog stays
  // open (only a fresh Edit click reseeds it).
  const [consentStatus, setConsentStatus] = useState<'opted_in' | 'not_opted_in'>('not_opted_in')
  const [consentRecordedAt, setConsentRecordedAt] = useState<string | null>(null)
  const [consentActionSubmitting, setConsentActionSubmitting] = useState(false)
  const [consentError, setConsentError] = useState<string | null>(null)
  const [revokeConfirmOpen, setRevokeConfirmOpen] = useState(false)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(user?.name ?? '')
      setMobile(user?.mobile ?? '')
      setRole(user?.role ?? 'sales_user')
      setTeamId(user?.teamId ?? '')
      setMobileAvailable(true)
      setError(null)
      setConsentStatus(user?.consentStatus ?? 'not_opted_in')
      setConsentRecordedAt(user?.consentRecordedAt ?? null)
      setConsentError(null)
    }
  }, [open, user])

  async function handleRecordConsent() {
    if (!user || consentActionSubmitting) return
    setConsentError(null)
    setConsentActionSubmitting(true)
    try {
      const response = await apiFetch(`/users/${user.id}/opt-in-consent`, { method: 'POST' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setConsentError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      const body = await response.json()
      setConsentStatus('opted_in')
      setConsentRecordedAt(body.granted_at)
      onConsentChanged?.()
    } catch {
      setConsentError('Something went wrong. Please try again.')
    } finally {
      setConsentActionSubmitting(false)
    }
  }

  async function handleRevokeConsent() {
    if (!user || consentActionSubmitting) return
    setConsentError(null)
    setConsentActionSubmitting(true)
    try {
      const response = await apiFetch(`/users/${user.id}/opt-in-consent`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setConsentError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      setConsentStatus('not_opted_in')
      setConsentRecordedAt(null)
      onConsentChanged?.()
    } catch {
      setConsentError('Something went wrong. Please try again.')
    } finally {
      setConsentActionSubmitting(false)
      setRevokeConfirmOpen(false)
    }
  }

  async function handleMobileBlur() {
    if (!mobile.trim()) return
    setCheckingMobile(true)
    try {
      const params = new URLSearchParams({ mobile })
      if (user) {
        params.set('exclude_user_id', user.id)
      }
      const response = await apiFetch(`/users/mobile-availability?${params.toString()}`)
      if (response.ok) {
        const body = await response.json()
        setMobileAvailable(body.available !== false)
      }
    } catch {
      // Network failure — don't block submit on an inline check that
      // couldn't run; the server-side create/update call is still
      // authoritative and will reject a real conflict with 409.
    } finally {
      setCheckingMobile(false)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch(user ? `/users/${user.id}` : '/users', {
        method: user ? 'PATCH' : 'POST',
        body: JSON.stringify(
          user ? { name, mobile, team_id: teamId } : { name, mobile, role, team_id: teamId },
        ),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        if (body?.error?.code === 'mobile_taken') {
          setMobileAvailable(false)
        }
        setError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }

      onSaved()
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
        <form onSubmit={handleSubmit}>
        <DialogTitle>{user ? 'Edit User' : 'Add User'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              required
            />
            <TextField
              label="Mobile"
              value={mobile}
              onChange={(event) => setMobile(event.target.value)}
              onBlur={handleMobileBlur}
              required
              error={!mobileAvailable}
              helperText={
                !mobileAvailable
                  ? 'This mobile number is already in use'
                  : checkingMobile
                    ? 'Checking availability…'
                    : user && consentStatus === 'opted_in' && mobile !== user.mobile
                      ? `Saving this number will revoke ${name || 'this User'}'s existing WhatsApp consent — they'll need to opt in again before receiving messages.`
                      : undefined
              }
            />
            {user && (
              <Stack spacing={1}>
                <Typography variant="subtitle2">Consent</Typography>
                {consentError && <Alert severity="error">{consentError}</Alert>}
                <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                  {consentStatus === 'opted_in' ? (
                    <StatusBadge status="success" icon={<MarkChatReadIcon />} label="Opted In" />
                  ) : (
                    <StatusBadge status="warning" icon={<WarningAmberIcon />} label="Not Opted In" />
                  )}
                  {consentStatus === 'opted_in' && consentRecordedAt && (
                    <Typography variant="body2" color="text.secondary">
                      {new Date(consentRecordedAt).toLocaleString()}
                    </Typography>
                  )}
                  {consentStatus === 'opted_in' ? (
                    <Button
                      size="small"
                      color="error"
                      disabled={consentActionSubmitting}
                      onClick={() => setRevokeConfirmOpen(true)}
                    >
                      Revoke Consent
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      disabled={consentActionSubmitting}
                      onClick={handleRecordConsent}
                    >
                      Record Consent
                    </Button>
                  )}
                </Stack>
              </Stack>
            )}
            {!user && (
              <TextField
                select
                label="Role"
                value={role}
                onChange={(event) => setRole(event.target.value as 'sales_user' | 'manager')}
                required
              >
                {ROLE_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField
              select
              label="Team"
              value={teamId}
              onChange={(event) => setTeamId(event.target.value)}
              required
            >
              {teams.map((team) => (
                <MenuItem key={team.id} value={team.id}>
                  {team.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={submitting || checkingMobile || !mobileAvailable}
          >
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
    <ConfirmationDialog
      open={revokeConfirmOpen}
      title="Revoke Consent"
      consequence={`This immediately stops all future WhatsApp notifications to ${name || 'this User'}.`}
      confirmLabel="Revoke"
      danger
      submitting={consentActionSubmitting}
      onConfirm={handleRevokeConsent}
      onCancel={() => setRevokeConfirmOpen(false)}
    />
    </>
  )
}

export default UserFormDialog
