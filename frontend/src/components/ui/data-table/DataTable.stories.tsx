import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { DataTable } from "./DataTable"
import type { DataTableColumnDef } from "./dataTableFeatures"

// Wave 199 SW1 — DataTable Storybook fixture (CONTEXT-tier, no infra).
//
// Generic TanStack-Table wrapper. Unlike the W196 DataTablePagination story
// (which builds its own `useReactTable`), DataTable takes `{ columns, data }`
// and manages core/filtered/sorted/paginated/faceted row models + selection
// internally — so the story just passes a column def + sample rows. 18 rows →
// 2 pages, demonstrating the built-in pagination. Labels via ambient i18n.
//
// Variants: Default / DarkMode.

type Person = { id: number; name: string; email: string; role: string }

const DATA: Person[] = Array.from({ length: 18 }, (_, i) => ({
  id: i + 1,
  name: `Пользователь ${i + 1}`,
  email: `user${i + 1}@guu.ru`,
  role: i % 3 === 0 ? "admin" : "student",
}))

const columns: DataTableColumnDef<Person>[] = [
  { accessorKey: "name", header: "Имя" },
  { accessorKey: "email", header: "Email" },
  { accessorKey: "role", header: "Роль" },
]

const Harness = () => <DataTable columns={columns} data={DATA} />

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

const meta: Meta<typeof DataTable> = {
  title: "UI/DataTable",
  component: DataTable,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <Harness />,
}

export default meta
type Story = StoryObj<typeof DataTable>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
