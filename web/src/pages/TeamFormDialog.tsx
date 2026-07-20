import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import ConflictDialog from '../components/ConflictDialog'
import { apiFetch } from '../api/authClient'

export interface TeamFormValues {
  id: string
  name: string
  version: number
}

interface TeamFormDialogProps {
  open: boolean
  team: TeamFormValues | null
  onClose: () => void
  onSaved: () => void
}

interface ConflictCurrent {
  name: string
  version: number
}

// One component for create + edit (`team === null` means create), same
// shape as UserFormDialog.
function TeamFormDialog({ open, team, onClose, onSaved }: TeamFormDialogProps) {
  const [name, setName] = useState('')
  const [version, setVersion] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [conflict, setConflict] = useState<ConflictCurrent | null>(null)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(team?.name ?? '')
      setVersion(team?.version ?? 1)
      setError(null)
      setConflict(null)
    }
  }, [open, team])

  async function performSave(versionToSend: number) {
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch(team ? `/teams/${team.id}` : '/teams', {
        method: team ? 'PATCH' : 'POST',
        body: JSON.stringify(team ? { name, version: versionToSend } : { name }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        if (body?.error?.code === 'version_conflict') {
          setConflict(body.error.details.current as ConflictCurrent)
          return
        }
        setConflict(null)
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await performSave(version)
  }

  function handleKeepMine() {
    if (!conflict) return
    performSave(conflict.version)
  }

  function handleDiscardMine() {
    if (!conflict) return
    setName(conflict.name)
    setVersion(conflict.version)
    setConflict(null)
  }

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
        <form onSubmit={handleSubmit}>
          <DialogTitle>{team ? 'Edit Sales Team' : 'Add Sales Team'}</DialogTitle>
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
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              Save
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <ConflictDialog
        open={conflict !== null}
        entityLabel="Sales Team"
        fields={conflict ? [{ label: 'Name', mine: name, theirs: conflict.name }] : []}
        submitting={submitting}
        onKeepMine={handleKeepMine}
        onDiscardMine={handleDiscardMine}
      />
    </>
  )
}

export default TeamFormDialog
