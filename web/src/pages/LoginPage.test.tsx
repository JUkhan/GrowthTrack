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

describe('LoginPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('navigates to /home on a successful login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: '1', username: 'admin', role: 'administrator' }), {
          status: 200,
        }),
      ),
    )

    renderLoginPage()
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'invalid_credentials', message: 'Invalid username or password' },
          }),
          { status: 401 },
        ),
      ),
    )

    renderLoginPage()
    await submitForm('admin', 'wrong-password')

    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'GrowthTrack' })).toBeInTheDocument()
  })

  it('shows a generic error and does not navigate when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderLoginPage()
    await submitForm('admin', 'correct-horse-battery-staple')

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
  })
})
