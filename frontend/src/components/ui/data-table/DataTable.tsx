import * as React from "react"
import { useTranslation } from "react-i18next"
import {
  ColumnFiltersState,
  ColumnVisibilityState,
  RowData,
  SortingState,
  flexRender,
  useTable,
} from "@tanstack/react-table"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DataTablePagination } from "./DataTablePagination"
import { dataTableFeatures, type DataTableColumnDef } from "./dataTableFeatures"

export interface DataTableProps<TData extends RowData> {
  columns: DataTableColumnDef<TData>[]
  data: TData[]
}

function DataTableInner<TData extends RowData>({ columns, data }: DataTableProps<TData>) {
  const { t } = useTranslation()
  const [rowSelection, setRowSelection] = React.useState({})
  const [columnVisibility, setColumnVisibility] = React.useState<ColumnVisibilityState>({})
  // Use a zero-argument Array factory for the initial collections. It keeps
  // the state updater compatible with TanStack's `OnChangeFn` while avoiding
  // a mutable module-level default shared between table instances.
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(Array.of())
  const [sorting, setSorting] = React.useState<SortingState>(Array.of())

  const table = useTable({
    features: dataTableFeatures,
    data,
    columns,
    state: {
      sorting,
      columnVisibility,
      rowSelection,
      columnFilters,
    },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
  })
  const rows = table.getRowModel().rows

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-border-subtle bg-surface">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  // Wave 120 polish-v2 — `aria-sort` belongs on the
                  // `<th>` (TableHead) per ARIA spec, NOT the inner div.
                  // axe-core `aria-allowed-attr` flagged the prior placement
                  // on /admin/users. Compute here from column sort state.
                  const canSort = header.column.getCanSort()
                  const sortDir = header.column.getIsSorted()
                  const ariaSort = !canSort
                    ? undefined
                    : sortDir === "asc"
                      ? "ascending"
                      : sortDir === "desc"
                        ? "descending"
                        : "none"
                  return (
                    <TableHead key={header.id} colSpan={header.colSpan} aria-sort={ariaSort}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.length ? (
              rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() ? "selected" : undefined}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  {t("common:noResults")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <DataTablePagination table={table} />
    </div>
  )
}

export const DataTable = React.memo(DataTableInner) as <TData extends RowData>(
  props: DataTableProps<TData>
) => React.ReactElement

export default DataTable
