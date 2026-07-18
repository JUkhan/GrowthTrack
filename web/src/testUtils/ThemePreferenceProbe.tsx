import { useThemeMode } from '../theme/ThemeModeContext'

// Renders the current ThemeModeContext preference as plain text so tests
// outside the theme module itself can assert on it without reaching into
// context internals.
export function ThemePreferenceProbe() {
  const { preference } = useThemeMode()
  return <div data-testid="theme-preference">{preference}</div>
}
