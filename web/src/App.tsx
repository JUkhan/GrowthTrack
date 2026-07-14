import CssBaseline from '@mui/material/CssBaseline'
import Container from '@mui/material/Container'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import Typography from '@mui/material/Typography'

// App shell only — Story 1.6 applies GrowthTrack's design tokens to this theme.
const theme = createTheme()

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container maxWidth="sm" sx={{ py: 4 }}>
        <Typography variant="h4" component="h1">
          GrowthTrack
        </Typography>
      </Container>
    </ThemeProvider>
  )
}

export default App
