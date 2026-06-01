import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ScheduleCardSkeleton } from "./ScheduleCardSkeleton"

// Wave 198 SW3 — ScheduleCardSkeleton Storybook fixture (shimmer; `items?`).
//
// Loading placeholder for ScheduleCard (header + N lesson rows). `items` controls
// the row count. Pure visual — Skeleton primitives + global glass tokens;
// useTranslation drives the aria-label (ambient i18n). Scoped in `.schedule-theme`.
//
// Variants: Default (3) / FiveItems / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="schedule-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 420 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ScheduleCardSkeleton> = {
  title: "Schedule/ScheduleCardSkeleton",
  component: ScheduleCardSkeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { items: 3 },
}

export default meta
type Story = StoryObj<typeof ScheduleCardSkeleton>

export const Default: Story = {
  decorators: [themed(false)],
}

export const FiveItems: Story = {
  args: { items: 5 },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
