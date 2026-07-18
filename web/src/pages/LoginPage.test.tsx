import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'
import { ThemeModeProvider } from '../theme/ThemeModeContext'
import { ThemePreferenceProbe } from '../testUtils/ThemePreferenceProbe'

function renderLoginPage(state?: { message: string }) {
  const router = createMemoryRouter(
    [
      { path: '/', element: <LoginPage /> },
      { path: '/home', element: <div>Home Placeholder</div> },
    ],
    { initialEntries: [state ? { pathname: '/', state } : '/'] },
  )
  render(
    <ThemeModeProvider>
      <ThemePreferenceProbe />
      <RouterProvider router={router} />
    </ThemeModeProvider>,
  )
}

async function submitForm(username: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/username/i), username)
  await user.type(screen.getByLabelText(/password/i), password)
  await user.click(screen.getByRole('button', { name: 'Log in' }))
}

function accountLockedResponse(retryAfterSeconds: number) {
  return new Response(
    JSON.stringify({
      error: {
        code: 'account_locked',
        message: 'Too many failed login attempts. Try again later.',
        details: { retry_after_seconds: retryAfterSeconds },
      },
    }),
    { status: 401 },
  )
}

function stubFetch(loginResponse: () => Response, bootstrapRequired = false) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/bootstrap-status') {
        return Promise.resolve(
          new Response(JSON.stringify({ bootstrap_required: bootstrapRequired }), { status: 200 }),
        )
      }
      return Promise.resolve(loginResponse())
    }),
  )
}

describe('LoginPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('navigates to /home on a successful login', async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify({ id: '1', username: 'admin', role: 'administrator' }), {
          status: 200,
        }),
    )

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    await submitForm('admin', 'correct-horse-battery-staple')

    await waitFor(() => {
      expect(screen.getByText('Home Placeholder')).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      '/auth/login',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
  })

  it('shows the inline error message on a 401 and does not navigate', async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify({
            error: { code: 'invalid_credentials', message: 'Invalid username or password' },
          }),
          { status: 401 },
        ),
    )

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    await submitForm('admin', 'wrong-password')

    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'GrowthTrack' })).toBeInTheDocument()
  })

  it('shows a generic error and does not navigate when the request itself fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/bootstrap-status') {
          return Promise.resolve(
            new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }),
          )
        }
        return Promise.reject(new TypeError('Failed to fetch'))
      }),
    )

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    await submitForm('admin', 'correct-horse-battery-staple')

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
  })

  it('renders the bootstrap form instead of the login form when bootstrap is required', async () => {
    stubFetch(() => new Response(null, { status: 200 }), true)

    renderLoginPage()

    expect(
      await screen.findByRole('heading', { name: 'Create the first Administrator account' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'GrowthTrack' })).not.toBeInTheDocument()
  })

  it('shows a warning alert with the router-state message when present', async () => {
    stubFetch(() => new Response(null, { status: 200 }))

    renderLoginPage({ message: 'Your account has been deactivated. Contact an administrator.' })
    await screen.findByRole('heading', { name: 'GrowthTrack' })

    expect(
      await screen.findByText('Your account has been deactivated. Contact an administrator.'),
    ).toBeInTheDocument()
  })

  it('shows no warning alert when there is no router-state message', async () => {
    stubFetch(() => new Response(null, { status: 200 }))

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the lockout cooldown alert and disables the submit button on an account_locked response', async () => {
    stubFetch(() => accountLockedResponse(42))

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    await submitForm('admin', 'wrong-password')

    expect(
      await screen.findByText('Too many failed attempts. Try again in 42s.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log in' })).toBeDisabled()
  })

  it('counts down the displayed lockout timer after each second', async () => {
    stubFetch(() => accountLockedResponse(3))

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    await submitForm('admin', 'wrong-password')

    expect(await screen.findByText('Too many failed attempts. Try again in 3s.')).toBeInTheDocument()

    await waitFor(
      () => {
        expect(
          screen.getByText('Too many failed attempts. Try again in 2s.'),
        ).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })

  it('has a link to the forgot-password page', async () => {
    stubFetch(() => new Response(null, { status: 200 }))

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })

    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
  })

  it('syncs the theme preference from the login response immediately, without a reload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/bootstrap-status') {
          return Promise.resolve(
            new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }),
          )
        }
        if (url === '/auth/login' && init?.method === 'POST') {
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
        // ThemeModeProvider's own mount-time /auth/me — unauthenticated, pre-login.
        return Promise.resolve(new Response(null, { status: 401 }))
      }),
    )

    renderLoginPage()
    await screen.findByRole('heading', { name: 'GrowthTrack' })
    expect(screen.getByTestId('theme-preference')).toHaveTextContent('system')

    await submitForm('admin', 'correct-horse-battery-staple')

    await waitFor(() => {
      expect(screen.getByTestId('theme-preference')).toHaveTextContent('dark')
    })
  })
})
