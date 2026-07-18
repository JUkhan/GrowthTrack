import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResetPasswordPage from './ResetPasswordPage'

function renderResetPasswordPage(search = '?token=a-raw-reset-token') {
  const router = createMemoryRouter(
    [
      { path: '/reset-password', element: <ResetPasswordPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
    ],
    { initialEntries: [`/reset-password${search}`] },
  )
  render(<RouterProvider router={router} />)
  return router
}

async function submitForm(newPassword: string, confirmPassword: string) {
  const user = userEvent.setup()
  // /^new password/i (not /confirm/) so it doesn't also match "Confirm new password".
  await user.type(screen.getByLabelText(/^new password/i), newPassword)
  await user.type(screen.getByLabelText(/confirm new password/i), confirmPassword)
  await user.click(screen.getByRole('button', { name: 'Reset password' }))
}

describe('ResetPasswordPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the token from the URL and submits it with the new password', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    renderResetPasswordPage('?token=my-raw-token')
    await submitForm('brand-new-password-1', 'brand-new-password-1')

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/auth/reset-password',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ token: 'my-raw-token', new_password: 'brand-new-password-1' }),
        }),
      )
    })
  })

  it('navigates to / with a success router-state message on a successful reset', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    renderResetPasswordPage()
    await submitForm('brand-new-password-1', 'brand-new-password-1')

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('shows a generic error and does not navigate on an invalid_reset_token response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'invalid_reset_token',
              message: 'This reset link is invalid or has expired.',
            },
          }),
          { status: 400 },
        ),
      ),
    )

    renderResetPasswordPage()
    await submitForm('brand-new-password-1', 'brand-new-password-1')

    expect(
      await screen.findByText('This reset link is invalid or has expired.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Login Placeholder')).not.toBeInTheDocument()
  })

  it('shows a client-side error and does not call the API when the passwords do not match', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    renderResetPasswordPage()
    await submitForm('brand-new-password-1', 'a-different-password')

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
