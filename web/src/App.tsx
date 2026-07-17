import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'

// App shell only — Story 1.6 applies GrowthTrack's design tokens to this theme.
const theme = createTheme()

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <RouterProvider router={router} />
    </ThemeProvider>
  )
}

export default App
