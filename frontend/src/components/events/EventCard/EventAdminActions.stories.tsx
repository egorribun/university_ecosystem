import { useState, type ComponentProps } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { EventAdminActions } from "./EventAdminActions"

// Wave 199 SW1 — EventAdminActions Storybook fixture (CONTEXT-tier, no infra).
//
// The admin "⋮" menu overlaid on an event card (absolute top-3 right-3). No
// network, only useTranslation. `menuAnchor` is a controlled prop used ONLY for
// a truthiness check (Boolean(menuAnchor)) + aria-controls — it is never
// dereferenced — so the harness opens the dropdown by seeding state with a
// detached element. A `relative` card gives the absolute button/dropdown a
// positioned ancestor.
//
// Variants: Closed (button only) / Open (dropdown) / DarkMode.

type Args = ComponentProps<typeof EventAdminActions>

const AdminActionsHarness = ({ args, startOpen }: { args: Args; startOpen: boolean }) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(() =>
    startOpen && typeof document !== "undefined" ? document.createElement("button") : null
  )
  return (
    <div
      className="relative h-40 w-[360px] rounded-2xl border border-(--glass-border) bg-(--bg-surface) shadow-surface"
      role="presentation"
    >
      <EventAdminActions {...args} menuAnchor={anchor} setMenuAnchor={setAnchor} />
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof EventAdminActions> = {
  title: "Events/EventAdminActions",
  component: EventAdminActions,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { menuId: "evt-admin-menu", onEdit: () => {}, onDelete: () => {} },
}

export default meta
type Story = StoryObj<typeof EventAdminActions>

export const Closed: Story = {
  decorators: [themed(false)],
  render: (args) => <AdminActionsHarness args={args} startOpen={false} />,
}

export const Open: Story = {
  decorators: [themed(false)],
  render: (args) => <AdminActionsHarness args={args} startOpen />,
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
  render: (args) => <AdminActionsHarness args={args} startOpen />,
}
