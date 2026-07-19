import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import StatusBadge from './StatusBadge'
import { formatCrBdt, formatPercent } from '../utils/format'

export interface BrandEntry {
  external_brand_id: string
  brand_name: string
  sales: string
  rank: number
  growth_pct: string
}

export interface BrandPerformanceSummary {
  top_brands: BrandEntry[]
  low_performing_brands: BrandEntry[]
  focus_brands: BrandEntry[]
}

interface BrandPerformanceSectionProps {
  data: BrandPerformanceSummary | null
  loading: boolean
  error: boolean
  onRetry: () => void
}

interface BrandListConfig {
  key: keyof BrandPerformanceSummary
  heading: string
}

// No per-row classification tag: each list already sits under a heading
// naming its category, so a redundant per-row badge would just be noise
// (unlike mockups/dashboard.html's single flat list, which needed the tag).
const LISTS: BrandListConfig[] = [
  { key: 'top_brands', heading: 'Top Brands' },
  { key: 'low_performing_brands', heading: 'Low-Performing Brands' },
  { key: 'focus_brands', heading: 'Focus Brands' },
]

// Brand Performance has no admin-initiated action that would populate it —
// data arrives via nightly ingestion (Story 2.1) — so, unlike UX-DR16's
// general empty-state pattern, there is deliberately no action button here.
const EMPTY_COPY = 'No brands classified yet'

function BrandRow({ entry }: { entry: BrandEntry }) {
  const direction = Number(entry.growth_pct) >= 0 ? 'up' : 'down'
  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ justifyContent: 'space-between', alignItems: 'center', py: 1 }}
    >
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {entry.brand_name}
      </Typography>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Typography variant="body2">{formatCrBdt(entry.sales)}</Typography>
        <Typography variant="body2" color="text.secondary">
          #{entry.rank}
        </Typography>
        <StatusBadge
          status={direction === 'up' ? 'success' : 'error'}
          icon={direction === 'up' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
          label={formatPercent(entry.growth_pct)}
        />
      </Stack>
    </Stack>
  )
}

// Row count matches the configured default bucket size (brand_top_n /
// brand_low_performing_n / brand_focus_n = 5 in config.py) so the skeleton
// doesn't visibly grow once real data resolves.
function BrandListSkeleton() {
  return (
    <Stack spacing={1}>
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} variant="rounded" height={32} />
      ))}
    </Stack>
  )
}

// Independent loading/error state from Story 2.2's seven-field skeleton
// batch — Brand Performance is explicitly an "additional section" per
// epics.md's Story 2.3 AC, not part of that batch, so it fetches and
// fails on its own schedule.
function BrandPerformanceSection({ data, loading, error, onRetry }: BrandPerformanceSectionProps) {
  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" component="h2" sx={{ mb: 2 }}>
        Brand Performance
      </Typography>

      {error && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={onRetry}>
              Retry
            </Button>
          }
        >
          Couldn't load brand performance data. Please try again.
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
          gap: 2,
        }}
      >
        {LISTS.map((list) => {
          const entries = data?.[list.key] ?? []
          return (
            <Paper key={list.key} sx={{ p: 2 }}>
              <Typography variant="subtitle1" component="h3" sx={{ mb: 1, fontWeight: 600 }}>
                {list.heading}
              </Typography>
              {loading ? (
                <BrandListSkeleton />
              ) : entries.length > 0 ? (
                <Stack divider={<Box sx={{ borderBottom: 1, borderColor: 'divider' }} />}>
                  {entries.map((entry) => (
                    <BrandRow key={entry.external_brand_id} entry={entry} />
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  {EMPTY_COPY}
                </Typography>
              )}
            </Paper>
          )
        })}
      </Box>
    </Box>
  )
}

export default BrandPerformanceSection
