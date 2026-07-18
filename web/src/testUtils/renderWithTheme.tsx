import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { createAppTheme } from '../theme/createAppTheme'

export function renderWithTheme(
  ui: ReactElement,
  mode: 'light' | 'dark' = 'light',
): RenderResult {
  return render(
    <ThemeProvider theme={createAppTheme(mode)}>
      <CssBaseline />
      {ui}
    </ThemeProvider>,
  )
}
