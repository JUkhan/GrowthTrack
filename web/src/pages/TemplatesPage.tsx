import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, Link as RouterLink } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Container from '@mui/material/Container'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import EmptyState from '../components/EmptyState'
import ResponsiveDataTable from '../components/ResponsiveDataTable'
import type { DataTableColumn } from '../components/ResponsiveDataTable'
import { apiFetch } from '../api/authClient'
import TemplateFormDialog from './TemplateFormDialog'
import type { TemplateFormValues } from './TemplateFormDialog'

type SessionStatus = { kind: 'loading' } | { kind: 'authenticated' } | { kind: 'unauthenticated' }

interface MessageTemplateRow {
  id: string
  name: string
  twilio_content_sid: string
  variable_slots: string[]
  body_preview_template: string
}

// No shared nav shell exists yet (RecipientsPage.tsx's own comment flags
// this as unowned by any story) — this page duplicates the session-check
// pattern rather than inventing one.
function TemplatesPage() {
  const [session, setSession] = useState<SessionStatus>({ kind: 'loading' })
  const [templates, setTemplates] = useState<MessageTemplateRow[] | null>(null)
  const [templatesError, setTemplatesError] = useState(false)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<TemplateFormValues | null>(null)

  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
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

  const loadTemplates = useCallback(async () => {
    setTemplatesError(false)
    try {
      const response = await apiFetch('/message-templates')
      if (!isMountedRef.current) return
      if (!response.ok) {
        setTemplatesError(true)
        return
      }
      setTemplates((await response.json()) as MessageTemplateRow[])
    } catch {
      if (isMountedRef.current) setTemplatesError(true)
    }
  }, [])

  useEffect(() => {
    if (session.kind !== 'authenticated') return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- same fetch-on-mount shape as RecipientsPage.tsx's existing load effects
    loadTemplates()
  }, [session.kind, loadTemplates])

  if (session.kind === 'loading') {
    return null
  }

  if (session.kind === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  function openCreateDialog() {
    setEditingTemplate(null)
    setDialogOpen(true)
  }

  const columns: DataTableColumn<MessageTemplateRow>[] = [
    { key: 'name', header: 'Name', render: (row) => row.name },
    { key: 'sid', header: 'Content SID', render: (row) => row.twilio_content_sid },
    {
      key: 'variable_slots',
      header: 'Variable Slots',
      render: (row) => (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
          {row.variable_slots.length === 0
            ? '—'
            : // Positionally ordered, not independently identified — no stable id to key by.
              row.variable_slots.map((slot, index) => (
                <Chip key={index} label={slot} size="small" />
              ))}
        </Stack>
      ),
    },
    {
      key: 'preview',
      header: 'Preview Text',
      render: (row) => (
        <Typography
          variant="body2"
          sx={{
            maxWidth: 320,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={row.body_preview_template}
        >
          {row.body_preview_template}
        </Typography>
      ),
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Button
          size="small"
          onClick={() => {
            setEditingTemplate({
              id: row.id,
              name: row.name,
              twilioContentSid: row.twilio_content_sid,
              variableSlots: row.variable_slots,
              bodyPreviewTemplate: row.body_preview_template,
            })
            setDialogOpen(true)
          }}
        >
          Edit
        </Button>
      ),
    },
  ]

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
      >
        <Typography variant="h4">Message Templates</Typography>
        <Button variant="contained" onClick={openCreateDialog}>
          Add Template
        </Button>
      </Stack>

      <Link component={RouterLink} to="/notifications/compose" sx={{ mb: 2, display: 'inline-block' }}>
        Back to Compose Notification
      </Link>

      {templatesError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Couldn't load message templates. Please try again.
        </Alert>
      )}

      {templates !== null && templates.length === 0 ? (
        <EmptyState
          message="No message templates yet"
          actionLabel="Add Template"
          onAction={openCreateDialog}
        />
      ) : (
        <ResponsiveDataTable
          columns={columns}
          rows={templates ?? []}
          getRowKey={(row) => row.id}
        />
      )}

      <TemplateFormDialog
        open={dialogOpen}
        template={editingTemplate}
        onClose={() => setDialogOpen(false)}
        onSaved={() => {
          setDialogOpen(false)
          loadTemplates()
        }}
      />
    </Container>
  )
}

export default TemplatesPage
