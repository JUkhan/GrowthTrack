import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DashboardPage from './DashboardPage'
import LoginPage from './LoginPage'
import { ThemeModeProvider } from '../theme/ThemeModeContext'
import { ThemePreferenceProbe } from '../testUtils/ThemePreferenceProbe'

function renderDashboardPage() {
  const router = createMemoryRouter(
    [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
    ],
    { initialEntries: ['/dashboard'] },
  )
  return render(
    <ThemeModeProvider>
      <ThemePreferenceProbe />
      <RouterProvider router={router} />
    </ThemeModeProvider>,
  )
}

function renderDashboardPageWithRealLoginPage() {
  const router = createMemoryRouter(
    [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/', element: <LoginPage /> },
    ],
    { initialEntries: ['/dashboard'] },
  )
  return render(
    <ThemeModeProvider>
      <RouterProvider router={router} />
    </ThemeModeProvider>,
  )
}

function summaryBody(overrides: Record<string, unknown> = {}) {
  return {
    today_sales: '1000000.00',
    ytd_sales: '50000000.00',
    mtd_sales: '12000000.00',
    achievement_pct: '95.00',
    growth_pct: '3.00',
    team_performance: [{ team_name: 'North', achievement_pct: '95.00' }],
    data_as_of: '2026-07-19T08:00:00Z',
    is_stale: false,
    ...overrides,
  }
}

// Default empty-lists response for /dashboard/brand-performance — an
// independent fetch from /dashboard/summary (Story 2.3). Every mock below
// stubs it explicitly (rather than relying on a null-body 200 catch-all)
// so it resolves deterministically to "loaded, empty" instead of an error
// state that would collide with summary-fetch error/skeleton assertions.
function brandPerformanceResponse(): Response {
  return new Response(
    JSON.stringify({ top_brands: [], low_performing_brands: [], focus_brands: [] }),
    { status: 200 },
  )
}

function stubFetch(summaryResponse: () => Response, meOk = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/me') {
        return Promise.resolve(new Response(meOk ? null : null, { status: meOk ? 200 : 401 }))
      }
      if (url === '/dashboard/summary') {
        return Promise.resolve(summaryResponse())
      }
      if (url === '/dashboard/brand-performance') {
        return Promise.resolve(brandPerformanceResponse())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

describe('DashboardPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('redirects to / when /auth/me returns 401', async () => {
    stubFetch(() => new Response(JSON.stringify(summaryBody()), { status: 200 }), false)

    renderDashboardPage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('redirects to / when the /auth/me request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderDashboardPage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('shows 7 skeleton tiles while /dashboard/summary is pending', async () => {
    let resolvePending: (() => void) | undefined
    const pending = new Promise<Response>((resolve) => {
      resolvePending = () =>
        resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/me') {
          return Promise.resolve(new Response(null, { status: 200 }))
        }
        if (url === '/dashboard/summary') {
          return pending
        }
        if (url === '/dashboard/brand-performance') {
          return Promise.resolve(brandPerformanceResponse())
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    const { container } = renderDashboardPage()

    await waitFor(() => {
      expect(container.querySelectorAll('.MuiSkeleton-root')).toHaveLength(7)
    })

    resolvePending?.()
  })

  it('renders all seven fields once the response resolves', async () => {
    stubFetch(() => new Response(JSON.stringify(summaryBody()), { status: 200 }))

    renderDashboardPage()

    expect(await screen.findByText('0.1 Cr')).toBeInTheDocument() // today_sales 1,000,000 / 1e7
    expect(screen.getByText("Today's Sales")).toBeInTheDocument()
    expect(screen.getByText('5.0 Cr')).toBeInTheDocument() // ytd_sales
    expect(screen.getByText('1.2 Cr')).toBeInTheDocument() // mtd_sales
    expect(screen.getByText('YTD Sales')).toBeInTheDocument()
    expect(screen.getByText('MTD Sales')).toBeInTheDocument()
    expect(screen.getAllByText('95%').length).toBeGreaterThan(0) // Achievement % and team row
    expect(screen.getAllByText('3%').length).toBeGreaterThan(0) // Growth % value + trend badge label
    expect(screen.getByText('Notification Status')).toBeInTheDocument()
    expect(screen.getByText('No sends yet')).toBeInTheDocument()
    expect(screen.getByText('Team Performance')).toBeInTheDocument()
    expect(screen.getByText('North')).toBeInTheDocument()
  })

  it('renders the down/error trend for small negative growth that rounds to 0%, not the up/success trend', async () => {
    stubFetch(
      () => new Response(JSON.stringify(summaryBody({ growth_pct: '-0.4' })), { status: 200 }),
    )

    renderDashboardPage()

    const badge = await screen.findByText('0%', { selector: '.MuiChip-label' })
    expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError')
  })

  it('renders the warning-styled freshness badge with the stale copy when is_stale is true', async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify(summaryBody({ is_stale: true })), { status: 200 }),
    )

    renderDashboardPage()

    const badge = await screen.findByText(/source refresh delayed/)
    expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorWarning')
  })

  it('renders the neutral freshness badge when is_stale is false', async () => {
    stubFetch(
      () => new Response(JSON.stringify(summaryBody({ is_stale: false })), { status: 200 }),
    )

    renderDashboardPage()

    const badge = await screen.findByText(/Data as of .* Asia\/Dhaka/)
    expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorDefault')
  })

  it('always shows "No sends yet" for Notification Status regardless of the mocked response', async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify(summaryBody({ team_performance: [] })),
          { status: 200 },
        ),
    )

    renderDashboardPage()

    expect(await screen.findByText('No sends yet')).toBeInTheDocument()
  })

  it('renders "—" for Achievement % and Growth % when the API returns null (fresh company DB)', async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify(summaryBody({ achievement_pct: null, growth_pct: null })),
          { status: 200 },
        ),
    )

    const { container } = renderDashboardPage()

    await screen.findByText('Dashboard')
    await waitFor(() => {
      expect(container.querySelectorAll('.MuiSkeleton-root')).toHaveLength(0)
    })
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('renders the Team Performance tile with no rows when team_performance is an empty array', async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify(summaryBody({ team_performance: [] })), { status: 200 }),
    )

    renderDashboardPage()

    expect(await screen.findByText('Team Performance')).toBeInTheDocument()
    expect(screen.queryByText('North')).not.toBeInTheDocument()
  })

  it('shows an error banner with a Retry button when /dashboard/summary fails, and Retry refetches successfully', async () => {
    let summaryCallCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/me') {
          return Promise.resolve(new Response(null, { status: 200 }))
        }
        if (url === '/dashboard/summary') {
          summaryCallCount += 1
          if (summaryCallCount === 1) {
            return Promise.resolve(new Response(null, { status: 500 }))
          }
          return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
        }
        if (url === '/dashboard/brand-performance') {
          return Promise.resolve(brandPerformanceResponse())
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    const { container } = renderDashboardPage()
    const user = userEvent.setup()

    expect(
      await screen.findByText("Couldn't load dashboard data. Please try again."),
    ).toBeInTheDocument()
    // Tiles must not stay stuck on skeletons once the error is known — an
    // error banner alongside "still loading" tiles is a contradictory state.
    expect(container.querySelectorAll('.MuiSkeleton-root')).toHaveLength(0)
    expect(await screen.findByText('Unable to load')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(
        screen.queryByText("Couldn't load dashboard data. Please try again."),
      ).not.toBeInTheDocument()
    })
    expect(await screen.findByText('North')).toBeInTheDocument()
  })

  it('clicking Log out calls POST /auth/logout and navigates to /', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/auth/logout') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url === '/dashboard/summary') {
        return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
      }
      if (url === '/dashboard/brand-performance') {
        return Promise.resolve(brandPerformanceResponse())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderDashboardPage()
    const user = userEvent.setup()
    await screen.findByText('Dashboard')

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
      if (url === '/dashboard/summary') {
        return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
      }
      if (url === '/dashboard/brand-performance') {
        return Promise.resolve(brandPerformanceResponse())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderDashboardPage()
    const user = userEvent.setup()
    await screen.findByText('Dashboard')

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
      if (url === '/dashboard/summary') {
        return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
      }
      if (url === '/dashboard/brand-performance') {
        return Promise.resolve(brandPerformanceResponse())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderDashboardPage()
    const user = userEvent.setup()
    await screen.findByText('Dashboard')

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
      if (url === '/dashboard/summary') {
        return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
      }
      if (url === '/dashboard/brand-performance') {
        return Promise.resolve(brandPerformanceResponse())
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderDashboardPage()
    const user = userEvent.setup()
    await screen.findByText('Dashboard')
    await waitFor(() => {
      expect(screen.getByTestId('theme-preference')).toHaveTextContent('dark')
    })

    await user.click(screen.getByRole('button', { name: 'Log out' }))

    await waitFor(() => {
      expect(screen.getByTestId('theme-preference')).toHaveTextContent('system')
    })
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

    renderDashboardPageWithRealLoginPage()

    expect(
      await screen.findByText('Your account has been deactivated. Contact an administrator.'),
    ).toBeInTheDocument()
  })

  it('renders the Brand Performance section below the seven-field grid once /dashboard/brand-performance resolves', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/me') {
          return Promise.resolve(new Response(null, { status: 200 }))
        }
        if (url === '/dashboard/summary') {
          return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
        }
        if (url === '/dashboard/brand-performance') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                top_brands: [
                  {
                    external_brand_id: 'B1',
                    brand_name: 'Acme',
                    sales: '5000000.00',
                    rank: 1,
                    growth_pct: '2.00',
                  },
                ],
                low_performing_brands: [],
                focus_brands: [],
              }),
              { status: 200 },
            ),
          )
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    renderDashboardPage()

    expect(await screen.findByText('Brand Performance')).toBeInTheDocument()
    expect(await screen.findByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('Team Performance')).toBeInTheDocument() // seven-field grid still present
  })

  it('shows the Brand Performance section\'s own error state when /dashboard/brand-performance fails, without affecting the seven-field tiles', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/auth/me') {
          return Promise.resolve(new Response(null, { status: 200 }))
        }
        if (url === '/dashboard/summary') {
          return Promise.resolve(new Response(JSON.stringify(summaryBody()), { status: 200 }))
        }
        if (url === '/dashboard/brand-performance') {
          return Promise.resolve(new Response(null, { status: 500 }))
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    renderDashboardPage()

    expect(
      await screen.findByText("Couldn't load brand performance data. Please try again."),
    ).toBeInTheDocument()
    // The seven-field grid resolved successfully and is unaffected.
    expect(await screen.findByText('North')).toBeInTheDocument()
    expect(
      screen.queryByText("Couldn't load dashboard data. Please try again."),
    ).not.toBeInTheDocument()
  })
})
