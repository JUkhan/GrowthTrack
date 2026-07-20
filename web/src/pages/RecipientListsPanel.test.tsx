import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RecipientListsPanel from './RecipientListsPanel'
import type { RecipientListRow } from './RecipientListsPanel'
import type { DirectoryUser } from './RecipientsPage'

const ACTIVE_USER: DirectoryUser = {
  id: 'u1',
  name: 'Karim',
  mobile: '+8801700000601',
  username: null,
  role: 'sales_user',
  status: 'active',
  team_id: 't1',
  team_name: 'North Zone',
  version: 1,
  consent_status: 'not_opted_in',
  consent_recorded_at: null,
}

const INACTIVE_MEMBER: DirectoryUser = {
  id: 'u2',
  name: 'Rahim',
  mobile: '+8801700000602',
  username: null,
  role: 'sales_user',
  status: 'inactive',
  team_id: 't1',
  team_name: 'North Zone',
  version: 1,
  consent_status: 'not_opted_in',
  consent_recorded_at: null,
}

const GROUP_ROW: RecipientListRow = {
  id: 'rl1',
  name: 'North Group',
  kind: 'group',
  status: 'active',
  version: 1,
  member_user_ids: ['u1'],
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof RecipientListsPanel>> = {}) {
  return render(
    <RecipientListsPanel
      kind="group"
      title="Recipient Groups"
      emptyMessage="No Recipient Groups yet. Add your first Group to target a named set of Users in one selection."
      addButtonLabel="Add Recipient Group"
      recipientLists={[GROUP_ROW]}
      error={false}
      users={[ACTIVE_USER]}
      onReload={vi.fn()}
      {...overrides}
    />,
  )
}

describe('RecipientListsPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders rows from the given recipientLists filtered by kind upstream', () => {
    renderPanel()

    expect(screen.getByText('North Group')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows the empty state with the kind-specific copy when there are zero lists', () => {
    renderPanel({ recipientLists: [] })

    expect(
      screen.getByText(
        'No Recipient Groups yet. Add your first Group to target a named set of Users in one selection.',
      ),
    ).toBeInTheDocument()
  })

  it('creates a recipient list and reloads on save', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'rl2' }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const onReload = vi.fn()
    renderPanel({ onReload })
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Add Recipient Group' }))
    await user.type(screen.getByLabelText(/name/i), 'South Group')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(onReload).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/recipient-lists',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('editing a list whose member has since gone inactive still shows that member in the picker', async () => {
    renderPanel({
      recipientLists: [{ ...GROUP_ROW, member_user_ids: ['u2'] }],
      users: [ACTIVE_USER, INACTIVE_MEMBER],
    })
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Edit' }))

    expect(screen.getByText('Rahim (inactive)')).toBeInTheDocument()
  })

  it('seeds the edit dialog version from the row and PATCHes with it', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'rl1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/recipient-lists/rl1',
        expect.objectContaining({
          method: 'PATCH',
          body: expect.stringContaining(`"version":${GROUP_ROW.version}`),
        }),
      )
    })
  })

  it('shows the real member-count consequence text and calls DELETE on confirm', async () => {
    let deleteCalled = false
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === 'DELETE') {
          deleteCalled = true
          return Promise.resolve(new Response(null, { status: 204 }))
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )
    renderPanel()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Remove' }))

    expect(
      await screen.findByText(
        'This removes North Group from the directory. Future notifications will no longer reach its 1 member(s).',
      ),
    ).toBeInTheDocument()

    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(deleteCalled).toBe(true)
    })
  })
})
