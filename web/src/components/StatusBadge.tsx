import type { ReactElement } from 'react'
import Chip from '@mui/material/Chip'
import { rounded } from '../theme/tokens'

interface StatusBadgeProps {
  status: 'success' | 'warning' | 'error'
  icon: ReactElement
  label: string
}

// Always both icon and label — never a color-only rendering (DESIGN.md's
// "never color alone" rule; AC #7/#9's accessibility floor). No default
// icon: the specific glyph (check/clock/alert-triangle/retry-arrow) varies
// per call site's actual state, so callers always pass one explicitly.
function StatusBadge({ status, icon, label }: StatusBadgeProps) {
  return <Chip color={status} icon={icon} label={label} sx={{ borderRadius: rounded.full }} />
}

export default StatusBadge
