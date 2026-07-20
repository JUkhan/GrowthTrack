import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RecipientsPage from './RecipientsPage'

const USER_ROW = {
  id: 'u1',
  name: 'Karim',
  mobile: '+8801700000401',
  username: null,
  role: 'sales_user',
  status: 'active',
  team_id: 't1',
  team_name: 'North Zone',
  version: 1,
  consent_status: 'opted_in',
  consent_recorded_at: '2026-07-01T10:00:00Z',
}

const TEAM_ROW = { id: 't1', name: 'North Zone', status: 'active', version: 1 }

const GROUP_ROW = {
  id: 'rl1',
  name: 'North Group',
  kind: 'group',
  status: 'active',
  version: 1,
  member_user_ids: ['u1'],
}

const CHANNEL_ROW = {
  id: 'rl2',
  name: 'North Channel',
  kind: 'channel',
  status: 'active',
  version: 1,
  member_user_ids: [],
}

function renderRecipientsPage() {
  const router = createMemoryRouter(
    [
      { path: '/recipients', element: <RecipientsPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
      { path: '/dashboard', element: <div>Dashboard Placeholder</div> },
    ],
    { initialEntries: ['/recipients'] },
  )
  return render(<RouterProvider router={router} />)
}

function stubFetch(overrides: {
  meOk?: boolean
  users?: unknown[]
  teams?: unknown[]
  recipientLists?: unknown[]
  onDeleteUser?: (id: string) => Response
}) {
  const {
    meOk = true,
    users = [USER_ROW],
    teams = [TEAM_ROW],
    recipientLists = [GROUP_ROW, CHANNEL_ROW],
    onDeleteUser,
  } = overrides
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'

      if (url === '/auth/me') {
        return Promise.resolve(new Response(null, { status: meOk ? 200 : 401 }))
      }
      if (url === '/users' && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify(users), { status: 200 }))
      }
      if (url === '/teams' && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify(teams), { status: 200 }))
      }
      if (url === '/recipient-lists' && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify(recipientLists), { status: 200 }))
      }
      if (url.startsWith('/users/') && method === 'DELETE') {
        const id = url.split('/').pop()!
        return Promise.resolve(onDeleteUser ? onDeleteUser(id) : new Response(null, { status: 204 }))
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

describe('RecipientsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('redirects to / when /auth/me returns 401', async () => {
    stubFetch({ meOk: false })

    renderRecipientsPage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('renders Users from GET /users on the Users tab by default', async () => {
    stubFetch({})

    renderRecipientsPage()

    expect(await screen.findByText('Karim')).toBeInTheDocument()
    expect(screen.getByText('+8801700000401')).toBeInTheDocument()
    expect(screen.getByText('North Zone')).toBeInTheDocument()
  })

  it('renders a Consent column badge per row from GET /users', async () => {
    stubFetch({
      users: [
        USER_ROW,
        {
          id: 'u2',
          name: 'Rahim',
          mobile: '+8801700000402',
          username: null,
          role: 'sales_user',
          status: 'active',
          team_id: 't1',
          team_name: 'North Zone',
          version: 1,
          consent_status: 'not_opted_in',
          consent_recorded_at: null,
        },
      ],
    })

    renderRecipientsPage()

    expect(await screen.findByText('Opted In')).toBeInTheDocument()
    expect(screen.getByText('Not Opted In')).toBeInTheDocument()
  })

  it('seeds the edit dialog consent fields from the row', async () => {
    stubFetch({})

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Edit' }))

    expect(await screen.findAllByText('Opted In')).not.toHaveLength(0)
  })

  it('reloads Users via onConsentChanged after a consent action without closing the dialog', async () => {
    let usersRequestCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url === '/auth/me') return Promise.resolve(new Response(null, { status: 200 }))
        if (url === '/users' && method === 'GET') {
          usersRequestCount += 1
          return Promise.resolve(new Response(JSON.stringify([USER_ROW]), { status: 200 }))
        }
        if (url === '/teams' && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify([TEAM_ROW]), { status: 200 }))
        }
        if (url === '/recipient-lists' && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
        }
        if (url === '/users/u1/opt-in-consent' && method === 'DELETE') {
          return Promise.resolve(new Response(null, { status: 204 }))
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await screen.findByRole('button', { name: 'Revoke Consent' })
    const countBeforeAction = usersRequestCount

    await user.click(screen.getByRole('button', { name: 'Revoke Consent' }))
    const confirmButtons = await screen.findAllByRole('button', { name: 'Revoke' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(usersRequestCount).toBeGreaterThan(countBeforeAction)
    })
    expect(screen.getByText('Edit User')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('shows the empty state with a primary action when there are zero Users', async () => {
    stubFetch({ users: [] })

    renderRecipientsPage()

    expect(
      await screen.findByText(
        'No Users yet. Add your first Sales User or Manager to start building the notification directory.',
      ),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Add User' }).length).toBeGreaterThan(0)
  })

  it('switches to the Sales Teams tab and renders teams from GET /teams', async () => {
    stubFetch({})

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Sales Teams' }))

    expect(await screen.findByText('North Zone')).toBeInTheDocument()
  })

  it('does not show an Edit button for an Administrator row', async () => {
    stubFetch({
      users: [
        {
          id: 'admin-1',
          name: null,
          mobile: null,
          username: 'admin',
          role: 'administrator',
          status: 'active',
          team_id: null,
          team_name: null,
          version: 1,
        },
      ],
    })

    renderRecipientsPage()

    await screen.findByText('admin')
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })

  it('confirms and removes a User via the ConfirmationDialog naming the real consequence', async () => {
    let deleteCalled = false
    stubFetch({
      onDeleteUser: () => {
        deleteCalled = true
        return new Response(null, { status: 204 })
      },
    })

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Remove' }))

    expect(
      await screen.findByText(
        'This removes Karim from the directory. Future notifications will no longer reach them.',
      ),
    ).toBeInTheDocument()

    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(deleteCalled).toBe(true)
    })
  })

  it('shows an inline error when removing the sole active Administrator returns 409', async () => {
    stubFetch({
      users: [
        {
          id: 'admin-1',
          name: null,
          mobile: null,
          username: 'admin',
          role: 'administrator',
          status: 'active',
          team_id: null,
          team_name: null,
          version: 1,
        },
      ],
      onDeleteUser: () =>
        new Response(
          JSON.stringify({
            error: {
              code: 'last_administrator',
              message: 'The last remaining Administrator account cannot be deleted or deactivated',
            },
          }),
          { status: 409 },
        ),
    })

    renderRecipientsPage()
    await screen.findByText('admin')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    expect(
      await screen.findByText(
        'The last remaining Administrator account cannot be deleted or deactivated',
      ),
    ).toBeInTheDocument()
  })

  it('switches to the Recipient Groups tab and renders only group-kind lists from GET /recipient-lists', async () => {
    stubFetch({})

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Recipient Groups' }))

    expect(await screen.findByText('North Group')).toBeInTheDocument()
    expect(screen.queryByText('North Channel')).not.toBeInTheDocument()
  })

  it('switches to the Recipient Channels tab and renders only channel-kind lists from GET /recipient-lists', async () => {
    stubFetch({})

    renderRecipientsPage()
    await screen.findByText('Karim')
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Recipient Channels' }))

    expect(await screen.findByText('North Channel')).toBeInTheDocument()
    expect(screen.queryByText('North Group')).not.toBeInTheDocument()
  })

  it('clears actionError when switching into the Recipient Groups tab', async () => {
    stubFetch({
      onDeleteUser: () =>
        new Response(
          JSON.stringify({ error: { code: 'last_administrator', message: 'Cannot remove' } }),
          { status: 409 },
        ),
      users: [
        {
          id: 'admin-1',
          name: null,
          mobile: null,
          username: 'admin',
          role: 'administrator',
          status: 'active',
          team_id: null,
          team_name: null,
          version: 1,
        },
      ],
    })

    renderRecipientsPage()
    await screen.findByText('admin')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' })
    await user.click(confirmButtons[confirmButtons.length - 1])
    expect(await screen.findByText('Cannot remove')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'Recipient Groups' }))

    expect(screen.queryByText('Cannot remove')).not.toBeInTheDocument()
  })
})
