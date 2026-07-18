import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('renders the passed message and action label', () => {
    renderWithTheme(
      <EmptyState message="No recipients yet." actionLabel="Add recipient" onAction={() => {}} />,
    )

    expect(screen.getByText('No recipients yet.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add recipient' })).toBeInTheDocument()
  })

  it('calls onAction when the action button is clicked', async () => {
    const onAction = vi.fn()
    const user = userEvent.setup()
    renderWithTheme(
      <EmptyState message="No recipients yet." actionLabel="Add recipient" onAction={onAction} />,
    )

    await user.click(screen.getByRole('button', { name: 'Add recipient' }))

    expect(onAction).toHaveBeenCalledTimes(1)
  })
})
