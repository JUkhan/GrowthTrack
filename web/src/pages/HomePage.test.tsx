import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import HomePage from './HomePage'
import LoginPage from './LoginPage'
import { ThemeModeProvider } from '../theme/ThemeModeContext'
import { ThemePreferenceProbe } from '../testUtils/ThemePreferenceProbe'

function renderHomePage() {
  const router = createMemoryRouter(
    [
      { path: '/home', element: <HomePage /> },
      { path: '/', element: <div>Login Placeholder</div> },
    ],
    { initialEntries: ['/home'] },
  )
  render(
    <ThemeModeProvider>
      <ThemePreferenceProbe />
      <RouterProvider router={router} />
    </ThemeModeProvider>,
  )
}

function renderHomePageWithRealLoginPage() {
  const router = createMemoryRouter(
    [
      { path: '/home', element: <HomePage /> },
      { path: '/', element: <LoginPage /> },
    ],
    { initialEntries: ['/home'] },
  )
  render(
    <ThemeModeProvider>
      <RouterProvider router={router} />
    </ThemeModeProvider>,
  )
}

describe('HomePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the placeholder when /auth/me succeeds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))

    renderHomePage()

    expect(await screen.findByRole('heading', { name: 'Logged in' })).toBeInTheDocument()
  })

  it('redirects to / when /auth/me returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))

    renderHomePage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('redirects to / when the /auth/me request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderHomePage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('clicking Log out calls POST /auth/logout and navigates to /', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/logout') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHomePage()
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Logged in' })

    await user.click(screen.getByRole('button', { name: 'Log out' }))

    await waitFor(() => {
      expect(screen.getByText('Login Placeholder')).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('renders the theme toggle and clicking Dark issues a PATCH /auth/me with the new preference', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/me' && init?.method === 'PATCH') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: '1',
              username: 'admin',
              role: 'administrator',
              theme_preference: 'dark',
            }),
            { status: 200 },
          ),
        )
      }
      if (url === '/auth/me') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: '1',
              username: 'admin',
              role: 'administrator',
              theme_preference: 'system',
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHomePage()
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Logged in' })

    await user.click(screen.getByRole('button', { name: 'Dark theme' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/auth/me',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ theme_preference: 'dark' }),
        }),
      )
    })
  })

  it('resets the theme preference to system on logout', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/logout') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url === '/auth/me') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: '1',
              username: 'admin',
              role: 'administrator',
              theme_preference: 'dark',
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHomePage()
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Logged in' })
    await waitFor(() => {
      expect(screen.getByTestId('theme-preference')).toHaveTextContent('dark')
    })

    await user.click(screen.getByRole('button', { name: 'Log out' }))

    await waitFor(() => {
      expect(screen.getByTestId('theme-preference')).toHaveTextContent('system')
    })
  })

  it('reverts the toggle when the PATCH /auth/me request fails outright (network error)', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/me' && init?.method === 'PATCH') {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      if (url === '/auth/me') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: '1',
              username: 'admin',
              role: 'administrator',
              theme_preference: 'system',
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHomePage()
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Logged in' })

    await user.click(screen.getByRole('button', { name: 'Dark theme' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'System theme' })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
    })
    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('relays an account_deactivated message to the Login route, which displays it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/me') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                error: {
                  code: 'account_deactivated',
                  message: 'Your account has been deactivated. Contact an administrator.',
                },
              }),
              { status: 401 },
            ),
          )
        }
        if (url === '/auth/bootstrap-status') {
          return Promise.resolve(
            new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }),
          )
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    renderHomePageWithRealLoginPage()

    expect(
      await screen.findByText('Your account has been deactivated. Contact an administrator.'),
    ).toBeInTheDocument()
  })
})
