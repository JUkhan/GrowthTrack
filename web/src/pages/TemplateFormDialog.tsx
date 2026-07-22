import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import { apiFetch } from '../api/authClient'

export interface TemplateFormValues {
  id: string
  name: string
  twilioContentSid: string
  variableSlots: string[]
  bodyPreviewTemplate: string
}

interface TemplateFormDialogProps {
  open: boolean
  template: TemplateFormValues | null
  onClose: () => void
  onSaved: () => void
}

// One component for create + edit (`template === null` means create), same
// shape as TeamFormDialog — but no version/ConflictDialog handling, since
// MessageTemplate has no optimistic-concurrency column (Story 4.5, AC #4).
function TemplateFormDialog({ open, template, onClose, onSaved }: TemplateFormDialogProps) {
  const [name, setName] = useState('')
  const [twilioContentSid, setTwilioContentSid] = useState('')
  const [variableSlots, setVariableSlots] = useState<string[]>([])
  const [bodyPreviewTemplate, setBodyPreviewTemplate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the form to the dialog's target record each time it opens
      setName(template?.name ?? '')
      setTwilioContentSid(template?.twilioContentSid ?? '')
      setVariableSlots(template?.variableSlots ?? [])
      setBodyPreviewTemplate(template?.bodyPreviewTemplate ?? '')
      setError(null)
    }
  }, [open, template])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const response = await apiFetch(
        template ? `/message-templates/${template.id}` : '/message-templates',
        {
          method: template ? 'PATCH' : 'POST',
          body: JSON.stringify({
            name,
            twilio_content_sid: twilioContentSid,
            variable_slots: variableSlots,
            body_preview_template: bodyPreviewTemplate,
          }),
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

  function updateSlot(index: number, value: string) {
    setVariableSlots((slots) => slots.map((slot, i) => (i === index ? value : slot)))
  }

  function removeSlot(index: number) {
    setVariableSlots((slots) => slots.filter((_, i) => i !== index))
  }

  function addSlot() {
    setVariableSlots((slots) => [...slots, ''])
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={handleSubmit}>
        <DialogTitle>{template ? 'Edit Message Template' : 'Add Message Template'}</DialogTitle>
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
              label="Twilio Content SID"
              value={twilioContentSid}
              onChange={(event) => setTwilioContentSid(event.target.value)}
              helperText="From the approved template in the Twilio Console (Content API)"
              required
            />
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Variable Slots
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                gutterBottom
                sx={{ display: 'block' }}
              >
                Order matters — it maps positionally to Twilio's template variables ({'{1}'},{' '}
                {'{2}'}, …). Reference each by name in Preview Text as {'{slot_name}'}.
              </Typography>
              <Stack spacing={1}>
                {variableSlots.map((slot, index) => (
                  // Positionally ordered and freely reordered/removed — no stable id to key by.
                  <Stack key={index} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <TextField
                      value={slot}
                      onChange={(event) => updateSlot(index, event.target.value)}
                      size="small"
                      fullWidth
                      label={`Slot ${index + 1}`}
                      required
                    />
                    <IconButton
                      type="button"
                      aria-label={`Remove slot ${index + 1}`}
                      onClick={() => removeSlot(index)}
                      size="small"
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
                <Button
                  type="button"
                  startIcon={<AddIcon />}
                  onClick={addSlot}
                  size="small"
                  sx={{ alignSelf: 'flex-start' }}
                >
                  Add Slot
                </Button>
              </Stack>
            </Box>
            <TextField
              label="Preview Text"
              value={bodyPreviewTemplate}
              onChange={(event) => setBodyPreviewTemplate(event.target.value)}
              helperText="Human-readable text with {slot_name} placeholders — used for the composer's live preview only"
              multiline
              minRows={3}
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
  )
}

export default TemplateFormDialog
