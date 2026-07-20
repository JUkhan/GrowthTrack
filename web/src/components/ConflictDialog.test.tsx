import { useState } from 'react'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Button from '@mui/material/Button'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import ConflictDialog from './ConflictDialog'
import type { ConflictField } from './ConflictDialog'

const FIELDS: ConflictField[] = [
  { label: 'Name', mine: 'My Name', theirs: 'Their Name' },
  { label: 'Mobile', mine: '+1 555', theirs: '+1 999' },
]

function Harness({
  submitting = false,
  onKeepMine = () => {},
  onDiscardMine = () => {},
}: {
  submitting?: boolean
  onKeepMine?: () => void
  onDiscardMine?: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>Trigger Conflict</Button>
      <ConflictDialog
        open={open}
        entityLabel="User"
        fields={FIELDS}
        submitting={submitting}
        onKeepMine={onKeepMine}
        onDiscardMine={onDiscardMine}
      />
    </>
  )
}

describe('ConflictDialog', () => {
  it('renders both mine and theirs values for every field', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness />)

    await user.click(screen.getByRole('button', { name: 'Trigger Conflict' }))

    expect(screen.getByText('Yours: My Name')).toBeInTheDocument()
    expect(screen.getByText('Current: Their Name')).toBeInTheDocument()
    expect(screen.getByText('Yours: +1 555')).toBeInTheDocument()
    expect(screen.getByText('Current: +1 999')).toBeInTheDocument()
  })

  it('calls onDiscardMine when Discard My Changes is clicked', async () => {
    const user = userEvent.setup()
    const onDiscardMine = vi.fn()
    renderWithTheme(<Harness onDiscardMine={onDiscardMine} />)

    await user.click(screen.getByRole('button', { name: 'Trigger Conflict' }))
    await user.click(screen.getByRole('button', { name: 'Discard My Changes' }))

    expect(onDiscardMine).toHaveBeenCalledOnce()
  })

  it('calls onKeepMine when Keep My Changes is clicked', async () => {
    const user = userEvent.setup()
    const onKeepMine = vi.fn()
    renderWithTheme(<Harness onKeepMine={onKeepMine} />)

    await user.click(screen.getByRole('button', { name: 'Trigger Conflict' }))
    await user.click(screen.getByRole('button', { name: 'Keep My Changes' }))

    expect(onKeepMine).toHaveBeenCalledOnce()
  })

  it('disables both buttons while submitting is true', async () => {
    const user = userEvent.setup()
    renderWithTheme(<Harness submitting />)

    await user.click(screen.getByRole('button', { name: 'Trigger Conflict' }))

    expect(screen.getByRole('button', { name: 'Discard My Changes' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Keep My Changes' })).toBeDisabled()
  })
})
