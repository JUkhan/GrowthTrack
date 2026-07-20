import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ConfirmationDialog from '../components/ConfirmationDialog'
import EmptyState from '../components/EmptyState'
import ResponsiveDataTable from '../components/ResponsiveDataTable'
import type { DataTableColumn } from '../components/ResponsiveDataTable'
import StatusBadge from '../components/StatusBadge'
import { apiFetch } from '../api/authClient'
import type { DirectoryUser } from './RecipientsPage'
import RecipientListFormDialog from './RecipientListFormDialog'
import type { RecipientListFormValues } from './RecipientListFormDialog'

export interface RecipientListRow {
  id: string
  name: string
  kind: 'group' | 'channel'
  status: 'active' | 'inactive'
  version: number
  member_user_ids: string[]
}

interface RecipientListsPanelProps {
  kind: 'group' | 'channel'
  title: string
  emptyMessage: string
  addButtonLabel: string
  recipientLists: RecipientListRow[] | null
  error: boolean
  users: DirectoryUser[]
  onReload: () => void
}

function statusBadge(status: 'active' | 'inactive') {
  return status === 'active' ? (
    <StatusBadge status="success" icon={<CheckCircleIcon />} label="Active" />
  ) : (
    <StatusBadge status="neutral" icon={<BlockIcon />} label="Inactive" />
  )
}

// Parameterized by `kind`, rendered twice by RecipientsPage (once per new
// tab) — Groups and Channels are the same UI and API shape, differing
// only by the `kind` value sent/filtered. A real, immediate 2-consumer
// extraction, not a speculative one.
function RecipientListsPanel({
  kind,
  title,
  emptyMessage,
  addButtonLabel,
  recipientLists,
  error,
  users,
  onReload,
}: RecipientListsPanelProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RecipientListFormValues | null>(null)
  const [removing, setRemoving] = useState<RecipientListRow | null>(null)
  const [removingSubmitting, setRemovingSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // The picker never offers an inactive or unaddressable (mobile === null,
  // in practice an Administrator row) User (AC #6) — filtered out here
  // rather than relying solely on the server's MemberNotAddressable
  // rejection. The list's own already-selected members are included
  // untouched even if one has since gone inactive, so editing a list
  // doesn't silently drop a member from view (Story 3.1 code review's
  // fix for the Team select, applied here identically).
  const activeAddressableOptions = users
    .filter((user) => user.status === 'active' && user.mobile !== null)
    .map((user) => ({ id: user.id, name: user.name ?? user.mobile ?? user.id }))

  const pickerOptions =
    editing && !editing.memberUserIds.every((id) => activeAddressableOptions.some((o) => o.id === id))
      ? [
          ...activeAddressableOptions,
          ...users
            .filter(
              (user) =>
                editing.memberUserIds.includes(user.id) &&
                !activeAddressableOptions.some((o) => o.id === user.id),
            )
            .map((user) => ({ id: user.id, name: `${user.name ?? user.mobile ?? user.id} (inactive)` })),
        ]
      : activeAddressableOptions

  const columns: DataTableColumn<RecipientListRow>[] = [
    { key: 'name', header: 'Name', render: (row) => row.name },
    { key: 'members', header: 'Members', render: (row) => row.member_user_ids.length },
    { key: 'status', header: 'Status', render: (row) => statusBadge(row.status) },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={() => {
              setEditing({
                id: row.id,
                name: row.name,
                kind: row.kind,
                memberUserIds: row.member_user_ids,
              })
              setDialogOpen(true)
            }}
          >
            Edit
          </Button>
          <Button size="small" color="error" onClick={() => setRemoving(row)}>
            Remove
          </Button>
        </Stack>
      ),
    },
  ]

  async function confirmRemove() {
    if (!removing || removingSubmitting) return
    setActionError(null)
    setRemovingSubmitting(true)
    try {
      const response = await apiFetch(`/recipient-lists/${removing.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setActionError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      onReload()
    } catch {
      setActionError('Something went wrong. Please try again.')
    } finally {
      setRemovingSubmitting(false)
      setRemoving(null)
    }
  }

  return (
    <Box>
      {actionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      <Stack direction="row" sx={{ justifyContent: 'flex-end', mb: 2 }}>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null)
            setDialogOpen(true)
          }}
        >
          {addButtonLabel}
        </Button>
      </Stack>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Couldn't load {title}. Please try again.
        </Alert>
      )}
      {recipientLists && recipientLists.length === 0 ? (
        <EmptyState
          message={emptyMessage}
          actionLabel={addButtonLabel}
          onAction={() => {
            setEditing(null)
            setDialogOpen(true)
          }}
        />
      ) : (
        recipientLists && (
          <ResponsiveDataTable columns={columns} rows={recipientLists} getRowKey={(row) => row.id} />
        )
      )}

      <RecipientListFormDialog
        open={dialogOpen}
        recipientList={editing}
        kind={kind}
        options={pickerOptions}
        onClose={() => setDialogOpen(false)}
        onSaved={() => {
          setDialogOpen(false)
          onReload()
        }}
      />

      <ConfirmationDialog
        open={removing !== null}
        title={`Remove ${kind === 'group' ? 'Recipient Group' : 'Recipient Channel'}`}
        consequence={
          removing
            ? `This removes ${removing.name} from the directory. Future notifications will no longer reach its ${removing.member_user_ids.length} member(s).`
            : ''
        }
        confirmLabel="Remove"
        danger
        submitting={removingSubmitting}
        onConfirm={confirmRemove}
        onCancel={() => setRemoving(null)}
      />
    </Box>
  )
}

export default RecipientListsPanel
