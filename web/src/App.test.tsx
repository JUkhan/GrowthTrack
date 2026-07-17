import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App shell', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the GrowthTrack heading', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }),
      ),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'GrowthTrack' }),
    ).toBeInTheDocument()
  })
})
