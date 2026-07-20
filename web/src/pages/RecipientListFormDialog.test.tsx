import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RecipientListFormDialog from './RecipientListFormDialog'

const OPTIONS = [{ id: 'u1', name: 'Karim' }]

describe('RecipientListFormDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a recipient list via POST /recipient-lists with the fixed kind and selected members', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: '1' }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <RecipientListFormDialog
        open
        recipientList={null}
        kind="group"
        options={OPTIONS}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/name/i), 'North Group')
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Karim' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/recipient-lists',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'North Group', kind: 'group', member_user_ids: ['u1'] }),
      }),
    )
  })

  it('shows "Add Recipient Channel" as the title when kind is channel and no list is being edited', () => {
    render(
      <RecipientListFormDialog
        open
        recipientList={null}
        kind="channel"
        options={OPTIONS}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )

    expect(screen.getByText('Add Recipient Channel')).toBeInTheDocument()
  })

  it('pre-fills name and members and PATCHes /recipient-lists/{id} when editing', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: '1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <RecipientListFormDialog
        open
        recipientList={{ id: '1', name: 'North Group', kind: 'group', memberUserIds: ['u1'] }}
        kind="group"
        options={OPTIONS}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    expect(screen.getByLabelText(/name/i)).toHaveValue('North Group')
    expect(screen.getByText('Karim')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/recipient-lists/1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ name: 'North Group', kind: 'group', member_user_ids: ['u1'] }),
        }),
      )
    })
  })

  it('shows an inline error on a 409 recipient_list_name_taken response and does not call onSaved', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'recipient_list_name_taken',
              message: 'A Recipient Group/Channel with this name already exists',
            },
          }),
          { status: 409 },
        ),
      ),
    )
    const onSaved = vi.fn()

    render(
      <RecipientListFormDialog
        open
        recipientList={null}
        kind="group"
        options={OPTIONS}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/name/i), 'North Group')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(
      await screen.findByText('A Recipient Group/Channel with this name already exists'),
    ).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })
})
