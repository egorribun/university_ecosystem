import type { RowData } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react"

import { cn } from "@/utils/cn"
import { Button } from "@/components/ui/Button"
import type { DataTableColumn } from "./dataTableFeatures"
// We might need a DropdownMenu here, but sticking to basics first.
// If DropdownMenu isn't available in components/ui, we'll simplify.
// Checking listed files: DropdownMenu was not in the `list_dir` output of `components/ui`.
// We will implement a simplified version for now using just click to sort.

interface DataTableColumnHeaderProps<
  TData extends RowData,
  TValue,
> extends React.HTMLAttributes<HTMLDivElement> {
  column: DataTableColumn<TData, TValue>
  title: string
}

export function DataTableColumnHeader<TData extends RowData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <div className={cn(className)}>{title}</div>
  }

  const sortDirection = column.getIsSorted()

  // Wave 120 polish-v2 — `aria-sort` moved to the parent `<TableHead>`
  // (`<th>`) in DataTable.tsx where it's valid per ARIA spec. Setting it on
  // an inner `<div>` triggered axe `aria-allowed-attr` (only allowed on
  // `<th>` or elements with role="columnheader"/"rowheader"). Button's
  // aria-label below still announces sort state to screen readers.
  return (
    <div className={cn("flex items-center space-x-2", className)}>
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 data-[state=open]:bg-accent"
        onClick={() => column.toggleSorting(sortDirection === "asc")}
        aria-label={`${title}, ${sortDirection === "asc" ? "sorted ascending" : sortDirection === "desc" ? "sorted descending" : "not sorted"}`}
      >
        <span>{title}</span>
        {sortDirection === "desc" ? (
          <ArrowDown className="ml-2 h-4 w-4" aria-hidden="true" />
        ) : sortDirection === "asc" ? (
          <ArrowUp className="ml-2 h-4 w-4" aria-hidden="true" />
        ) : (
          <ChevronsUpDown className="ml-2 h-4 w-4" aria-hidden="true" />
        )}
      </Button>
    </div>
  )
}
