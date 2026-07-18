import { useState } from 'react'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Button from '@mui/material/Button'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import ConfirmationDialog from './ConfirmationDialog'

function Harness({ danger = false, onConfirm = () => {} }: { danger?: boolean; onConfirm?: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>Delete recipient</Button>
      <ConfirmationDialog
        open={open}
        title="Remove Dr. Rahman"
        consequence="This removes Dr. Rahman's territory assignment. Sales reps in Chattogram North will stop seeing this entry."
        confirmLabel="Remove"
        danger={danger}
        onConfirm={onConfirm}
        onCancel={() => setOpen(false)}
      />
    </>
  )
}

describe('ConfirmationDialog', () => {
  it('renders the consequence text verbatim', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness />)

    await user.click(screen.getByRole('button', { name: 'Delete recipient' }))

    expect(
      screen.getByText(
        "This removes Dr. Rahman's territory assignment. Sales reps in Chattogram North will stop seeing this entry.",
      ),
    ).toBeInTheDocument()
  })

  it('renders the confirm button as color="error" only when danger is true', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness danger />)

    await user.click(screen.getByRole('button', { name: 'Delete recipient' }))

    expect(screen.getByRole('button', { name: 'Remove' })).toHaveClass('MuiButton-colorError')
  })

  it('does not use color="error" on the confirm button when danger is false', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness />)

    await user.click(screen.getByRole('button', { name: 'Delete recipient' }))

    expect(screen.getByRole('button', { name: 'Remove' })).not.toHaveClass('MuiButton-colorError')
  })

  it('returns focus to the trigger button after the dialog closes', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness />)

    const trigger = screen.getByRole('button', { name: 'Delete recipient' })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => {
      expect(trigger).toHaveFocus()
    })
  })
})
