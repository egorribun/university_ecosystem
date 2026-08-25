import { fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { type ColumnFiltersState, useTable } from "@tanstack/react-table"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

import { DataTable } from "./DataTable"
import { dataTableFeatures, type DataTableColumnDef } from "./dataTableFeatures"

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

const featureRows: Row[] = [
  { id: "1", name: "Alice", status: "enabled" },
  { id: "2", name: "Bob", status: "disabled" },
  { id: "3", name: "Carol", status: "enabled" },
]

const featureColumns: DataTableColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "status", header: "Status" },
]

function FeatureRegistryHarness() {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const table = useTable({
    features: dataTableFeatures,
    data: featureRows,
    columns: featureColumns,
    state: { columnFilters },
    onColumnFiltersChange: setColumnFilters,
  })
  const statusColumn = table.getColumn("status")
  const facetedValues = [...(statusColumn?.getFacetedUniqueValues() ?? new Map())]
    .sort(([left], [right]) => String(left).localeCompare(String(right)))
    .map(([value, count]) => `${String(value)}:${count}`)
    .join(",")

  return (
    <div>
      <button type="button" onClick={() => statusColumn?.setFilterValue("disabled")}>
        Filter disabled
      </button>
      <output data-testid="filtered-rows">
        {table
          .getFilteredRowModel()
          .rows.map((row) => row.original.name)
          .join(",")}
      </output>
      <output data-testid="faceted-rows">
        {statusColumn
          ?.getFacetedRowModel()
          .rows.map((row) => row.original.name)
          .join(",")}
      </output>
      <output data-testid="faceted-values">{facetedValues}</output>
    </div>
  )
}

function renderedBodyRows() {
  return [...document.querySelectorAll("tbody tr")].map((row) => row.textContent)
}

describe("DataTable closure branches", () => {
  it("renders placeholder and unsorted headers, cycles sorting, and marks a row selected", () => {
    render(
      <DataTable
        columns={columns}
        data={[
          { id: "2", name: "Bob", status: "inactive" },
          { id: "1", name: "Alice", status: "active" },
        ]}
      />
    )

    expect(renderedBodyRows()).toEqual(["Bobinactive", "Aliceactive"])

    const nameHeader = screen.getByRole("columnheader", { name: "Name" })
    expect(nameHeader).toHaveAttribute("aria-sort", "none")

    const nameButton = screen.getByRole("button", { name: "Name" })
    fireEvent.click(nameButton)
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute(
      "aria-sort",
      "ascending"
    )
    expect(renderedBodyRows()).toEqual(["Aliceactive", "Bobinactive"])
    fireEvent.click(nameButton)
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute(
      "aria-sort",
      "descending"
    )
    expect(renderedBodyRows()).toEqual(["Bobinactive", "Aliceactive"])

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

  it("filters rows and exposes faceted row and unique-value models from the real registry", () => {
    render(<FeatureRegistryHarness />)

    expect(screen.getByTestId("filtered-rows")).toHaveTextContent("Alice,Bob,Carol")
    expect(screen.getByTestId("faceted-rows")).toHaveTextContent("Alice,Bob,Carol")
    expect(screen.getByTestId("faceted-values")).toHaveTextContent("disabled:1,enabled:2")

    fireEvent.click(screen.getByRole("button", { name: "Filter disabled" }))

    expect(screen.getByTestId("filtered-rows")).toHaveTextContent("Bob")
    expect(screen.getByTestId("faceted-rows")).toHaveTextContent("Alice,Bob,Carol")
    expect(screen.getByTestId("faceted-values")).toHaveTextContent("disabled:1,enabled:2")
  })

  it("paginates the public table with the real row model", () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      id: String(index + 1),
      name: `User ${index + 1}`,
      status: "active",
    }))

    render(<DataTable columns={columns} data={rows} />)

    expect(screen.getByRole("button", { name: "User 1" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "User 11" })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:pagination.nextPage" }))

    expect(screen.queryByRole("button", { name: "User 1" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "User 11" })).toBeInTheDocument()
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()
  })
})
