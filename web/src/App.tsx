import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { createAppTheme } from './theme/createAppTheme'
import { ThemeModeProvider, useThemeMode } from './theme/ThemeModeContext'

function ThemedApp() {
  const { mode } = useThemeMode()
  const theme = createAppTheme(mode)

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <RouterProvider router={router} />
    </ThemeProvider>
  )
}

function App() {
  return (
    <ThemeModeProvider>
      <ThemedApp />
    </ThemeModeProvider>
  )
}

export default App
