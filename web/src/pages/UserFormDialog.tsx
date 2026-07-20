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
import { apiFetch } from '../api/authClient'

export interface UserFormValues {
  id: string
  name: string
  mobile: string
  role: 'sales_user' | 'manager'
  teamId: string
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
}

const ROLE_OPTIONS: Array<{ value: 'sales_user' | 'manager'; label: string }> = [
  { value: 'sales_user', label: 'Sales User' },
  { value: 'manager', label: 'Manager' },
]

// One component for create + edit (`user === null` means create). Role is
// never shown in edit mode — immutable after creation (Story 3.1 Dev
// Notes' Role-Handling Matrix), and Administrator is never a selectable
// option here (AC #5) — Administrator accounts are bootstrap-only.
function UserFormDialog({ open, user, teams, onClose, onSaved }: UserFormDialogProps) {
  const [name, setName] = useState('')
  const [mobile, setMobile] = useState('')
  const [role, setRole] = useState<'sales_user' | 'manager'>('sales_user')
  const [teamId, setTeamId] = useState('')
  const [mobileAvailable, setMobileAvailable] = useState(true)
  const [checkingMobile, setCheckingMobile] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(user?.name ?? '')
      setMobile(user?.mobile ?? '')
      setRole(user?.role ?? 'sales_user')
      setTeamId(user?.teamId ?? '')
      setMobileAvailable(true)
      setError(null)
    }
  }, [open, user])

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
                    : undefined
              }
            />
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
  )
}

export default UserFormDialog
