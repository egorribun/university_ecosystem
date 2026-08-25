import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { axe } from "jest-axe"
import { DataTableColumnHeader } from "./DataTableColumnHeader"
import type { DataTableColumn } from "./dataTableFeatures"

/**
 * DataTableColumnHeader ARIA + sorting interaction tests.
 *
 * The component renders one of two shapes depending on whether the
 * underlying TanStack Table column is sortable:
 *  - non-sortable → plain `<div>{title}</div>` (no button, no ARIA);
 *  - sortable → button with aria-label that announces the current
 *    sort direction. Sort direction icon is aria-hidden because the
 *    state is conveyed through the label.
 *
 * Note: `aria-sort` itself lives on the parent `<TableHead>` (the
 * `<th>` element) — DataTableColumnHeader is the inner button only.
 */

function makeColumn(
  overrides: Partial<{
    canSort: boolean
    isSorted: false | "asc" | "desc"
  }> = {}
): DataTableColumn<Record<string, never>, unknown> {
  const { canSort = true, isSorted = false } = overrides
  const toggleSorting = vi.fn()
  return {
    getCanSort: () => canSort,
    getIsSorted: () => isSorted,
    toggleSorting,
    // Other Column<>'s methods aren't called by the component — cast through.
  } as unknown as DataTableColumn<Record<string, never>, unknown>
}

describe("DataTableColumnHeader — non-sortable column", () => {
  it("renders the title in a plain div without a button", () => {
    const column = makeColumn({ canSort: false })
    render(<DataTableColumnHeader column={column} title="Email" />)
    expect(screen.getByText("Email")).toBeInTheDocument()
    expect(screen.queryByRole("button")).toBeNull()
  })
})

describe("DataTableColumnHeader — sortable column", () => {
  it("renders a button with the title text", () => {
    render(<DataTableColumnHeader column={makeColumn()} title="Created" />)
    const btn = screen.getByRole("button")
    expect(btn).toHaveTextContent("Created")
  })

  it("announces 'not sorted' when no sort direction is set", () => {
    render(<DataTableColumnHeader column={makeColumn()} title="Created" />)
    expect(screen.getByRole("button", { name: /not sorted/i })).toBeInTheDocument()
  })

  it("announces 'sorted ascending' when isSorted is 'asc'", () => {
    render(<DataTableColumnHeader column={makeColumn({ isSorted: "asc" })} title="Created" />)
    expect(screen.getByRole("button", { name: /sorted ascending/i })).toBeInTheDocument()
  })

  it("announces 'sorted descending' when isSorted is 'desc'", () => {
    render(<DataTableColumnHeader column={makeColumn({ isSorted: "desc" })} title="Created" />)
    expect(screen.getByRole("button", { name: /sorted descending/i })).toBeInTheDocument()
  })

  it("calls toggleSorting on click — false when not asc, true when asc", async () => {
    const user = userEvent.setup()

    // Click from no-sort → should call toggleSorting(false) (asc).
    const colA = makeColumn({ isSorted: false })
    const { unmount } = render(<DataTableColumnHeader column={colA} title="X" />)
    await user.click(screen.getByRole("button"))
    expect(colA.toggleSorting).toHaveBeenCalledWith(false)
    unmount()

    // Click from asc → should call toggleSorting(true) (desc).
    const colB = makeColumn({ isSorted: "asc" })
    render(<DataTableColumnHeader column={colB} title="X" />)
    await user.click(screen.getByRole("button"))
    expect(colB.toggleSorting).toHaveBeenCalledWith(true)
  })
})

describe("DataTableColumnHeader — accessibility", () => {
  it.each([
    ["non-sortable", makeColumn({ canSort: false })],
    ["unsorted", makeColumn({ isSorted: false })],
    ["asc", makeColumn({ isSorted: "asc" })],
    ["desc", makeColumn({ isSorted: "desc" })],
  ] as const)("has no axe violations (%s)", async (_label, column) => {
    const { container } = render(<DataTableColumnHeader column={column} title="Status" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
