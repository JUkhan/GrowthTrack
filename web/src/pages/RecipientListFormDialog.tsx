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
import RecipientPicker from '../components/RecipientPicker'
import type { RecipientOption } from '../components/RecipientPicker'
import { apiFetch } from '../api/authClient'

export interface RecipientListFormValues {
  id: string
  name: string
  kind: 'group' | 'channel'
  memberUserIds: string[]
  version: number
}

interface RecipientListFormDialogProps {
  open: boolean
  recipientList: RecipientListFormValues | null
  kind: 'group' | 'channel'
  options: RecipientOption[]
  onClose: () => void
  onSaved: () => void
}

interface ConflictCurrent {
  name: string
  kind: 'group' | 'channel'
  member_user_ids: string[]
  version: number
}

function titleCase(kind: 'group' | 'channel'): string {
  return kind === 'group' ? 'Group' : 'Channel'
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
  const [version, setVersion] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [conflict, setConflict] = useState<ConflictCurrent | null>(null)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(recipientList?.name ?? '')
      setMemberUserIds(recipientList?.memberUserIds ?? [])
      setVersion(recipientList?.version ?? 1)
      setError(null)
      setConflict(null)
    }
  }, [open, recipientList])

  async function performSave(versionToSend: number) {
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch(
        recipientList ? `/recipient-lists/${recipientList.id}` : '/recipient-lists',
        {
          method: recipientList ? 'PATCH' : 'POST',
          body: JSON.stringify(
            recipientList
              ? { name, kind, member_user_ids: memberUserIds, version: versionToSend }
              : { name, kind, member_user_ids: memberUserIds },
          ),
        },
      )

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
    setMemberUserIds(conflict.member_user_ids)
    setVersion(conflict.version)
    setConflict(null)
  }

  // Equal counts don't mean equal membership — name the actual difference so
  // "Keep My Changes" can't silently discard a same-size membership swap.
  function describeCurrentMembers(currentMemberUserIds: string[]): string {
    const nameById = new Map(options.map((option) => [option.id, option.name]))
    const nameFor = (id: string) => nameById.get(id) ?? id
    const added = currentMemberUserIds.filter((id) => !memberUserIds.includes(id))
    const removed = memberUserIds.filter((id) => !currentMemberUserIds.includes(id))

    const count = `${currentMemberUserIds.length} member${currentMemberUserIds.length === 1 ? '' : 's'}`
    const diffParts = [
      added.length > 0 ? `added: ${added.map(nameFor).join(', ')}` : null,
      removed.length > 0 ? `removed: ${removed.map(nameFor).join(', ')}` : null,
    ].filter((part): part is string => part !== null)

    return diffParts.length > 0 ? `${count} (${diffParts.join('; ')})` : count
  }

  const title = kind === 'group' ? 'Recipient Group' : 'Recipient Channel'

  return (
    <>
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
      <ConflictDialog
        open={conflict !== null}
        entityLabel={title}
        fields={
          conflict
            ? [
                { label: 'Name', mine: name, theirs: conflict.name },
                { label: 'Kind', mine: titleCase(kind), theirs: titleCase(conflict.kind) },
                {
                  label: 'Members',
                  mine: `${memberUserIds.length} member${memberUserIds.length === 1 ? '' : 's'}`,
                  theirs: describeCurrentMembers(conflict.member_user_ids),
                },
              ]
            : []
        }
        submitting={submitting}
        onKeepMine={handleKeepMine}
        onDiscardMine={handleDiscardMine}
      />
    </>
  )
}

export default RecipientListFormDialog
