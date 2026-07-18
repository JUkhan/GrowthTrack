import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Typography from '@mui/material/Typography'

interface EmptyStateProps {
  message: string
  actionLabel: string
  onAction: () => void
}

// No illustration/mascot prop — DESIGN.md's Do's and Don'ts explicitly bans
// decorative empty-state mascots (AC #5/#11). `message` is always the
// caller's direct, specific copy; this component supplies no default text.
function EmptyState({ message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <Box sx={{ textAlign: 'center', py: 4 }}>
      <Typography variant="body1" gutterBottom>
        {message}
      </Typography>
      <Button variant="contained" color="primary" onClick={onAction}>
        {actionLabel}
      </Button>
    </Box>
  )
}

export default EmptyState
