import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsPage from './SettingsPage'

const SCHEDULE = {
  send_hour: 7,
  send_minute: 0,
  updated_at: '2026-07-23T01:00:00+00:00',
  updated_by_user_id: null,
}

function renderSettingsPage() {
  const router = createMemoryRouter(
    [
      { path: '/settings', element: <SettingsPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
      { path: '/dashboard', element: <div>Dashboard Placeholder</div> },
    ],
    { initialEntries: ['/settings'] },
  )
  return render(<RouterProvider router={router} />)
}

function stubFetch(overrides: {
  meOk?: boolean
  schedule?: unknown
  getOk?: boolean
  patchStatus?: number
  patchBody?: unknown
}) {
  const {
    meOk = true,
    schedule = SCHEDULE,
    getOk = true,
    patchStatus = 200,
    patchBody = SCHEDULE,
  } = overrides
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'

      if (url === '/auth/me') {
        return Promise.resolve(new Response(null, { status: meOk ? 200 : 401 }))
      }
      if (url === '/settings/report-schedule' && method === 'GET') {
        return Promise.resolve(
          new Response(getOk ? JSON.stringify(schedule) : null, { status: getOk ? 200 : 500 }),
        )
      }
      if (url === '/settings/report-schedule' && method === 'PATCH') {
        return Promise.resolve(
          new Response(JSON.stringify(patchBody), { status: patchStatus }),
        )
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

describe('SettingsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('redirects to / when /auth/me returns 401', async () => {
    stubFetch({ meOk: false })

    renderSettingsPage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('renders the fetched send time', async () => {
    stubFetch({})

    renderSettingsPage()

    await waitFor(() => {
      expect(screen.getByLabelText(/send time/i)).toHaveValue('07:00')
    })
  })

  it('shows an inline error when the schedule fails to load', async () => {
    stubFetch({ getOk: false })

    renderSettingsPage()

    expect(
      await screen.findByText("Couldn't load the Daily Report schedule. Please try again."),
    ).toBeInTheDocument()
  })

  it('saves an edited time and shows the success snackbar', async () => {
    stubFetch({ patchBody: { ...SCHEDULE, send_hour: 8, send_minute: 30 } })

    renderSettingsPage()
    await waitFor(() => {
      expect(screen.getByLabelText(/send time/i)).toHaveValue('07:00')
    })

    // userEvent.type doesn't drive a segmented type="time" input the way a
    // real browser does — fireEvent.change sets the value directly, same
    // effect as a user picking 08:30 in the native time widget.
    const input = screen.getByLabelText(/send time/i)
    fireEvent.change(input, { target: { value: '08:30' } })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Schedule updated')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByLabelText(/send time/i)).toHaveValue('08:30')
    })
  })

  it('renders an inline error Alert when the save request fails', async () => {
    stubFetch({ patchStatus: 422, patchBody: { error: { message: 'Invalid schedule' } } })

    renderSettingsPage()
    await waitFor(() => {
      expect(screen.getByLabelText(/send time/i)).toHaveValue('07:00')
    })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Invalid schedule')).toBeInTheDocument()
  })
})
