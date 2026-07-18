import type { FormEvent, ReactNode } from 'react'
import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import Typography from '@mui/material/Typography'

interface AuthFormShellProps {
  heading: string
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  children: ReactNode
}

function AuthFormShell({ heading, onSubmit, children }: AuthFormShellProps) {
  return (
    <Container maxWidth="xs" sx={{ py: 8 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        {heading}
      </Typography>
      <Box
        component="form"
        onSubmit={onSubmit}
        noValidate
        sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
      >
        {children}
      </Box>
    </Container>
  )
}

export default AuthFormShell
