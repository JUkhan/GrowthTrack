// Transcribed verbatim from DESIGN.md's `colors`/`typography`/`rounded`
// frontmatter — the single place brand values live. If DESIGN.md's hex
// values ever change, this is the one file that needs to change to match;
// don't duplicate the literal hex strings elsewhere.

export const colors = {
  primary: '#154D71',
  primaryForeground: '#FFFFFF',
  primaryDark: '#5B9BC4',
  primaryForegroundDark: '#08202E',
  accent: '#12966B',
  accentForeground: '#FFFFFF',
  accentDark: '#34D399',
  accentForegroundDark: '#062018',
  statusWarning: '#C77700',
  statusWarningForeground: '#FFFFFF',
  statusWarningDark: '#F2B84B',
  statusWarningForegroundDark: '#2B1B00',
  statusError: '#C0362C',
  statusErrorForeground: '#FFFFFF',
  statusErrorDark: '#F1817A',
  statusErrorForegroundDark: '#2B0A07',
} as const

export const typography = {
  statDisplay: {
    fontFamily: 'Roboto',
    fontSize: '32px',
    fontWeight: 600,
    lineHeight: 1.15,
    letterSpacing: '0em',
    fontVariantNumeric: 'tabular-nums',
  },
  statDisplaySm: {
    fontFamily: 'Roboto',
    fontSize: '22px',
    fontWeight: 600,
    lineHeight: 1.2,
    fontVariantNumeric: 'tabular-nums',
  },
} as const

export const rounded = {
  sm: 4,
  md: 8,
  lg: 12,
  full: 9999,
} as const
