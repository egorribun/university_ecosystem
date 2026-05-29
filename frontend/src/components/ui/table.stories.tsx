import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from "./table"

// Wave 199 SW1 — ui/table composition example (CONTEXT-tier, no infra).
//
// Semantic table primitives (forwardRef wrappers over thead/tbody/tr/th/td).
// Pure styling, no state, no network, no portal. One composed showcase per theme.
//
// Variants: Default / DarkMode.

const ROWS = [
  { name: "Иванова Анна", group: "ИС-301", attendance: "98%" },
  { name: "Петров Иван", group: "ИС-301", attendance: "91%" },
  { name: "Сидорова Мария", group: "ИС-302", attendance: "87%" },
  { name: "Кузнецов Олег", group: "ИС-302", attendance: "95%" },
]

const TableComposite = () => (
  <Table>
    <TableCaption>Посещаемость за семестр</TableCaption>
    <TableHeader>
      <TableRow>
        <TableHead>Студент</TableHead>
        <TableHead>Группа</TableHead>
        <TableHead className="text-right">Посещаемость</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {ROWS.map((row) => (
        <TableRow key={row.name}>
          <TableCell className="font-medium text-text-primary">{row.name}</TableCell>
          <TableCell>{row.group}</TableCell>
          <TableCell className="text-right">{row.attendance}</TableCell>
        </TableRow>
      ))}
    </TableBody>
    <TableFooter>
      <TableRow>
        <TableCell colSpan={2}>Средняя</TableCell>
        <TableCell className="text-right">92.75%</TableCell>
      </TableRow>
    </TableFooter>
  </Table>
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem", width: 560 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof Table> = {
  title: "UI/Table",
  component: Table,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <TableComposite />,
}

export default meta
type Story = StoryObj<typeof Table>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
