import type { RowData } from "@tanstack/react-table"
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"

import { Button } from "@/components/ui/Button"
import { Select } from "@/components/ui/Select"
import { useTranslation } from "react-i18next"
import type { DataTableInstance } from "./dataTableFeatures"

interface DataTablePaginationProps<TData extends RowData> {
  table: DataTableInstance<TData>
}

export function DataTablePagination<TData extends RowData>({
  table,
}: DataTablePaginationProps<TData>) {
  const { t } = useTranslation(["common"])
  return (
    <div className="flex items-center justify-between px-2">
      <div className="flex-1 text-sm text-text-secondary">
        {table.getFilteredSelectedRowModel().rows.length} of{" "}
        {table.getFilteredRowModel().rows.length} row(s) selected.
      </div>
      <div className="flex items-center space-x-6 lg:space-x-8">
        <div className="flex items-center space-x-2">
          <p className="text-sm font-medium" id="data-table-pagination-pagesize-label">
            {t("common:pagination.rowsPerPage")}
          </p>
          <Select
            value={`${table.state.pagination.pageSize}`}
            onValueChange={(value) => {
              table.setPageSize(Number(value))
            }}
            options={[10, 20, 30, 40, 50].map((pageSize) => ({
              label: `${pageSize}`,
              value: `${pageSize}`,
            }))}
            className="h-8 w-20"
            // Wave 120 polish-v2 — connect the visible label via aria-labelledby
            // so the combobox button has an accessible name (axe `button-name`
            // failed on /admin/users without this).
            aria-labelledby="data-table-pagination-pagesize-label"
          />
        </div>
        <div className="flex w-24 items-center justify-center text-sm font-medium">
          Page {table.state.pagination.pageIndex + 1} of {table.getPageCount()}
        </div>
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            className="hidden h-8 w-8 p-0 lg:flex"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only">{t("common:pagination.firstPage")}</span>
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only">{t("common:pagination.prevPage")}</span>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only">{t("common:pagination.nextPage")}</span>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="hidden h-8 w-8 p-0 lg:flex"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only">{t("common:pagination.lastPage")}</span>
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
