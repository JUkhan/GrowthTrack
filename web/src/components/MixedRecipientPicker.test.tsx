import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MixedRecipientPicker from './MixedRecipientPicker'
import type { RecipientEntry } from './MixedRecipientPicker'

const OPTIONS: RecipientEntry[] = [
  { id: 'u1', name: 'Karim', type: 'user' },
  { id: 't1', name: 'Team B', type: 'team' },
  { id: 'rl1', name: 'North Group', type: 'recipient_list' },
]

function stubResolveRecipients(body: {
  selected_count: number
  unique_count: number
  overlap_count: number
  ineligible_count: number
}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/notifications/resolve-recipients') {
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    }),
  )
}

describe('MixedRecipientPicker', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('calls onChange with the newly selected option when picking from the combined options list', async () => {
    const onChange = vi.fn()
    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[]}
        onChange={onChange}
        onResolvedChange={vi.fn()}
      />,
    )
    const user = userEvent.setup()

    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Team B' }))

    expect(onChange).toHaveBeenCalledWith([{ id: 't1', name: 'Team B', type: 'team' }])
  })

  it('calls onChange without the entry when removing an already-selected chip', async () => {
    const onChange = vi.fn()
    stubResolveRecipients({
      selected_count: 1,
      unique_count: 1,
      overlap_count: 0,
      ineligible_count: 0,
    })
    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[{ id: 'u1', name: 'Karim', type: 'user' }]}
        onChange={onChange}
        onResolvedChange={vi.fn()}
      />,
    )
    const user = userEvent.setup()

    const karimChip = screen.getByText('Karim').closest('.MuiChip-root') as HTMLElement
    await user.click(within(karimChip).getByTestId('CancelIcon'))

    expect(onChange).toHaveBeenCalledWith([])
  })

  it('calls onResolvedChange(null) and renders no dedupe note when nothing is selected', () => {
    const onResolvedChange = vi.fn()
    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[]}
        onChange={vi.fn()}
        onResolvedChange={onResolvedChange}
      />,
    )

    expect(onResolvedChange).toHaveBeenCalledWith(null)
    expect(screen.queryByText(/selected →/)).not.toBeInTheDocument()
  })

  it('fetches resolve-recipients when the selection changes and renders the dedupe note', async () => {
    stubResolveRecipients({
      selected_count: 14,
      unique_count: 11,
      overlap_count: 3,
      ineligible_count: 0,
    })
    const onResolvedChange = vi.fn()

    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[{ id: 't1', name: 'Team B', type: 'team' }]}
        onChange={vi.fn()}
        onResolvedChange={onResolvedChange}
      />,
    )

    expect(
      await screen.findByText('14 selected → 11 unique recipients (3 overlaps merged)'),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(onResolvedChange).toHaveBeenCalledWith({
        selectedCount: 14,
        uniqueCount: 11,
        overlapCount: 3,
        ineligibleCount: 0,
      })
    })
  })

  it('surfaces ineligible_count separately from overlap_count in the dedupe note', async () => {
    stubResolveRecipients({
      selected_count: 5,
      unique_count: 3,
      overlap_count: 1,
      ineligible_count: 1,
    })

    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[{ id: 'u1', name: 'Karim', type: 'user' }]}
        onChange={vi.fn()}
        onResolvedChange={vi.fn()}
      />,
    )

    expect(
      await screen.findByText(
        '5 selected → 3 unique recipients (1 overlaps merged, 1 inactive or not opted in)',
      ),
    ).toBeInTheDocument()
  })

  it('sends the selection split by type in the resolve-recipients request body', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/notifications/resolve-recipients') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              selected_count: 2,
              unique_count: 2,
              overlap_count: 0,
              ineligible_count: 0,
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.resolve(new Response(null, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MixedRecipientPicker
        options={OPTIONS}
        selected={[
          { id: 'u1', name: 'Karim', type: 'user' },
          { id: 'rl1', name: 'North Group', type: 'recipient_list' },
        ]}
        onChange={vi.fn()}
        onResolvedChange={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/notifications/resolve-recipients',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            user_ids: ['u1'],
            team_ids: [],
            recipient_list_ids: ['rl1'],
          }),
        }),
      )
    })
  })
})
