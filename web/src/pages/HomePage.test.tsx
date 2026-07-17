import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import HomePage from './HomePage'

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
})
