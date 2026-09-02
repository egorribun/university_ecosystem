import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DataTablePagination } from "./DataTablePagination"
import type { DataTableInstance } from "./dataTableFeatures"

type TestRow = Record<string, never>

function makeTable(): DataTableInstance<TestRow> {
  return {
    getFilteredSelectedRowModel: () => ({ rows: [{}] }),
    getFilteredRowModel: () => ({ rows: [{}, {}, {}, {}] }),
    state: { pagination: { pageIndex: 1, pageSize: 20 } },
    getPageCount: () => 3,
    getCanPreviousPage: () => true,
    getCanNextPage: () => true,
    setPageSize: vi.fn(),
    setPageIndex: vi.fn(),
    previousPage: vi.fn(),
    nextPage: vi.fn(),
  } as unknown as DataTableInstance<TestRow>
}

describe("DataTablePagination", () => {
  it("changes page size and dispatches all navigation actions", async () => {
    const user = userEvent.setup()
    const table = makeTable()
    render(<DataTablePagination table={table} />)

    expect(screen.getByText(/1 of 4 row\(s\) selected/)).toBeInTheDocument()
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument()

    await user.click(screen.getByRole("combobox"))
    await user.click(screen.getByRole("option", { name: "50" }))

    const buttons = screen.getAllByRole("button")
    expect(buttons).toHaveLength(4)
    for (const button of buttons) await user.click(button)

    expect(table.setPageSize).toHaveBeenCalledWith(50)
    expect(table.setPageIndex).toHaveBeenNthCalledWith(1, 0)
    expect(table.previousPage).toHaveBeenCalledOnce()
    expect(table.nextPage).toHaveBeenCalledOnce()
    expect(table.setPageIndex).toHaveBeenNthCalledWith(2, 2)
  })
})
