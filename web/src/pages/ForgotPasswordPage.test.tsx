import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ForgotPasswordPage from './ForgotPasswordPage'

function renderForgotPasswordPage() {
  const router = createMemoryRouter(
    [
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
    ],
    { initialEntries: ['/forgot-password'] },
  )
  render(<RouterProvider router={router} />)
}

async function submitForm(username: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/username/i), username)
  await user.click(screen.getByRole('button', { name: 'Send reset instructions' }))
}

const CONFIRMATION_TEXT =
  'If an account with that username exists, password reset instructions have been generated.'

describe('ForgotPasswordPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the generic confirmation for a real, existing account (token issued server-side)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: CONFIRMATION_TEXT }), { status: 200 }),
      ),
    )

    renderForgotPasswordPage()
    await submitForm('admin')

    expect(await screen.findByText(CONFIRMATION_TEXT)).toBeInTheDocument()
  })

  it('shows the same generic confirmation for a username that does not exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: CONFIRMATION_TEXT }), { status: 200 }),
      ),
    )

    renderForgotPasswordPage()
    await submitForm('a-username-that-does-not-exist')

    expect(await screen.findByText(CONFIRMATION_TEXT)).toBeInTheDocument()
  })

  it('shows a generic error and no confirmation when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderForgotPasswordPage()
    await submitForm('admin')

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText(CONFIRMATION_TEXT)).not.toBeInTheDocument()
  })

  it('has a link back to the login page', () => {
    vi.stubGlobal('fetch', vi.fn())

    renderForgotPasswordPage()

    expect(screen.getByRole('link', { name: 'Back to login' })).toHaveAttribute('href', '/')
  })
})
