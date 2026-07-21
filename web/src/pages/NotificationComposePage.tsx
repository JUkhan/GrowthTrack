import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Link as RouterLink, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import FormControlLabel from '@mui/material/FormControlLabel'
import Link from '@mui/material/Link'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'
import MixedRecipientPicker from '../components/MixedRecipientPicker'
import type { RecipientEntry, ResolvedCounts } from '../components/MixedRecipientPicker'

type SessionStatus = { kind: 'loading' } | { kind: 'authenticated' } | { kind: 'unauthenticated' }

interface DirectoryUser {
  id: string
  name: string | null
  username: string | null
  status: 'active' | 'inactive'
  mobile: string | null
}

interface DirectoryTeam {
  id: string
  name: string
  status: 'active' | 'inactive'
}

interface DirectoryRecipientList {
  id: string
  name: string
  status: 'active' | 'inactive'
}

interface MessageTemplate {
  id: string
  name: string
  variable_slots: string[]
  body_preview_template: string
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function renderPreview(template: MessageTemplate | null, values: Record<string, string>): string {
  if (!template) return ''
  if (template.variable_slots.length === 0) return template.body_preview_template
  // Single pass over the original template text, not a sequential
  // split/join per slot — re-scanning the accumulated string after each
  // substitution would let one slot's typed value (if it happens to
  // contain literal "{other_slot}" text) get wrongly substituted again on
  // a later iteration, showing a preview that doesn't match what Twilio's
  // Content API actually sends (a flat content_variables dict, not
  // sequential string templating).
  const pattern = new RegExp(
    template.variable_slots.map((slot) => `\\{${escapeRegExp(slot)}\\}`).join('|'),
    'g',
  )
  return template.body_preview_template.replace(pattern, (match) => values[match.slice(1, -1)] ?? '')
}

// No nav shell exists yet in this codebase (DashboardPage.tsx's own comment
// flags this as unowned by any story) — a "Back to Dashboard" link is this
// page's placement of the mockup's sidebar "Notifications" nav item, same
// lightweight pattern RecipientsPage.tsx already uses.
function NotificationComposePage() {
  const [session, setSession] = useState<SessionStatus>({ kind: 'loading' })
  const navigate = useNavigate()

  const [users, setUsers] = useState<DirectoryUser[]>([])
  const [teams, setTeams] = useState<DirectoryTeam[]>([])
  const [recipientLists, setRecipientLists] = useState<DirectoryRecipientList[]>([])
  const [templates, setTemplates] = useState<MessageTemplate[]>([])
  const [optionsError, setOptionsError] = useState(false)

  const [selected, setSelected] = useState<RecipientEntry[]>([])
  const [resolved, setResolved] = useState<ResolvedCounts | null>(null)

  const [templateId, setTemplateId] = useState('')
  const [variableValues, setVariableValues] = useState<Record<string, string>>({})

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

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

  const loadOptions = useCallback(async () => {
    setOptionsError(false)
    try {
      const [usersRes, teamsRes, listsRes, templatesRes] = await Promise.all([
        apiFetch('/users'),
        apiFetch('/teams'),
        apiFetch('/recipient-lists'),
        apiFetch('/message-templates'),
      ])
      if (!usersRes.ok || !teamsRes.ok || !listsRes.ok || !templatesRes.ok) {
        setOptionsError(true)
        return
      }
      setUsers((await usersRes.json()) as DirectoryUser[])
      setTeams((await teamsRes.json()) as DirectoryTeam[])
      setRecipientLists((await listsRes.json()) as DirectoryRecipientList[])
      setTemplates((await templatesRes.json()) as MessageTemplate[])
    } catch {
      setOptionsError(true)
    }
  }, [])

  useEffect(() => {
    if (session.kind !== 'authenticated') return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, same shape as DashboardPage.tsx's existing effects
    loadOptions()
  }, [session.kind, loadOptions])

  const pickerOptions: RecipientEntry[] = useMemo(
    () => [
      // GET /users returns every role/status, including Administrators
      // (always mobile=None) and inactive Users — filtered out here so an
      // ineligible pick is never offered in the first place, the same
      // contract RecipientPicker.tsx already enforces on its own options.
      ...users
        .filter((user) => user.status === 'active' && user.mobile != null)
        .map((user): RecipientEntry => ({ id: user.id, name: user.name ?? user.username ?? user.id, type: 'user' })),
      ...teams
        .filter((team) => team.status === 'active')
        .map((team): RecipientEntry => ({ id: team.id, name: team.name, type: 'team' })),
      ...recipientLists
        .filter((list) => list.status === 'active')
        .map((list): RecipientEntry => ({ id: list.id, name: list.name, type: 'recipient_list' })),
    ],
    [users, teams, recipientLists],
  )

  const selectedTemplate = templates.find((template) => template.id === templateId) ?? null

  function handleTemplateChange(nextTemplateId: string) {
    setTemplateId(nextTemplateId)
    const nextTemplate = templates.find((template) => template.id === nextTemplateId) ?? null
    setVariableValues(
      Object.fromEntries((nextTemplate?.variable_slots ?? []).map((slot) => [slot, ''])),
    )
  }

  const uniqueCount = resolved?.uniqueCount ?? 0
  const hasBlankVariable =
    selectedTemplate?.variable_slots.some((slot) => !variableValues[slot]?.trim()) ?? false
  const canSend = uniqueCount > 0 && selectedTemplate !== null && !hasBlankVariable && !submitting

  let recipientHint: string | null = null
  if (!submitting) {
    if (selected.length === 0) {
      recipientHint = 'Select at least one recipient'
    } else if (resolved === null) {
      recipientHint = 'Resolving recipients…'
    } else if (uniqueCount === 0) {
      recipientHint = 'No eligible recipients in this selection'
    }
  }

  async function handleSend() {
    if (!canSend || !selectedTemplate) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const response = await apiFetch('/notifications', {
        method: 'POST',
        body: JSON.stringify({
          template_id: selectedTemplate.id,
          variable_values: variableValues,
          user_ids: selected.filter((entry) => entry.type === 'user').map((entry) => entry.id),
          team_ids: selected.filter((entry) => entry.type === 'team').map((entry) => entry.id),
          recipient_list_ids: selected
            .filter((entry) => entry.type === 'recipient_list')
            .map((entry) => entry.id),
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setSubmitError(body?.error?.message ?? 'Something went wrong. Please try again.')
        return
      }
      navigate('/dashboard')
    } catch {
      setSubmitError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (session.kind === 'loading') {
    return null
  }

  if (session.kind === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
          New Manual Notification
        </Typography>
        <Link component={RouterLink} to="/dashboard">
          Back to Dashboard
        </Link>
      </Stack>

      {optionsError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Couldn't load recipients or templates. Please try again.
        </Alert>
      )}

      {submitError && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setSubmitError(null)}>
          {submitError}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1.3fr 1fr' },
          gap: 3,
        }}
      >
        <Stack spacing={3}>
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Recipients
            </Typography>
            <MixedRecipientPicker
              options={pickerOptions}
              selected={selected}
              onChange={setSelected}
              onResolvedChange={setResolved}
            />
          </Box>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Message
            </Typography>
            <Stack spacing={2}>
              <TextField
                select
                label="Template"
                value={templateId}
                onChange={(event) => handleTemplateChange(event.target.value)}
              >
                {templates.map((template) => (
                  <MenuItem key={template.id} value={template.id}>
                    {template.name}
                  </MenuItem>
                ))}
              </TextField>
              {selectedTemplate?.variable_slots.map((slot) => (
                <TextField
                  key={slot}
                  label={slot}
                  value={variableValues[slot] ?? ''}
                  onChange={(event) =>
                    setVariableValues((prev) => ({ ...prev, [slot]: event.target.value }))
                  }
                />
              ))}
              <Tooltip title="Report attachment available once Daily Reports are generated — Story 4.2">
                <FormControlLabel
                  control={<Checkbox checked={false} disabled />}
                  label="Attach current report"
                />
              </Tooltip>
            </Stack>
          </Box>

          <Stack direction="row" spacing={2} sx={{ justifyContent: 'flex-end', alignItems: 'center' }}>
            <Button variant="outlined" component={RouterLink} to="/dashboard" disabled={submitting}>
              Cancel
            </Button>
            <Stack alignItems="flex-end" spacing={0.5}>
              <Button
                variant="contained"
                disabled={!canSend}
                onClick={handleSend}
                startIcon={submitting ? <CircularProgress size={16} color="inherit" /> : undefined}
              >
                {submitting ? `Sending to ${uniqueCount} recipients…` : `Send to ${uniqueCount} recipients`}
              </Button>
              {recipientHint && (
                <Typography variant="caption" color="text.secondary">
                  {recipientHint}
                </Typography>
              )}
            </Stack>
          </Stack>
        </Stack>

        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Live WhatsApp Preview
          </Typography>
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2 }}>
            <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 2, whiteSpace: 'pre-line' }}>
              {selectedTemplate ? (
                renderPreview(selectedTemplate, variableValues)
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Select a template to preview the message.
                </Typography>
              )}
            </Box>
            <Typography variant="caption" color="text.secondary">
              Preview — not yet sent
            </Typography>
          </Box>
        </Box>
      </Box>
    </Container>
  )
}

export default NotificationComposePage
