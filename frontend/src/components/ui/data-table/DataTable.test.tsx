import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

import { DataTable } from "./DataTable"
import type { DataTableColumnDef } from "./dataTableFeatures"

type Row = { id: string; name: string; status: string }

const columns: DataTableColumnDef<Row>[] = [
  {
    id: "group",
    header: "Details",
    columns: [
      {
        accessorKey: "name",
        header: ({ column }) => (
          <button type="button" onClick={column.getToggleSortingHandler()}>
            Name
          </button>
        ),
        cell: ({ row }) => (
          <button type="button" onClick={() => row.toggleSelected()}>
            {row.original.name}
          </button>
        ),
      },
    ],
  },
  {
    accessorKey: "status",
    header: "Status",
  },
]

describe("DataTable closure branches", () => {
  it("renders placeholder and unsorted headers, cycles sorting, and marks a row selected", () => {
    render(
      <DataTable
        columns={columns}
        data={[
          { id: "1", name: "Alice", status: "active" },
          { id: "2", name: "Bob", status: "inactive" },
        ]}
      />
    )

    const nameHeader = screen.getByRole("columnheader", { name: "Name" })
    expect(nameHeader).toHaveAttribute("aria-sort", "none")

    const nameButton = screen.getByRole("button", { name: "Name" })
    fireEvent.click(nameButton)
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute(
      "aria-sort",
      "ascending"
    )
    fireEvent.click(nameButton)
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute(
      "aria-sort",
      "descending"
    )

    fireEvent.click(screen.getByRole("button", { name: "Alice" }))
    expect(screen.getByRole("row", { name: /Alice active/ })).toHaveAttribute(
      "data-state",
      "selected"
    )

    expect(screen.getAllByRole("columnheader").some((header) => header.textContent === "")).toBe(
      true
    )
  })

  it("renders the no-results row for empty data", () => {
    render(<DataTable columns={columns} data={[]} />)
    expect(screen.getByText("No results.")).toBeInTheDocument()
  })
})
