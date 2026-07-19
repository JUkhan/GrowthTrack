// Shared money/percentage formatting — the Dashboard (Story 2.2) and the
// Daily Report (Story 4.2) must never disagree on these figures, so the
// formatting logic lives in one place rather than being duplicated later.

export function formatCrBdt(amount: string): string {
  const crores = Number(amount) / 1e7
  return `${crores.toFixed(1)} Cr`
}

export function formatPercent(pct: string): string {
  return `${Math.round(Number(pct))}%`
}
