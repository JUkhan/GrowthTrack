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
        user={{
          id: 'u1',
          name: 'Karim',
          mobile: '+8801700000302',
          role: 'sales_user',
          teamId: 'team-1',
          version: 1,
          consentStatus: 'not_opted_in',
          consentRecordedAt: null,
        }}
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
            version: 1,
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

  const OPTED_IN_USER = {
    id: 'u1',
    name: 'Karim',
    mobile: '+8801700000305',
    role: 'sales_user' as const,
    teamId: 'team-1',
    version: 1,
    consentStatus: 'opted_in' as const,
    consentRecordedAt: '2026-07-01T10:00:00Z',
  }

  const NOT_OPTED_IN_USER = {
    ...OPTED_IN_USER,
    consentStatus: 'not_opted_in' as const,
    consentRecordedAt: null,
  }

  it('renders "Opted In" with a formatted timestamp for an opted-in user', async () => {
    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )

    expect(await screen.findByText('Opted In')).toBeInTheDocument()
    expect(
      screen.getByText(new Date(OPTED_IN_USER.consentRecordedAt).toLocaleString()),
    ).toBeInTheDocument()
  })

  it('renders "Not Opted In" with no timestamp for a not-opted-in user', async () => {
    render(
      <UserFormDialog
        open
        user={NOT_OPTED_IN_USER}
        teams={TEAMS}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )

    expect(await screen.findByText('Not Opted In')).toBeInTheDocument()
    expect(screen.queryByText('Opted In')).not.toBeInTheDocument()
  })

  it('omits the Consent section entirely in create mode', () => {
    render(
      <UserFormDialog open user={null} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )

    expect(screen.queryByText('Consent')).not.toBeInTheDocument()
    expect(screen.queryByText('Opted In')).not.toBeInTheDocument()
    expect(screen.queryByText('Not Opted In')).not.toBeInTheDocument()
  })

  it('clicking Record Consent POSTs and flips the badge without closing the dialog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ user_id: 'u1', granted_at: '2026-07-20T12:00:00Z' }), {
        status: 201,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <UserFormDialog
        open
        user={NOT_OPTED_IN_USER}
        teams={TEAMS}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Record Consent' }))

    await waitFor(() => {
      expect(screen.getByText('Opted In')).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/users/u1/opt-in-consent',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('clicking Revoke Consent opens the ConfirmationDialog naming the real consequence, DELETEs on confirm, and flips the badge', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Revoke Consent' }))

    expect(
      await screen.findByText('This immediately stops all future WhatsApp notifications to Karim.'),
    ).toBeInTheDocument()

    const confirmButtons = screen.getAllByRole('button', { name: 'Revoke' })
    await user.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(screen.getByText('Not Opted In')).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/users/u1/opt-in-consent',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('shows the mobile-change notice only for an opted-in user with an edited mobile value', async () => {
    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    const mobileField = screen.getByLabelText(/mobile/i)
    await user.clear(mobileField)
    await user.type(mobileField, '+8801700000399')

    expect(
      await screen.findByText(/Saving this number will revoke Karim's existing WhatsApp consent/),
    ).toBeInTheDocument()
  })

  it('does not show the mobile-change notice for a not-opted-in user even with an edited mobile value', async () => {
    render(
      <UserFormDialog
        open
        user={NOT_OPTED_IN_USER}
        teams={TEAMS}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    const mobileField = screen.getByLabelText(/mobile/i)
    await user.clear(mobileField)
    await user.type(mobileField, '+8801700000399')

    expect(
      screen.queryByText(/Saving this number will revoke/),
    ).not.toBeInTheDocument()
  })

  const CONFLICT_CURRENT = {
    name: 'Karim Updated',
    mobile: '+8801700000399',
    team_id: 'team-1',
    team_name: 'North Zone',
    version: 2,
  }

  it('opens ConflictDialog with the current values on a 409 version_conflict response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'version_conflict',
            message: 'conflict',
            details: { current: CONFLICT_CURRENT },
          },
        }),
        { status: 409 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Conflicting Changes')).toBeInTheDocument()
    expect(screen.getByText('Current: Karim Updated')).toBeInTheDocument()
    expect(screen.getByText('Current: +8801700000399')).toBeInTheDocument()
    expect(screen.getByText('Current: North Zone')).toBeInTheDocument()
  })

  it('clicking Discard My Changes repopulates the form and closes ConflictDialog, leaving the edit dialog open', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'version_conflict',
            message: 'conflict',
            details: { current: CONFLICT_CURRENT },
          },
        }),
        { status: 409 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Conflicting Changes')

    await user.click(screen.getByRole('button', { name: 'Discard My Changes' }))

    await waitFor(() => {
      expect(screen.queryByText('Conflicting Changes')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Edit User' })).toBeInTheDocument()
    expect(screen.getByLabelText(/name/i)).toHaveValue('Karim Updated')
    expect(screen.getByLabelText(/mobile/i)).toHaveValue('+8801700000399')
  })

  it('clicking Keep My Changes re-PATCHes with the conflict version and calls onSaved on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: 'version_conflict',
              message: 'conflict',
              details: { current: CONFLICT_CURRENT },
            },
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'u1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <UserFormDialog open user={OPTED_IN_USER} teams={TEAMS} onClose={vi.fn()} onSaved={onSaved} />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Conflicting Changes')

    await user.click(screen.getByRole('button', { name: 'Keep My Changes' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/users/u1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          name: 'Karim',
          mobile: '+8801700000305',
          team_id: 'team-1',
          version: 2,
        }),
      }),
    )
  })
})
