import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, Link as RouterLink } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import MarkChatReadIcon from '@mui/icons-material/MarkChatRead'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ConfirmationDialog from '../components/ConfirmationDialog'
import EmptyState from '../components/EmptyState'
import ResponsiveDataTable from '../components/ResponsiveDataTable'
import type { DataTableColumn } from '../components/ResponsiveDataTable'
import StatusBadge from '../components/StatusBadge'
import { apiFetch } from '../api/authClient'
import RecipientListsPanel from './RecipientListsPanel'
import type { RecipientListRow } from './RecipientListsPanel'
import TeamFormDialog from './TeamFormDialog'
import type { TeamFormValues } from './TeamFormDialog'
import UserFormDialog from './UserFormDialog'
import type { TeamOption, UserFormValues } from './UserFormDialog'

type SessionStatus = { kind: 'loading' } | { kind: 'authenticated' } | { kind: 'unauthenticated' }

export interface DirectoryUser {
  id: string
  name: string | null
  mobile: string | null
  username: string | null
  role: string
  status: 'active' | 'inactive'
  team_id: string | null
  team_name: string | null
  version: number
  consent_status: 'opted_in' | 'not_opted_in'
  consent_recorded_at: string | null
}

interface DirectoryTeam {
  id: string
  name: string
  status: 'active' | 'inactive'
  version: number
}

const ROLE_LABELS: Record<string, string> = {
  administrator: 'Administrator',
  sales_user: 'Sales User',
  manager: 'Manager',
}

function statusBadge(status: 'active' | 'inactive') {
  return status === 'active' ? (
    <StatusBadge status="success" icon={<CheckCircleIcon />} label="Active" />
  ) : (
    <StatusBadge status="neutral" icon={<BlockIcon />} label="Inactive" />
  )
}

// Uses MarkChatReadIcon (not CheckCircleIcon) so the Opted In badge is
// visually distinct from the Active status badge at a glance — both are
// "success"-colored, so the icon shape is the only differentiator.
function consentBadge(status: 'opted_in' | 'not_opted_in') {
  return status === 'opted_in' ? (
    <StatusBadge status="success" icon={<MarkChatReadIcon />} label="Opted In" />
  ) : (
    <StatusBadge status="warning" icon={<WarningAmberIcon />} label="Not Opted In" />
  )
}

// RecipientsPage duplicates DashboardPage's session-check-and-redirect
// pattern rather than extracting a shared layout — no nav shell exists yet
// (DashboardPage's own comment flags this as unowned by any story).
function RecipientsPage() {
  const [session, setSession] = useState<SessionStatus>({ kind: 'loading' })
  const [tab, setTab] = useState<'users' | 'teams' | 'groups' | 'channels'>('users')

  const [users, setUsers] = useState<DirectoryUser[] | null>(null)
  const [usersError, setUsersError] = useState(false)
  const [teams, setTeams] = useState<DirectoryTeam[] | null>(null)
  const [teamsError, setTeamsError] = useState(false)
  const [recipientLists, setRecipientLists] = useState<RecipientListRow[] | null>(null)
  const [recipientListsError, setRecipientListsError] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const [userDialogOpen, setUserDialogOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserFormValues | null>(null)
  const [removingUser, setRemovingUser] = useState<DirectoryUser | null>(null)
  const [removingUserSubmitting, setRemovingUserSubmitting] = useState(false)

  const [teamDialogOpen, setTeamDialogOpen] = useState(false)
  const [editingTeam, setEditingTeam] = useState<TeamFormValues | null>(null)
  const [removingTeam, setRemovingTeam] = useState<DirectoryTeam | null>(null)
  const [removingTeamSubmitting, setRemovingTeamSubmitting] = useState(false)

  // Shared across every fetch this page kicks off (not just the two
  // effects below) — a create/edit/remove action can still be in flight
  // when the user navigates away, and its subsequent loadUsers()/
  // loadTeams() refresh must not setState on an unmounted component.
  const isMountedRef = useRef(true)
  useEffect(() => {
    return () => {
      isMountedRef.current = false
    }
  }, [])

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

  const loadUsers = useCallback(async () => {
    setUsersError(false)
    try {
      const response = await apiFetch('/users')
      if (!isMountedRef.current) return
      if (!response.ok) {
        setUsersError(true)
        return
      }
      setUsers((await response.json()) as DirectoryUser[])
    } catch {
      if (isMountedRef.current) setUsersError(true)
    }
  }, [])

  const loadTeams = useCallback(async () => {
    setTeamsError(false)
    try {
      const response = await apiFetch('/teams')
      if (!isMountedRef.current) return
      if (!response.ok) {
        setTeamsError(true)
        return
      }
      setTeams((await response.json()) as DirectoryTeam[])
    } catch {
      if (isMountedRef.current) setTeamsError(true)
    }
  }, [])

  const loadRecipientLists = useCallback(async () => {
    setRecipientListsError(false)
    try {
      const response = await apiFetch('/recipient-lists')
      if (!isMountedRef.current) return
      if (!response.ok) {
        setRecipientListsError(true)
        return
      }
      setRecipientLists((await response.json()) as RecipientListRow[])
    } catch {
      if (isMountedRef.current) setRecipientListsError(true)
    }
  }, [])

  useEffect(() => {
    if (session.kind !== 'authenticated') return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- same fetch-on-mount shape as DashboardPage.tsx's existing summary/brand-performance effects
    loadUsers()
    loadTeams()
    loadRecipientLists()
  }, [session.kind, loadUsers, loadTeams, loadRecipientLists])

  if (session.kind === 'loading') {
    return null
  }

  if (session.kind === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  const activeTeamOptions: TeamOption[] = (teams ?? [])
    .filter((team) => team.status === 'active')
    .map((team) => ({ id: team.id, name: team.name }))

  // Include the User's currently-assigned Team even if it's since been
  // deactivated, so editing doesn't render a blank Team select for a row
  // whose Team was removed after assignment (code review of Story 3.1).
  const groupLists = (recipientLists ?? []).filter((list) => list.kind === 'group')
  const channelLists = (recipientLists ?? []).filter((list) => list.kind === 'channel')

  const editingUserTeamOptions: TeamOption[] =
    editingUser && !activeTeamOptions.some((option) => option.id === editingUser.teamId)
      ? [
          ...activeTeamOptions,
          ...(teams ?? [])
            .filter((team) => team.id === editingUser.teamId)
            .map((team) => ({ id: team.id, name: `${team.name} (inactive)` })),
        ]
      : activeTeamOptions

  const userColumns: DataTableColumn<DirectoryUser>[] = [
    { key: 'name', header: 'Name', render: (row) => row.name ?? row.username ?? '—' },
    { key: 'mobile', header: 'Mobile', render: (row) => row.mobile ?? '—' },
    { key: 'role', header: 'Role', render: (row) => ROLE_LABELS[row.role] ?? row.role },
    { key: 'team', header: 'Team', render: (row) => row.team_name ?? '—' },
    { key: 'status', header: 'Status', render: (row) => statusBadge(row.status) },
    { key: 'consent', header: 'Consent', render: (row) => consentBadge(row.consent_status) },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Stack direction="row" spacing={1}>
          {row.role !== 'administrator' && (
            <Button
              size="small"
              onClick={() => {
                setEditingUser({
                  id: row.id,
                  name: row.name ?? '',
                  mobile: row.mobile ?? '',
                  role: row.role as 'sales_user' | 'manager',
                  teamId: row.team_id ?? '',
                  consentStatus: row.consent_status,
                  consentRecordedAt: row.consent_recorded_at,
                })
                setUserDialogOpen(true)
              }}
            >
              Edit
            </Button>
          )}
          <Button size="small" color="error" onClick={() => setRemovingUser(row)}>
            Remove
          </Button>
        </Stack>
      ),
    },
  ]

  const teamColumns: DataTableColumn<DirectoryTeam>[] = [
    { key: 'name', header: 'Name', render: (row) => row.name },
    { key: 'status', header: 'Status', render: (row) => statusBadge(row.status) },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={() => {
              setEditingTeam({ id: row.id, name: row.name })
              setTeamDialogOpen(true)
            }}
          >
            Edit
          </Button>
          <Button size="small" color="error" onClick={() => setRemovingTeam(row)}>
            Remove
          </Button>
        </Stack>
      ),
    },
  ]

  async function confirmRemoveUser() {
    if (!removingUser || removingUserSubmitting) return
    setActionError(null)
    setRemovingUserSubmitting(true)
    try {
      const response = await apiFetch(`/users/${removingUser.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setActionError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      await loadUsers()
    } catch {
      setActionError('Something went wrong. Please try again.')
    } finally {
      setRemovingUserSubmitting(false)
      setRemovingUser(null)
    }
  }

  async function confirmRemoveTeam() {
    if (!removingTeam || removingTeamSubmitting) return
    setActionError(null)
    setRemovingTeamSubmitting(true)
    try {
      const response = await apiFetch(`/teams/${removingTeam.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setActionError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      await loadTeams()
    } catch {
      setActionError('Something went wrong. Please try again.')
    } finally {
      setRemovingTeamSubmitting(false)
      setRemovingTeam(null)
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
          Recipients
        </Typography>
        <Link component={RouterLink} to="/dashboard">
          Back to Dashboard
        </Link>
      </Stack>

      {actionError && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}

      <Tabs
        value={tab}
        onChange={(_, value) => {
          setActionError(null)
          setTab(value)
        }}
        sx={{ mb: 3 }}
      >
        <Tab value="users" label="Users" />
        <Tab value="teams" label="Sales Teams" />
        <Tab value="groups" label="Recipient Groups" />
        <Tab value="channels" label="Recipient Channels" />
      </Tabs>

      {tab === 'users' && (
        <Box>
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', alignItems: 'center', mb: 2 }}>
            {activeTeamOptions.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                Add a Sales Team first before adding Users.
              </Typography>
            )}
            <Button
              variant="contained"
              disabled={activeTeamOptions.length === 0}
              onClick={() => {
                setEditingUser(null)
                setUserDialogOpen(true)
              }}
            >
              Add User
            </Button>
          </Stack>
          {usersError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Couldn't load Users. Please try again.
            </Alert>
          )}
          {users && users.length === 0 ? (
            activeTeamOptions.length === 0 ? (
              <EmptyState
                message="No Sales Teams yet. Add a Sales Team before adding Users — every User needs one."
                actionLabel="Add Sales Team"
                onAction={() => {
                  setEditingTeam(null)
                  setTeamDialogOpen(true)
                }}
              />
            ) : (
              <EmptyState
                message="No Users yet. Add your first Sales User or Manager to start building the notification directory."
                actionLabel="Add User"
                onAction={() => {
                  setEditingUser(null)
                  setUserDialogOpen(true)
                }}
              />
            )
          ) : (
            users && (
              <ResponsiveDataTable columns={userColumns} rows={users} getRowKey={(row) => row.id} />
            )
          )}
        </Box>
      )}

      {tab === 'teams' && (
        <Box>
          <Stack direction="row" sx={{ justifyContent: 'flex-end', mb: 2 }}>
            <Button
              variant="contained"
              onClick={() => {
                setEditingTeam(null)
                setTeamDialogOpen(true)
              }}
            >
              Add Sales Team
            </Button>
          </Stack>
          {teamsError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Couldn't load Sales Teams. Please try again.
            </Alert>
          )}
          {teams && teams.length === 0 ? (
            <EmptyState
              message="No Sales Teams yet. Add your first team to start organizing Users."
              actionLabel="Add Sales Team"
              onAction={() => {
                setEditingTeam(null)
                setTeamDialogOpen(true)
              }}
            />
          ) : (
            teams && (
              <ResponsiveDataTable columns={teamColumns} rows={teams} getRowKey={(row) => row.id} />
            )
          )}
        </Box>
      )}

      {tab === 'groups' && (
        <RecipientListsPanel
          kind="group"
          title="Recipient Groups"
          emptyMessage="No Recipient Groups yet. Add your first Group to target a named set of Users in one selection."
          addButtonLabel="Add Recipient Group"
          recipientLists={groupLists}
          error={recipientListsError}
          users={users ?? []}
          onReload={loadRecipientLists}
        />
      )}

      {tab === 'channels' && (
        <RecipientListsPanel
          kind="channel"
          title="Recipient Channels"
          emptyMessage="No Recipient Channels yet. Add your first Channel to target a named set of Users in one selection."
          addButtonLabel="Add Recipient Channel"
          recipientLists={channelLists}
          error={recipientListsError}
          users={users ?? []}
          onReload={loadRecipientLists}
        />
      )}

      <UserFormDialog
        open={userDialogOpen}
        user={editingUser}
        teams={editingUserTeamOptions}
        onClose={() => setUserDialogOpen(false)}
        onSaved={() => {
          setUserDialogOpen(false)
          loadUsers()
        }}
        onConsentChanged={loadUsers}
      />

      <TeamFormDialog
        open={teamDialogOpen}
        team={editingTeam}
        onClose={() => setTeamDialogOpen(false)}
        onSaved={() => {
          setTeamDialogOpen(false)
          loadTeams()
        }}
      />

      <ConfirmationDialog
        open={removingUser !== null}
        title="Remove User"
        consequence={
          removingUser
            ? `This removes ${removingUser.name ?? removingUser.username ?? 'this User'} from the directory. Future notifications will no longer reach them.`
            : ''
        }
        confirmLabel="Remove"
        danger
        submitting={removingUserSubmitting}
        onConfirm={confirmRemoveUser}
        onCancel={() => setRemovingUser(null)}
      />

      <ConfirmationDialog
        open={removingTeam !== null}
        title="Remove Sales Team"
        consequence={
          removingTeam
            ? `This removes ${removingTeam.name} from the directory.`
            : ''
        }
        confirmLabel="Remove"
        danger
        submitting={removingTeamSubmitting}
        onConfirm={confirmRemoveTeam}
        onCancel={() => setRemovingTeam(null)}
      />
    </Container>
  )
}

export default RecipientsPage
