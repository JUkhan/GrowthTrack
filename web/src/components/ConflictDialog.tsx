import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

export interface ConflictField {
  label: string
  mine: string
  theirs: string
}

interface ConflictDialogProps {
  open: boolean
  entityLabel: string
  fields: ConflictField[]
  submitting?: boolean
  onKeepMine: () => void
  onDiscardMine: () => void
}

// Deliberately no `onClose` prop wired to the MUI `Dialog` — omitting it
// means backdrop-click/Escape do nothing while this dialog is open,
// forcing one of the two explicit buttons below. This is the concrete
// mechanism behind AC #2's "requires an explicit choice — never a silent
// overwrite."
function ConflictDialog({
  open,
  entityLabel,
  fields,
  submitting = false,
  onKeepMine,
  onDiscardMine,
}: ConflictDialogProps) {
  return (
    <Dialog open={open}>
      <DialogTitle>Conflicting Changes</DialogTitle>
      <DialogContent>
        <DialogContentText>
          {`This ${entityLabel} was changed by someone else since you opened it. Review both versions, then choose whether to keep your changes or discard them.`}
        </DialogContentText>
        <Stack spacing={2} sx={{ pt: 2 }}>
          {fields.map((field) => (
            <Stack key={field.label}>
              <Typography variant="subtitle2">{field.label}</Typography>
              <Typography variant="body2">Yours: {field.mine}</Typography>
              <Typography variant="body2" color="text.secondary">
                Current: {field.theirs}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onDiscardMine} disabled={submitting}>
          Discard My Changes
        </Button>
        <Button onClick={onKeepMine} variant="contained" disabled={submitting}>
          Keep My Changes
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default ConflictDialog
