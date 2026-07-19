import { useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import AccessTimeIcon from '@mui/icons-material/AccessTime'
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import { apiFetch } from '../api/authClient'
import BrandPerformanceSection from '../components/BrandPerformanceSection'
import type { BrandPerformanceSummary } from '../components/BrandPerformanceSection'
import StatTile from '../components/StatTile'
import StatusBadge from '../components/StatusBadge'
import ThemeToggle from '../components/ThemeToggle'
import { useThemeMode } from '../theme/ThemeModeContext'
import { formatCrBdt, formatPercent } from '../utils/format'

type SessionStatus =
  | { kind: 'loading' }
  | { kind: 'authenticated' }
  | { kind: 'unauthenticated'; message?: string }

interface TeamPerformance {
  team_name: string
  achievement_pct: string
}

interface DashboardSummary {
  today_sales: string
  ytd_sales: string
  mtd_sales: string
  achievement_pct: string | null
  growth_pct: string | null
  team_performance: TeamPerformance[]
  data_as_of: string | null
  is_stale: boolean
}

interface FreshnessBadge {
  status: 'neutral' | 'warning'
  icon: ReactElement
  label: string
}

function formatDhakaTime(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Dhaka',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(iso))
}

function freshnessBadge(dataAsOf: string | null, isStale: boolean): FreshnessBadge {
  if (dataAsOf === null) {
    return { status: 'warning', icon: <WarningAmberIcon />, label: 'No data yet' }
  }
  const hhmm = formatDhakaTime(dataAsOf)
  if (isStale) {
    return {
      status: 'warning',
      icon: <WarningAmberIcon />,
      label: `Data as of ${hhmm} — source refresh delayed`,
    }
  }
  return { status: 'neutral', icon: <AccessTimeIcon />, label: `Data as of ${hhmm}, Asia/Dhaka` }
}

function displayPercent(pct: string | null): string {
  return pct === null ? '—' : formatPercent(pct)
}

// Session/route-guard effect (GET /auth/me), Logout button, ThemeToggle, and
// the account-deactivated message relay are carried forward from the
// placeholder HomePage this story replaces — still provisional placements
// (EXPERIENCE.md's eventual home for both is a nav shell no story owns yet).
function DashboardPage() {
  const [session, setSession] = useState<SessionStatus>({ kind: 'loading' })
  const [submitting, setSubmitting] = useState(false)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const [brandPerformance, setBrandPerformance] = useState<BrandPerformanceSummary | null>(null)
  const [brandPerformanceError, setBrandPerformanceError] = useState(false)
  const [brandPerformanceRetryCount, setBrandPerformanceRetryCount] = useState(0)
  const navigate = useNavigate()
  const { resetPreference } = useThemeMode()

  useEffect(() => {
    let cancelled = false

    apiFetch('/auth/me')
      .then(async (response) => {
        if (cancelled) return
        if (response.ok) {
          setSession({ kind: 'authenticated' })
          return
        }
        const body = await response.json().catch(() => null)
        setSession({
          kind: 'unauthenticated',
          message: body?.error?.code === 'account_deactivated' ? body.error.message : undefined,
        })
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

  useEffect(() => {
    if (session.kind !== 'authenticated') return
    let cancelled = false

    apiFetch('/dashboard/summary')
      .then(async (response) => {
        if (cancelled) return
        if (!response.ok) {
          setSummaryError(true)
          return
        }
        const body = (await response.json()) as DashboardSummary
        if (!cancelled) {
          setSummary(body)
          setSummaryError(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSummaryError(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [session.kind, retryCount])

  // Independent from the /dashboard/summary fetch above (Story 2.3, AC #3:
  // Brand Performance is an "additional section", not part of the seven-
  // field skeleton batch) — its own loading/error/retry cycle.
  useEffect(() => {
    if (session.kind !== 'authenticated') return
    let cancelled = false
    setBrandPerformanceError(false)

    apiFetch('/dashboard/brand-performance')
      .then(async (response) => {
        if (cancelled) return
        if (!response.ok) {
          setBrandPerformanceError(true)
          return
        }
        const body = (await response.json()) as BrandPerformanceSummary
        if (!cancelled) {
          setBrandPerformance(body)
          setBrandPerformanceError(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBrandPerformanceError(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [session.kind, brandPerformanceRetryCount])

  async function handleLogout() {
    setSubmitting(true)
    try {
      const response = await apiFetch('/auth/logout', { method: 'POST' })
      if (response.ok) {
        // An unauthenticated visitor always sees system preference (AC #6) —
        // don't let this account's override linger for the next visitor.
        resetPreference()
        navigate('/', { replace: true })
      }
    } catch {
      // Network failure — stay put; the button re-enables so the user can retry.
    } finally {
      setSubmitting(false)
    }
  }

  if (session.kind === 'loading') {
    return null
  }

  if (session.kind === 'unauthenticated') {
    return (
      <Navigate
        to="/"
        replace
        state={session.message ? { message: session.message } : undefined}
      />
    )
  }

  const loading = summary === null
  const freshness: FreshnessBadge = summary
    ? freshnessBadge(summary.data_as_of, summary.is_stale)
    : { status: 'neutral', icon: <AccessTimeIcon />, label: 'Loading…' }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
          Dashboard
        </Typography>
        <Button variant="outlined" disabled={submitting} onClick={handleLogout}>
          Log out
        </Button>
        <ThemeToggle />
      </Stack>

      <Box sx={{ mb: 3 }}>
        <StatusBadge status={freshness.status} icon={freshness.icon} label={freshness.label} />
      </Box>

      {summaryError && (
        <Alert
          severity="error"
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={() => setRetryCount((count) => count + 1)}>
              Retry
            </Button>
          }
        >
          Couldn't load dashboard data. Please try again.
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(4, 1fr)' },
          gap: 2,
        }}
      >
        <StatTile
          label="Today's Sales"
          value={loading ? null : formatCrBdt(summary.today_sales)}
          loading={loading}
        />
        <StatTile
          label="YTD Sales"
          value={loading ? null : formatCrBdt(summary.ytd_sales)}
          loading={loading}
        />
        <StatTile
          label="MTD Sales"
          value={loading ? null : formatCrBdt(summary.mtd_sales)}
          loading={loading}
        />
        <StatTile
          label="Achievement %"
          value={loading ? null : displayPercent(summary.achievement_pct)}
          loading={loading}
        />
        <StatTile
          label="Growth %"
          value={loading ? null : displayPercent(summary.growth_pct)}
          trend={
            !loading && summary.growth_pct !== null
              ? {
                  direction: Math.round(Number(summary.growth_pct)) >= 0 ? 'up' : 'down',
                  label: formatPercent(summary.growth_pct),
                }
              : undefined
          }
          loading={loading}
        />
        <StatTile
          label="Notification Status"
          value={
            loading ? null : (
              <StatusBadge status="neutral" icon={<NotificationsNoneIcon />} label="No sends yet" />
            )
          }
          loading={loading}
        />
        <Box sx={{ gridColumn: { xs: 'span 1', md: 'span 2' } }}>
          <StatTile
            label="Team Performance"
            loading={loading}
            value={
              loading ? null : (
                <Stack spacing={1}>
                  {summary.team_performance.map((team) => (
                    <Stack
                      key={team.team_name}
                      direction="row"
                      sx={{ justifyContent: 'space-between' }}
                    >
                      <Typography variant="body2">{team.team_name}</Typography>
                      <Typography variant="body2">{formatPercent(team.achievement_pct)}</Typography>
                    </Stack>
                  ))}
                </Stack>
              )
            }
          />
        </Box>
      </Box>

      <BrandPerformanceSection
        data={brandPerformance}
        loading={brandPerformance === null && !brandPerformanceError}
        error={brandPerformanceError}
        onRetry={() => setBrandPerformanceRetryCount((count) => count + 1)}
      />
    </Container>
  )
}

export default DashboardPage
