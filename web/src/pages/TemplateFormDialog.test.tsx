import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TemplateFormDialog from './TemplateFormDialog'

describe('TemplateFormDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a template via POST /message-templates and calls onSaved', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: '1',
          name: 'Target Revision Notice',
          twilio_content_sid: 'HXreal123',
          variable_slots: [],
          body_preview_template: 'Static body',
        }),
        { status: 201 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(<TemplateFormDialog open template={null} onClose={vi.fn()} onSaved={onSaved} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/^name/i), 'Target Revision Notice')
    await user.type(screen.getByLabelText(/twilio content sid/i), 'HXreal123')
    await user.type(screen.getByLabelText(/preview text/i), 'Static body')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/message-templates',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'Target Revision Notice',
          twilio_content_sid: 'HXreal123',
          variable_slots: [],
          body_preview_template: 'Static body',
        }),
      }),
    )
  })

  it('pre-fills every field and PATCHes /message-templates/{id} when editing an existing template', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: '1',
          name: 'Renamed Notice',
          twilio_content_sid: 'HXupdated',
          variable_slots: ['team_name'],
          body_preview_template: '{team_name}',
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <TemplateFormDialog
        open
        template={{
          id: '1',
          name: 'Target Revision Notice',
          twilioContentSid: 'HXreal123',
          variableSlots: ['team_name'],
          bodyPreviewTemplate: '{team_name}',
        }}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    expect(screen.getByLabelText(/^name/i)).toHaveValue('Target Revision Notice')
    expect(screen.getByLabelText(/twilio content sid/i)).toHaveValue('HXreal123')
    expect(screen.getByLabelText(/^slot 1/i)).toHaveValue('team_name')
    expect(screen.getByLabelText(/preview text/i)).toHaveValue('{team_name}')

    const user = userEvent.setup()
    await user.clear(screen.getByLabelText(/^name/i))
    await user.type(screen.getByLabelText(/^name/i), 'Renamed Notice')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/message-templates/1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            name: 'Renamed Notice',
            twilio_content_sid: 'HXreal123',
            variable_slots: ['team_name'],
            body_preview_template: '{team_name}',
          }),
        }),
      )
    })
  })

  it('adds and removes variable slot rows', async () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<TemplateFormDialog open template={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Add Slot' }))
    await user.type(screen.getByLabelText(/^slot 1/i), 'team_name')
    expect(screen.getByLabelText(/^slot 1/i)).toHaveValue('team_name')

    await user.click(screen.getByRole('button', { name: /remove slot 1/i }))
    expect(screen.queryByLabelText(/^slot 1/i)).not.toBeInTheDocument()
  })

  it('shows an inline error on a 409 template_name_taken response and does not call onSaved', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'template_name_taken',
              message: 'A message template with this name already exists',
            },
          }),
          { status: 409 },
        ),
      ),
    )
    const onSaved = vi.fn()

    render(<TemplateFormDialog open template={null} onClose={vi.fn()} onSaved={onSaved} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/^name/i), 'Target Revision Notice')
    await user.type(screen.getByLabelText(/twilio content sid/i), 'HXreal123')
    await user.type(screen.getByLabelText(/preview text/i), 'Static body')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(
      await screen.findByText('A message template with this name already exists'),
    ).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })
})
