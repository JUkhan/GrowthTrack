import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TeamFormDialog from './TeamFormDialog'

describe('TeamFormDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a team via POST /teams and calls onSaved', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: '1', name: 'East Zone' }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={onSaved} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/name/i), 'East Zone')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/teams',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'East Zone' }) }),
    )
  })

  it('pre-fills the name and PATCHes /teams/{id} when editing an existing team', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: '1', name: 'Eastern Zone' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <TeamFormDialog
        open
        team={{ id: '1', name: 'East Zone' }}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    expect(screen.getByLabelText(/name/i)).toHaveValue('East Zone')

    const user = userEvent.setup()
    await user.clear(screen.getByLabelText(/name/i))
    await user.type(screen.getByLabelText(/name/i), 'Eastern Zone')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/teams/1',
        expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'Eastern Zone' }) }),
      )
    })
  })

  it('shows an inline error on a 409 team_name_taken response and does not call onSaved', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'team_name_taken', message: 'A Sales Team with this name already exists' },
          }),
          { status: 409 },
        ),
      ),
    )
    const onSaved = vi.fn()

    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={onSaved} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/name/i), 'East Zone')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(
      await screen.findByText('A Sales Team with this name already exists'),
    ).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })
})
