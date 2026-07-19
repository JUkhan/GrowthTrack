import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import StatTile from './StatTile'

describe('StatTile', () => {
  it('renders the label and value', () => {
    renderWithTheme(<StatTile label="Today's Sales" value="1.2 Cr" />)

    expect(screen.getByText("Today's Sales")).toBeInTheDocument()
    expect(screen.getByText('1.2 Cr')).toBeInTheDocument()
  })

  it('renders no trend badge when trend is omitted', () => {
    const { container } = renderWithTheme(<StatTile label="MTD" value="42" />)

    expect(container.querySelector('.MuiChip-root')).not.toBeInTheDocument()
  })

  it('renders the trend via the badge-chip treatment, not bare text, for an upward trend', () => {
    renderWithTheme(
      <StatTile label="Growth %" value="12%" trend={{ direction: 'up', label: '+3% vs last month' }} />,
    )

    const badge = screen.getByText('+3% vs last month').closest('.MuiChip-root')
    expect(badge).not.toBeNull()
    expect(badge).toHaveClass('MuiChip-colorSuccess')
  })

  it('renders the trend via the badge-chip treatment for a downward trend, using error not warning', () => {
    renderWithTheme(
      <StatTile label="Growth %" value="-4%" trend={{ direction: 'down', label: '-4% vs last month' }} />,
    )

    const badge = screen.getByText('-4% vs last month').closest('.MuiChip-root')
    expect(badge).not.toBeNull()
    expect(badge).toHaveClass('MuiChip-colorError')
  })

  it('renders a skeleton instead of the value/trend content when loading', () => {
    const { container } = renderWithTheme(
      <StatTile
        label="Today's Sales"
        value="1.2 Cr"
        trend={{ direction: 'up', label: '+3% vs last month' }}
        loading
      />,
    )

    expect(container.querySelector('.MuiSkeleton-root')).toBeInTheDocument()
    expect(screen.queryByText('1.2 Cr')).not.toBeInTheDocument()
    expect(screen.queryByText('+3% vs last month')).not.toBeInTheDocument()
  })
})
