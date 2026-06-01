import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
} from "@tanstack/react-table"
import { DataTableColumnHeader } from "./DataTableColumnHeader"

// Wave 196 SW3 — DataTableColumnHeader Storybook fixture (LEAF tier batch 2).
//
// Sortable column-header cell for the generic DataTable. It consumes a TanStack
// `Column<TData>` (calls getCanSort / getIsSorted / toggleSorting), so the story
// uses a tiny `useReactTable` harness (mirroring DataTable.tsx) to produce a real
// column. `enableSorting` toggles between the sort button and a plain title.
// No theme scope, no framer-motion.
//
// Variants: Sortable (sort button) / NotSortable (plain title) / DarkMode.

type Row = { name: string; email: string }
const data: Row[] = [{ name: "Anna Petrova", email: "anna@guu.ru" }]

function Harness({ title, sortable }: { title: string; sortable: boolean }) {
  const columns: ColumnDef<Row>[] = [
    { accessorKey: "name", header: title, enableSorting: sortable },
  ]
  const table = useReactTable<Row>({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const column = table.getColumn("name")
  if (!column) return null
  return <DataTableColumnHeader column={column} title={title} />
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof DataTableColumnHeader> = {
  title: "UI/DataTableColumnHeader",
  component: DataTableColumnHeader,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DataTableColumnHeader>

export const Sortable: Story = {
  render: () => <Harness title="Name" sortable />,
  decorators: [themed(false)],
}

export const NotSortable: Story = {
  render: () => <Harness title="Email" sortable={false} />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <Harness title="Name" sortable />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
