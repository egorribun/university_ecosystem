import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useMemo } from "react"
import { useTable } from "@tanstack/react-table"
import { DataTablePagination } from "./DataTablePagination"
import { dataTableFeatures, type DataTableColumnDef } from "./dataTableFeatures"

// Wave 196 SW3 — DataTablePagination Storybook fixture (LEAF tier batch 2).
//
// Pagination controls for the generic DataTable (page-size Select + first/prev/
// next/last + "N of M selected" + "Page X of Y"). It consumes a TanStack
// `Table<TData>`, so the story builds a real 42-row table via `useReactTable`
// (core + filtered + pagination row models + enableRowSelection) mirroring
// DataTable.tsx. Buttons mutate the table's internal (uncontrolled) state. Labels
// come from the global I18nextProvider. No theme scope, no framer-motion.
//
// Variants: Default (Page 1 of 5) / DarkMode.

type Row = { id: number; name: string }

function Harness() {
  const data = useMemo<Row[]>(
    () => Array.from({ length: 42 }, (_, i) => ({ id: i + 1, name: `Row ${i + 1}` })),
    []
  )
  const columns: DataTableColumnDef<Row>[] = [{ accessorKey: "name", header: "Name" }]
  const table = useTable({
    features: dataTableFeatures,
    data,
    columns,
    enableRowSelection: true,
    initialState: { pagination: { pageIndex: 0, pageSize: 10 } },
  })
  return <DataTablePagination table={table} />
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem", width: 720 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof DataTablePagination> = {
  title: "UI/DataTablePagination",
  component: DataTablePagination,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DataTablePagination>

export const Default: Story = {
  render: () => <Harness />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <Harness />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
