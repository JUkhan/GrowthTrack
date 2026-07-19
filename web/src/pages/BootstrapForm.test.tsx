import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BootstrapForm from './BootstrapForm'

function renderBootstrapForm(onAdministratorExists: () => void = vi.fn()) {
  const router = createMemoryRouter(
    [
      { path: '/', element: <BootstrapForm onAdministratorExists={onAdministratorExists} /> },
      { path: '/dashboard', element: <div>Home Placeholder</div> },
    ],
    { initialEntries: ['/'] },
  )
  render(<RouterProvider router={router} />)
}

async function submitForm(username: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/username/i), username)
  await user.type(screen.getByLabelText(/password/i), password)
  await user.click(screen.getByRole('button', { name: 'Create account' }))
}

describe('BootstrapForm', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('navigates to /dashboard on a successful bootstrap', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: '1', username: 'admin', role: 'administrator' }), {
          status: 200,
        }),
      ),
    )

    renderBootstrapForm()
    await submitForm('admin', 'correct-horse-battery-staple')

    await waitFor(() => {
      expect(screen.getByText('Home Placeholder')).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      '/auth/bootstrap',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
  })

  it('shows the inline error message on a 409 and does not navigate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'administrator_exists',
              message: 'An Administrator account already exists',
            },
          }),
          { status: 409 },
        ),
      ),
    )

    renderBootstrapForm()
    await submitForm('admin', 'correct-horse-battery-staple')

    expect(
      await screen.findByText('An Administrator account already exists'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
  })

  it('offers a back-to-login link on a 409 that calls onAdministratorExists', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'administrator_exists',
              message: 'An Administrator account already exists',
            },
          }),
          { status: 409 },
        ),
      ),
    )
    const onAdministratorExists = vi.fn()

    renderBootstrapForm(onAdministratorExists)
    await submitForm('admin', 'correct-horse-battery-staple')

    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Back to login' }))

    expect(onAdministratorExists).toHaveBeenCalledTimes(1)
  })

  it('shows a generic error and does not navigate when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderBootstrapForm()
    await submitForm('admin', 'correct-horse-battery-staple')

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText('Home Placeholder')).not.toBeInTheDocument()
  })
})
