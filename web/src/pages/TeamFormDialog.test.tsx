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
        team={{ id: '1', name: 'East Zone', version: 1 }}
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
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ name: 'Eastern Zone', version: 1 }),
        }),
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

  it('opens ConflictDialog showing the current values on a 409 version_conflict response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'version_conflict',
              message: 'conflict',
              details: { current: { name: 'Eastern Zone', version: 2 } },
            },
          }),
          { status: 409 },
        ),
      ),
    )

    render(
      <TeamFormDialog
        open
        team={{ id: '1', name: 'East Zone', version: 1 }}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Conflicting Changes')).toBeInTheDocument()
    expect(screen.getByText('Current: Eastern Zone')).toBeInTheDocument()
  })

  it('clicking Discard My Changes repopulates the form from current and closes ConflictDialog, leaving the edit dialog open', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'version_conflict',
              message: 'conflict',
              details: { current: { name: 'Eastern Zone', version: 2 } },
            },
          }),
          { status: 409 },
        ),
      ),
    )

    render(
      <TeamFormDialog
        open
        team={{ id: '1', name: 'East Zone', version: 1 }}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Conflicting Changes')

    await user.click(screen.getByRole('button', { name: 'Discard My Changes' }))

    await waitFor(() => {
      expect(screen.queryByText('Conflicting Changes')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Edit Sales Team' })).toBeInTheDocument()
    expect(screen.getByLabelText(/name/i)).toHaveValue('Eastern Zone')
  })

  it('clicking Keep My Changes re-PATCHes with the conflict version and calls onSaved on a subsequent 200', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: 'version_conflict',
              message: 'conflict',
              details: { current: { name: 'Eastern Zone', version: 2 } },
            },
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: '1', name: 'East Zone' }), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <TeamFormDialog
        open
        team={{ id: '1', name: 'East Zone', version: 1 }}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Conflicting Changes')

    await user.click(screen.getByRole('button', { name: 'Keep My Changes' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/teams/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'East Zone', version: 2 }),
      }),
    )
  })
})
