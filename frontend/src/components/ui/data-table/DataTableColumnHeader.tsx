import { Column } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react"

import { cn } from "@/utils/cn"
import { Button } from "@/components/ui/Button"
// We might need a DropdownMenu here, but sticking to basics first.
// If DropdownMenu isn't available in components/ui, we'll simplify.
// Checking listed files: DropdownMenu was not in the `list_dir` output of `components/ui`.
// We will implement a simplified version for now using just click to sort.

interface DataTableColumnHeaderProps<TData, TValue> extends React.HTMLAttributes<HTMLDivElement> {
  column: Column<TData, TValue>
  title: string
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <div className={cn(className)}>{title}</div>
  }

  const sortDirection = column.getIsSorted()
  const ariaSortValue = sortDirection === "asc" ? "ascending" : sortDirection === "desc" ? "descending" : "none"

  return (
    <div className={cn("flex items-center space-x-2", className)} aria-sort={ariaSortValue}>
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
