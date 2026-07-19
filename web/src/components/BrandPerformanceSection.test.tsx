import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import BrandPerformanceSection from './BrandPerformanceSection'
import type { BrandPerformanceSummary } from './BrandPerformanceSection'

function summary(overrides: Partial<BrandPerformanceSummary> = {}): BrandPerformanceSummary {
  return {
    top_brands: [
      { external_brand_id: 'B1', brand_name: 'Acme', sales: '50000000.00', rank: 1, growth_pct: '2.50' },
    ],
    low_performing_brands: [
      {
        external_brand_id: 'B2',
        brand_name: 'Beta Corp',
        sales: '1000000.00',
        rank: 10,
        growth_pct: '-3.75',
      },
    ],
    focus_brands: [
      {
        external_brand_id: 'B3',
        brand_name: 'Gamma Ltd',
        sales: '2000000.00',
        rank: 5,
        growth_pct: '-1.25',
      },
    ],
    ...overrides,
  }
}

describe('BrandPerformanceSection', () => {
  it('renders the three section headings', () => {
    renderWithTheme(
      <BrandPerformanceSection data={summary()} loading={false} error={false} onRetry={vi.fn()} />,
    )

    expect(screen.getByText('Top Brands')).toBeInTheDocument()
    expect(screen.getByText('Low-Performing Brands')).toBeInTheDocument()
    expect(screen.getByText('Focus Brands')).toBeInTheDocument()
  })

  it('renders skeletons in all three sections while loading', () => {
    const { container } = renderWithTheme(
      <BrandPerformanceSection data={null} loading error={false} onRetry={vi.fn()} />,
    )

    expect(container.querySelectorAll('.MuiSkeleton-root')).toHaveLength(15) // 5 rows x 3 sections
    expect(screen.queryByText('Acme')).not.toBeInTheDocument()
  })

  it('renders Brand Name, Sales, Rank, and Growth for each resolved entry', () => {
    renderWithTheme(
      <BrandPerformanceSection data={summary()} loading={false} error={false} onRetry={vi.fn()} />,
    )

    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('5.0 Cr')).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('3%')).toBeInTheDocument() // formatPercent('2.50')

    expect(screen.getByText('Beta Corp')).toBeInTheDocument()
    expect(screen.getByText('#10')).toBeInTheDocument()
    expect(screen.getByText('-4%')).toBeInTheDocument() // formatPercent('-3.75')
  })

  it('pairs positive growth with a success badge and negative growth with an error badge', () => {
    renderWithTheme(
      <BrandPerformanceSection data={summary()} loading={false} error={false} onRetry={vi.fn()} />,
    )

    const upBadge = screen.getByText('3%').closest('.MuiChip-root')
    expect(upBadge).toHaveClass('MuiChip-colorSuccess')

    const downBadge = screen.getByText('-4%').closest('.MuiChip-root')
    expect(downBadge).toHaveClass('MuiChip-colorError')
  })

  it('renders "No brands classified yet" with no action button for an empty list', () => {
    renderWithTheme(
      <BrandPerformanceSection
        data={summary({ focus_brands: [] })}
        loading={false}
        error={false}
        onRetry={vi.fn()}
      />,
    )

    const copies = screen.getAllByText('No brands classified yet')
    expect(copies).toHaveLength(1) // only focus_brands is empty
    expect(screen.queryByRole('button', { name: /add|create/i })).not.toBeInTheDocument()
  })

  it('renders an error Alert with a Retry button, and clicking it calls onRetry', async () => {
    const onRetry = vi.fn()
    renderWithTheme(
      <BrandPerformanceSection data={null} loading={false} error onRetry={onRetry} />,
    )

    expect(
      screen.getByText("Couldn't load brand performance data. Please try again."),
    ).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(onRetry).toHaveBeenCalledOnce()
  })
})
