import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TableSortLabel from '@mui/material/TableSortLabel'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'

export interface DataTableColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  sortable?: boolean
}

export interface ResponsiveDataTableProps<T> {
  columns: DataTableColumn<T>[]
  rows: T[]
  getRowKey: (row: T) => string
  sortColumn?: string
  sortDirection?: 'asc' | 'desc'
  onSortChange?: (columnKey: string) => void
  toolbar?: ReactNode
}

// Shared `data-table-row` shell (AC #8) — a generic, presentational surface
// only. No filter/pagination/sort-state wiring: each consumer (Notification
// History, Recipients, Audit Log) owns that against its own real API once
// it exists (Epic 2/3/5), not guessed at here.
function ResponsiveDataTable<T>({
  columns,
  rows,
  getRowKey,
  sortColumn,
  sortDirection,
  onSortChange,
  toolbar,
}: ResponsiveDataTableProps<T>) {
  const theme = useTheme()
  const isStacked = useMediaQuery(theme.breakpoints.down('sm'))

  return (
    <Box>
      {toolbar && <Box sx={{ mb: 2 }}>{toolbar}</Box>}
      {isStacked ? (
        <Stack spacing={2}>
          {rows.map((row) => (
            <Card key={getRowKey(row)} sx={{ p: 2 }}>
              <Stack spacing={1}>
                {columns.map((column) => (
                  <Box key={column.key}>
                    <Typography variant="caption" color="text.secondary">
                      {column.header}
                    </Typography>
                    <Box>{column.render(row)}</Box>
                  </Box>
                ))}
              </Stack>
            </Card>
          ))}
        </Stack>
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell key={column.key}>
                  {column.sortable ? (
                    <TableSortLabel
                      active={sortColumn === column.key}
                      direction={sortColumn === column.key ? (sortDirection ?? 'asc') : 'asc'}
                      onClick={() => onSortChange?.(column.key)}
                    >
                      {column.header}
                    </TableSortLabel>
                  ) : (
                    column.header
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={getRowKey(row)} hover>
                {columns.map((column) => (
                  <TableCell key={column.key}>{column.render(row)}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  )
}

export default ResponsiveDataTable
