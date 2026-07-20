import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import RecipientPicker from './RecipientPicker'

const OPTIONS = [
  { id: 'u1', name: 'Karim' },
  { id: 'u2', name: 'Rahim' },
]

describe('RecipientPicker', () => {
  it('renders the selected members and a "N selected" caption', () => {
    render(<RecipientPicker options={OPTIONS} selectedIds={['u1']} onChange={vi.fn()} />)

    expect(screen.getByText('Karim')).toBeInTheDocument()
    expect(screen.getByText('1 selected')).toBeInTheDocument()
  })

  it('shows "0 selected" when nothing is selected', () => {
    render(<RecipientPicker options={OPTIONS} selectedIds={[]} onChange={vi.fn()} />)

    expect(screen.getByText('0 selected')).toBeInTheDocument()
  })

  it('calls onChange with the newly selected id when picking an option', async () => {
    const onChange = vi.fn()
    render(<RecipientPicker options={OPTIONS} selectedIds={[]} onChange={onChange} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Karim' }))

    expect(onChange).toHaveBeenCalledWith(['u1'])
  })

  it('calls onChange without the id when removing an already-selected member', async () => {
    const onChange = vi.fn()
    render(<RecipientPicker options={OPTIONS} selectedIds={['u1', 'u2']} onChange={onChange} />)
    const user = userEvent.setup()

    const karimChip = screen.getByText('Karim').closest('.MuiChip-root') as HTMLElement
    await user.click(within(karimChip).getByTestId('CancelIcon'))

    expect(onChange).toHaveBeenCalledWith(['u2'])
  })
})
