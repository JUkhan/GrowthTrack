import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TemplatesPage from './TemplatesPage'

const TEMPLATE_ROW = {
  id: 't1',
  name: 'Target Revision Notice',
  twilio_content_sid: 'HXreal123',
  variable_slots: ['team_name', 'new_target'],
  body_preview_template: '{team_name}: {new_target}',
}

function renderTemplatesPage() {
  const router = createMemoryRouter(
    [
      { path: '/notifications/templates', element: <TemplatesPage /> },
      { path: '/', element: <div>Login Placeholder</div> },
      { path: '/notifications/compose', element: <div>Compose Placeholder</div> },
    ],
    { initialEntries: ['/notifications/templates'] },
  )
  return render(<RouterProvider router={router} />)
}

function stubFetch(overrides: { meOk?: boolean; templates?: unknown[] }) {
  const { meOk = true, templates = [TEMPLATE_ROW] } = overrides
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = init?.method ?? 'GET'

      if (url === '/auth/me') {
        return Promise.resolve(new Response(null, { status: meOk ? 200 : 401 }))
      }
      if (url === '/message-templates' && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify(templates), { status: 200 }))
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

describe('TemplatesPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('redirects to / when /auth/me returns 401', async () => {
    stubFetch({ meOk: false })

    renderTemplatesPage()

    expect(await screen.findByText('Login Placeholder')).toBeInTheDocument()
  })

  it('renders every field per row from GET /message-templates', async () => {
    stubFetch({})

    renderTemplatesPage()

    expect(await screen.findByText('Target Revision Notice')).toBeInTheDocument()
    expect(screen.getByText('HXreal123')).toBeInTheDocument()
    expect(screen.getByText('team_name')).toBeInTheDocument()
    expect(screen.getByText('new_target')).toBeInTheDocument()
    expect(screen.getByText('{team_name}: {new_target}')).toBeInTheDocument()
  })

  it('renders the empty state with an Add Template action when the list is empty', async () => {
    stubFetch({ templates: [] })

    renderTemplatesPage()

    expect(await screen.findByText('No message templates yet')).toBeInTheDocument()
    const user = userEvent.setup()
    const addButtons = screen.getAllByRole('button', { name: 'Add Template' })
    expect(addButtons.length).toBeGreaterThan(0)
    await user.click(addButtons[addButtons.length - 1])

    expect(await screen.findByRole('heading', { name: 'Add Message Template' })).toBeInTheDocument()
  })

  it('does not render a Remove or Delete button anywhere in the row actions', async () => {
    stubFetch({})

    renderTemplatesPage()
    await screen.findByText('Target Revision Notice')

    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
  })

  it('opens the edit dialog pre-filled from the row', async () => {
    stubFetch({})

    renderTemplatesPage()
    await screen.findByText('Target Revision Notice')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Edit' }))

    expect(await screen.findByRole('heading', { name: 'Edit Message Template' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^name/i)).toHaveValue('Target Revision Notice')
    expect(screen.getByLabelText(/twilio content sid/i)).toHaveValue('HXreal123')
  })

  it('reloads the list after a successful save', async () => {
    stubFetch({})
    renderTemplatesPage()
    await screen.findByText('Target Revision Notice')

    const updatedRow = { ...TEMPLATE_ROW, name: 'Updated Notice' }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'
        if (url === '/auth/me') return Promise.resolve(new Response(null, { status: 200 }))
        if (url === '/message-templates' && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify([updatedRow]), { status: 200 }))
        }
        if (url === '/message-templates/t1' && method === 'PATCH') {
          return Promise.resolve(new Response(JSON.stringify(updatedRow), { status: 200 }))
        }
        return Promise.resolve(new Response(null, { status: 200 }))
      }),
    )

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await screen.findByRole('heading', { name: 'Edit Message Template' })
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Updated Notice')).toBeInTheDocument()
    })
  })
})
