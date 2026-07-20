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
import RecipientPicker from '../components/RecipientPicker'
import type { RecipientOption } from '../components/RecipientPicker'
import { apiFetch } from '../api/authClient'

export interface RecipientListFormValues {
  id: string
  name: string
  kind: 'group' | 'channel'
  memberUserIds: string[]
}

interface RecipientListFormDialogProps {
  open: boolean
  recipientList: RecipientListFormValues | null
  kind: 'group' | 'channel'
  options: RecipientOption[]
  onClose: () => void
  onSaved: () => void
}

// One component for create + edit (`recipientList === null` means create),
// same shape as UserFormDialog/TeamFormDialog. `kind` is fixed by which
// tab opened the dialog (Groups tab -> 'group', Channels tab -> 'channel')
// — not user-editable here, even though the domain layer allows moving a
// list between kinds (it's purely a display label per AD-4).
function RecipientListFormDialog({
  open,
  recipientList,
  kind,
  options,
  onClose,
  onSaved,
}: RecipientListFormDialogProps) {
  const [name, setName] = useState('')
  const [memberUserIds, setMemberUserIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(recipientList?.name ?? '')
      setMemberUserIds(recipientList?.memberUserIds ?? [])
      setError(null)
    }
  }, [open, recipientList])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch(
        recipientList ? `/recipient-lists/${recipientList.id}` : '/recipient-lists',
        {
          method: recipientList ? 'PATCH' : 'POST',
          body: JSON.stringify({ name, kind, member_user_ids: memberUserIds }),
        },
      )

      if (!response.ok) {
        const body = await response.json().catch(() => null)
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

  const title = kind === 'group' ? 'Recipient Group' : 'Recipient Channel'

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={handleSubmit}>
        <DialogTitle>{recipientList ? `Edit ${title}` : `Add ${title}`}</DialogTitle>
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
            <RecipientPicker
              options={options}
              selectedIds={memberUserIds}
              onChange={setMemberUserIds}
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
  )
}

export default RecipientListFormDialog
