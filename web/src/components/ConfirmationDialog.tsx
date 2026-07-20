import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogTitle from '@mui/material/DialogTitle'

interface ConfirmationDialogProps {
  open: boolean
  title: string
  consequence: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  danger?: boolean
  submitting?: boolean
}

// `consequence` is always the caller's real, specific text (AC #11) — this
// component has no generic "Are you sure?" fallback copy anywhere. Relies
// on MUI Dialog's built-in focus trap and return-focus-to-trigger-on-close
// (AC #9) — disableRestoreFocus is never set.
function ConfirmationDialog({
  open,
  title,
  consequence,
  confirmLabel,
  onConfirm,
  onCancel,
  danger = false,
  submitting = false,
}: ConfirmationDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{consequence}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color={danger ? 'error' : 'primary'}
          disabled={submitting}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default ConfirmationDialog
