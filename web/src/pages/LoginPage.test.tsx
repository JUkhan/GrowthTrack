import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

function renderLoginPage() {
  const router = createMemoryRouter(
    [
      { path: '/', element: <LoginPage /> },
      { path: '/home', element: <div>Home Placeholder</div> },
    ],
    { initialEntries: ['/'] },
  )
  render(<RouterProvider router={router} />)
}

async function submitForm(username: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/username/i), username)
  await user.type(screen.getByLabelText(/password/i), password)
  await user.click(screen.getByRole('button', { name: 'Log in' }))
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
})
