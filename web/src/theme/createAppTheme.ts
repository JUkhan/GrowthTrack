import { createTheme, type Theme } from '@mui/material/styles'
import { colors, rounded, typography } from './tokens'

declare module '@mui/material/styles' {
  interface TypographyVariants {
    statDisplay: React.CSSProperties
    statDisplaySm: React.CSSProperties
  }
  interface TypographyVariantsOptions {
    statDisplay?: React.CSSProperties
    statDisplaySm?: React.CSSProperties
  }
}

declare module '@mui/material/Typography' {
  interface TypographyPropsVariantOverrides {
    statDisplay: true
    statDisplaySm: true
  }
}

export function createAppTheme(mode: 'light' | 'dark'): Theme {
  const isDark = mode === 'dark'

  return createTheme({
    palette: {
      mode,
      primary: {
        main: isDark ? colors.primaryDark : colors.primary,
        contrastText: isDark ? colors.primaryForegroundDark : colors.primaryForeground,
      },
      error: {
        main: isDark ? colors.statusErrorDark : colors.statusError,
        contrastText: isDark ? colors.statusErrorForegroundDark : colors.statusErrorForeground,
      },
      // status-success = accent (DESIGN.md: status-success: '{colors.accent}') —
      // reused as MUI's built-in `success` slot, never used for buttons.
      success: {
        main: isDark ? colors.accentDark : colors.accent,
        // Both modes use accent-foreground-dark: literal white
        // (accent-foreground) fails WCAG AA (~3.75:1) against the light-mode
        // accent background, while accent-foreground-dark clears ~4.56:1
        // there AND is DESIGN.md's own correct dark-mode pairing (~8.9:1).
        // See Dev Notes / contrast.test.ts.
        contrastText: colors.accentForegroundDark,
      },
      warning: {
        main: isDark ? colors.statusWarningDark : colors.statusWarning,
        // Same reasoning as success, using status-warning-foreground-dark
        // for both modes (~4.82:1 light, ~9.3:1 dark).
        contrastText: colors.statusWarningForegroundDark,
      },
    },
    shape: {
      borderRadius: rounded.md,
    },
    typography: {
      statDisplay: typography.statDisplay,
      statDisplaySm: typography.statDisplaySm,
    },
    components: {
      // MuiPaper's flat-bordered treatment below is the default for every
      // Paper-derived surface, including Dialog/Popover/Snackbar/Drawer under
      // the hood — the four overrides here cancel the inherited border on
      // exactly the surfaces DESIGN.md reserves for shadow instead (Task 3).
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: rounded.lg,
            border: 'none',
          },
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: {
            border: 'none',
          },
        },
      },
      MuiSnackbarContent: {
        styleOverrides: {
          root: {
            border: 'none',
          },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          // Only the temporary (mobile) variant is a shadowed overlay —
          // permanent/persistent drawers stay flat-bordered like any other
          // docked surface.
          paper: ({ ownerState }) =>
            ownerState.variant === 'temporary' ? { border: 'none' } : {},
        },
      },
      MuiPaper: {
        defaultProps: {
          elevation: 0,
        },
        styleOverrides: {
          root: ({ theme }) => ({
            border: '1px solid',
            borderColor: theme.palette.divider,
          }),
        },
      },
    },
  })
}
