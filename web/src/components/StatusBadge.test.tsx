import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CheckIcon from '@mui/icons-material/Check'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import StatusBadge from './StatusBadge'

describe('StatusBadge', () => {
  it.each(['success', 'warning', 'error', 'neutral'] as const)(
    'renders both the icon and the label together for the %s variant, never label-only',
    (status) => {
      renderWithTheme(
        <StatusBadge status={status} icon={<CheckIcon data-testid="badge-icon" />} label="Delivered" />,
      )

      expect(screen.getByText('Delivered')).toBeInTheDocument()
      expect(screen.getByTestId('badge-icon')).toBeInTheDocument()
    },
  )

  it('renders the neutral variant as MUI Chip\'s default grey', () => {
    renderWithTheme(
      <StatusBadge status="neutral" icon={<CheckIcon data-testid="badge-icon" />} label="No sends yet" />,
    )

    expect(screen.getByText('No sends yet').closest('.MuiChip-root')).toHaveClass(
      'MuiChip-colorDefault',
    )
  })
})
