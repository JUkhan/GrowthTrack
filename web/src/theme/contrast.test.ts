import { describe, expect, it } from 'vitest'
import { colors } from './tokens'
import { contrastRatio } from './contrast'

// WCAG 2.1 AA normal-text floor is 4.5:1 (the 3:1 floor only applies to
// large text / non-text UI, which none of DESIGN.md's badge/button text at
// 12px/600-weight qualifies as).
const AA_FLOOR = 4.5

describe('contrastRatio', () => {
  it('computes the textbook black/white ratio of 21:1', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 0)
  })

  it('computes a ratio of 1 for identical colors', () => {
    expect(contrastRatio('#154D71', '#154D71')).toBeCloseTo(1, 5)
  })
})

describe('DESIGN.md button/status-badge pairs clear WCAG AA (4.5:1)', () => {
  it('button-primary, light mode', () => {
    expect(contrastRatio(colors.primary, colors.primaryForeground)).toBeGreaterThanOrEqual(
      AA_FLOOR,
    )
  })

  it('button-primary, dark mode', () => {
    expect(
      contrastRatio(colors.primaryDark, colors.primaryForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })

  it('button-danger / status-error, light mode', () => {
    expect(contrastRatio(colors.statusError, colors.statusErrorForeground)).toBeGreaterThanOrEqual(
      AA_FLOOR,
    )
  })

  it('button-danger / status-error, dark mode', () => {
    expect(
      contrastRatio(colors.statusErrorDark, colors.statusErrorForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })

  it('status-success badge, dark mode (accent-dark / accent-foreground-dark)', () => {
    expect(
      contrastRatio(colors.accentDark, colors.accentForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })

  it('status-warning badge, dark mode', () => {
    expect(
      contrastRatio(colors.statusWarningDark, colors.statusWarningForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })

  // The two pairs DESIGN.md's own literal frontmatter specifies do NOT clear
  // AA in light mode — confirmed by hand-computation during story research,
  // not hypothetical. createAppTheme.ts's palette.success/warning.contrastText
  // deliberately does not use these literal foregrounds; see the mitigated
  // pairs below instead.
  it('status-success badge, light mode, with the literal accent-foreground (#FFFFFF) — documented AA failure', () => {
    expect(contrastRatio(colors.accent, colors.accentForeground)).toBeLessThan(AA_FLOOR)
  })

  it('status-warning badge, light mode, with the literal status-warning-foreground (#FFFFFF) — documented AA failure', () => {
    expect(contrastRatio(colors.statusWarning, colors.statusWarningForeground)).toBeLessThan(
      AA_FLOOR,
    )
  })

  // Mitigation (Dev Notes [ASSUMPTION — CONFIRM WITH UX]): reuse DESIGN.md's
  // own already-defined *-foreground-dark tones as the light-mode
  // badge/chip foreground instead of the literal white — these are the
  // values createAppTheme.ts actually sets as contrastText.
  it('status-success badge, light mode, with the accent-foreground-dark mitigation', () => {
    expect(
      contrastRatio(colors.accent, colors.accentForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })

  it('status-warning badge, light mode, with the status-warning-foreground-dark mitigation', () => {
    expect(
      contrastRatio(colors.statusWarning, colors.statusWarningForegroundDark),
    ).toBeGreaterThanOrEqual(AA_FLOOR)
  })
})
