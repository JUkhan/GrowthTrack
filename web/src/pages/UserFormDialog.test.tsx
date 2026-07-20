import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import UserFormDialog from './UserFormDialog'

const TEAMS = [{ id: 'team-1', name: 'North Zone' }]

function stubFetch(handlers: Partial<Record<string, () => Response>>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      const key = Object.keys(handlers).find((k) => url.startsWith(k))
      if (key) {
        return Promise.resolve(handlers[key]!())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

async function fillAndOpenTeam(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/name/i), 'Karim')
  await user.type(screen.getByLabelText(/mobile/i), '+8801700000301')
  await user.click(screen.getByLabelText(/team/i))
  await user.click(await screen.findByRole('option', { name: 'North Zone' }))
}

describe('UserFormDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a user via POST /users with the selected role and team', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: '1' }), { status: 201 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <UserFormDialog open user={null} teams={TEAMS} onClose={vi.fn()} onSaved={onSaved} />,
    )
    const user = userEvent.setup()
    await fillAndOpenTeam(user)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/users',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'Karim',
          mobile: '+8801700000301',
          role: 'sales_user',
          team_id: 'team-1',
        }),
      }),
    )
  })

  it('never renders Administrator as a Role option', async () => {
    render(
      <UserFormDialog open user={null} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()

    await user.click(screen.getByRole('combobox', { name: /role/i }))

    const options = await screen.findAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['Sales User', 'Manager'])
  })

  it('omits the Role field entirely in edit mode and PATCHes without it', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'u1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <UserFormDialog
        open
        user={{ id: 'u1', name: 'Karim', mobile: '+8801700000302', role: 'sales_user', teamId: 'team-1' }}
        teams={TEAMS}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )

    expect(screen.queryByRole('combobox', { name: /role/i })).not.toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/users/u1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            name: 'Karim',
            mobile: '+8801700000302',
            team_id: 'team-1',
          }),
        }),
      )
    })
  })

  it('shows an inline error and disables Save when the mobile-availability check reports unavailable', async () => {
    stubFetch({
      '/users/mobile-availability': () =>
        new Response(JSON.stringify({ available: false }), { status: 200 }),
    })

    render(
      <UserFormDialog open user={null} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/mobile/i), '+8801700000303')
    await user.tab()

    expect(
      await screen.findByText('This mobile number is already in use'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('does not flag the mobile as unavailable when the check reports available', async () => {
    stubFetch({
      '/users/mobile-availability': () =>
        new Response(JSON.stringify({ available: true }), { status: 200 }),
    })

    render(
      <UserFormDialog open user={null} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/mobile/i), '+8801700000304')
    await user.tab()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled()
    })
    expect(screen.queryByText('This mobile number is already in use')).not.toBeInTheDocument()
  })
})
