import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithTheme } from '../testUtils/renderWithTheme'
import ResponsiveDataTable, { type DataTableColumn } from './ResponsiveDataTable'

interface Row {
  id: string
  name: string
  status: string
}

const rows: Row[] = [
  { id: '1', name: 'Dr. Rahman', status: 'Delivered' },
  { id: '2', name: 'Dr. Karim', status: 'Failed' },
]

const columns: DataTableColumn<Row>[] = [
  { key: 'name', header: 'Name', render: (row) => row.name, sortable: true },
  { key: 'status', header: 'Status', render: (row) => row.status },
]

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })),
  )
}

describe('ResponsiveDataTable', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders as a table at default/desktop width', () => {
    stubMatchMedia(false)

    renderWithTheme(
      <ResponsiveDataTable columns={columns} rows={rows} getRowKey={(row) => row.id} />,
    )

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
  })

  it('renders as stacked cards when the viewport is below sm', () => {
    stubMatchMedia(true)

    renderWithTheme(
      <ResponsiveDataTable columns={columns} rows={rows} getRowKey={(row) => row.id} />,
    )

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getAllByText('Name')).toHaveLength(rows.length)
  })

  it('renders the toolbar above the table/card block unconditionally', () => {
    stubMatchMedia(false)

    renderWithTheme(
      <ResponsiveDataTable
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.id}
        toolbar={<div>Filter toolbar</div>}
      />,
    )

    expect(screen.getByText('Filter toolbar')).toBeInTheDocument()
  })

  it('wires sortable columns to onSortChange', async () => {
    stubMatchMedia(false)
    const onSortChange = vi.fn()

    renderWithTheme(
      <ResponsiveDataTable
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.id}
        onSortChange={onSortChange}
      />,
    )

    screen.getByRole('button', { name: 'Name' }).click()

    expect(onSortChange).toHaveBeenCalledWith('name')
  })
})
