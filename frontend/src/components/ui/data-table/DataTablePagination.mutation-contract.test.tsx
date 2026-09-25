import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const useTranslationMock = vi.hoisted(() =>
  vi.fn(() => ({
    t: (key: string) => key,
  }))
)

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

import { DataTablePagination } from "./DataTablePagination"
import type { DataTableInstance } from "./dataTableFeatures"

function makeTable(): DataTableInstance<Record<string, never>> {
  return {
    getFilteredSelectedRowModel: () => ({ rows: [] }),
    getFilteredRowModel: () => ({ rows: [] }),
    state: { pagination: { pageIndex: 0, pageSize: 20 } },
    getPageCount: () => 1,
    getCanPreviousPage: () => false,
    getCanNextPage: () => false,
    setPageSize: vi.fn(),
    setPageIndex: vi.fn(),
    previousPage: vi.fn(),
    nextPage: vi.fn(),
  } as unknown as DataTableInstance<Record<string, never>>
}

describe("DataTablePagination translation contract", () => {
  it("binds both pagination and Select to the common namespace", () => {
    useTranslationMock.mockClear()

    render(<DataTablePagination table={makeTable()} />)

    expect(useTranslationMock).toHaveBeenCalledWith(["common"])
    expect(useTranslationMock).toHaveBeenCalledWith("common")
  })
})
