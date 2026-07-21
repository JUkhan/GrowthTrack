import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NotificationComposePage from './NotificationComposePage'

const USER_ROW = {
  id: 'u1',
  name: 'Karim',
  username: null,
  status: 'active',
  mobile: '+8801700000001',
}

const TEMPLATE_ROW = {
  id: 'tpl1',
  name: 'Target Revision Notice',
  variable_slots: ['team_name'],
  body_preview_template: 'Hello {team_name}',
}

function renderComposePage() {
  const router = createMemoryRouter(
    [
      { path: '/notifications/compose', element: <NotificationComposePage /> },
      { path: '/', element: <div>Login Placeholder</div> },
      { path: '/dashboard', element: <div>Dashboard Placeholder</div> },
    ],
    { initialEntries: ['/notifications/compose'] },
  )
  return render(<RouterProvider router={router} />)
}

function stubFetch(overrides: {
  meOk?: boolean
  resolveBody?: unknown
  composeResponse?: () => Promise<Response> | Response
}) {
  const {
    meOk = true,
    resolveBody = { selected_count: 1, unique_count: 1, overlap_count: 0, ineligible_count: 0 },
    composeResponse,
  } = overrides
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'

    if (url === '/auth/me') {
      return Promise.resolve(new Response(null, { status: meOk ? 200 : 401 }))
    }
    if (url === '/users') {
      return Promise.resolve(new Response(JSON.stringify([USER_ROW]), { status: 200 }))
    }
    if (url === '/teams') {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
    }
    if (url === '/recipient-lists') {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
    }
    if (url === '/message-templates') {
      return Promise.resolve(new Response(JSON.stringify([TEMPLATE_ROW]), { status: 200 }))
    }
    if (url === '/notifications/resolve-recipients') {
      return Promise.resolve(new Response(JSON.stringify(resolveBody), { status: 200 }))
    }
    if (url === '/notifications' && method === 'POST') {
      return Promise.resolve(
        composeResponse
          ? composeResponse()
          : new Response(
              JSON.stringify({ notification_id: 'n1', outcomes: [] }),
              { status: 201 },
            ),
      )
    }
    return Promise.resolve(new Response(null, { status: 200 }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function selectRecipient(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByLabelText('Recipients'))
  await user.click(await screen.findByRole('option', { name: 'Karim' }))
}

async function selectTemplate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByLabelText('Template'))
  await user.click(await screen.findByRole('option', { name: 'Target Revision Notice' }))
}

async function selectTemplateAndFillVariables(user: ReturnType<typeof userEvent.setup>) {
  await selectTemplate(user)
  await user.type(await screen.findByLabelText('team_name'), 'Team B')
}

describe('NotificationComposePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('disables Send with an inline reason when no recipients are selected', async () => {
    stubFetch({})

    renderComposePage()

    expect(await screen.findByText('Select at least one recipient')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Send to 0 recipients/ })).toBeDisabled()
  })

  it('updates the live WhatsApp preview as variable fields are typed into', async () => {
    stubFetch({})
    const user = userEvent.setup()

    renderComposePage()
    await selectTemplate(user)

    const field = await screen.findByLabelText('team_name')
    await user.type(field, 'Team B')

    expect(await screen.findByText('Hello Team B')).toBeInTheDocument()
  })

  it('keeps Send disabled while a required template variable is left blank', async () => {
    stubFetch({})
    const user = userEvent.setup()

    renderComposePage()
    await selectRecipient(user)
    await selectTemplate(user)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeDisabled()
    })

    await user.type(await screen.findByLabelText('team_name'), 'Team B')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeEnabled()
    })
  })

  it('enables Send once a recipient resolves to a positive unique count and a template is chosen', async () => {
    stubFetch({})
    const user = userEvent.setup()

    renderComposePage()
    await selectRecipient(user)
    await selectTemplateAndFillVariables(user)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeEnabled()
    })
  })

  it('shows "Sending to N recipients…" and guards against double-submit while a send is in flight', async () => {
    let resolveCompose: (() => void) | undefined
    const pending = new Promise<Response>((resolve) => {
      resolveCompose = () =>
        resolve(new Response(JSON.stringify({ notification_id: 'n1', outcomes: [] }), { status: 201 }))
    })
    const fetchMock = stubFetch({ composeResponse: () => pending })
    const user = userEvent.setup()

    renderComposePage()
    await selectRecipient(user)
    await selectTemplateAndFillVariables(user)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeEnabled()
    })

    const sendButton = screen.getByRole('button', { name: /Send to 1 recipients/ })
    await user.click(sendButton)

    expect(await screen.findByText('Sending to 1 recipients…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sending to 1 recipients/ })).toBeDisabled()

    // The button is disabled while in flight, so a second click can't fire
    // a second request — only one POST /notifications call happened.
    expect(
      fetchMock.mock.calls.filter(
        ([url, init]) => url === '/notifications' && init?.method === 'POST',
      ),
    ).toHaveLength(1)

    resolveCompose?.()
    await waitFor(() => {
      expect(screen.getByText('Dashboard Placeholder')).toBeInTheDocument()
    })
  })

  it('shows the server error message and re-enables Send when compose fails', async () => {
    stubFetch({
      composeResponse: () =>
        new Response(
          JSON.stringify({ error: { code: 'no_recipients_selected', message: 'Select at least one recipient' } }),
          { status: 422 },
        ),
    })
    const user = userEvent.setup()

    renderComposePage()
    await selectRecipient(user)
    await selectTemplateAndFillVariables(user)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeEnabled()
    })

    await user.click(screen.getByRole('button', { name: /Send to 1 recipients/ }))

    expect(await screen.findByText('Select at least one recipient', { selector: '.MuiAlert-message' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Send to 1 recipients/ })).toBeEnabled()
  })
})
