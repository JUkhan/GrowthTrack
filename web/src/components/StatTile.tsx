import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Skeleton from '@mui/material/Skeleton'
import Typography from '@mui/material/Typography'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import StatusBadge from './StatusBadge'

interface StatTileProps {
  label: string
  value: ReactNode
  trend?: { direction: 'up' | 'down'; label: string }
  loading?: boolean
}

// DESIGN.md: trend indicator uses accent green (up) / status-error (down) —
// never warning — and is always paired with an up/down glyph, never bare
// colored text (same AA reasoning as the status-badge pairs, Task 5).
function StatTile({ label, value, trend, loading = false }: StatTileProps) {
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="caption" component="div" color="text.secondary">
        {label}
      </Typography>
      {loading ? (
        <Skeleton variant="rounded" width="60%" height={38} />
      ) : (
        <>
          <Typography variant="statDisplay" component="div">
            {value}
          </Typography>
          {trend && (
            <Box sx={{ mt: 1 }}>
              <StatusBadge
                status={trend.direction === 'up' ? 'success' : 'error'}
                icon={trend.direction === 'up' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
                label={trend.label}
              />
            </Box>
          )}
        </>
      )}
    </Paper>
  )
}

export default StatTile
