// Shared money/percentage formatting — the Dashboard (Story 2.2) and the
// Daily Report (Story 4.2) must never disagree on these figures, so the
// formatting logic lives in one place rather than being duplicated later.

export function formatCrBdt(amount: string): string {
  const value = Number(amount)
  if (Number.isNaN(value)) return '—'
  return `${(value / 1e7).toFixed(1)} Cr`
}

export function formatPercent(pct: string): string {
  const value = Number(pct)
  if (Number.isNaN(value)) return '—'
  return `${Math.round(value)}%`
}
