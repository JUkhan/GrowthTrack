import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import HomePage from './HomePage'
import LoginPage from './LoginPage'

function renderHomePage() {
  const router = createMemoryRouter(
    [
      { path: '/home', element: <HomePage /> },
      { path: '/', element: <div>Login Placeholder</div> },
    ],
    { initialEntries: ['/home'] },
  )
  render(<RouterProvider router={router} />)
}

function renderHomePageWithRealLoginPage() {
  const router = createMemoryRouter(
    [
      { path: '/home', element: <HomePage /> },
      { path: '/', element: <LoginPage /> },
    ],
    { initialEntries: ['/home'] },
  )
  render(<RouterProvider router={router} />)
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
