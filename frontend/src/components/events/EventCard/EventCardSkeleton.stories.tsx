import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { EventCardSkeleton } from "./EventCardSkeleton"

// Wave 198 SW3 — EventCardSkeleton Storybook fixture (zero-prop shimmer).
//
// Loading placeholder for EventCard (media + title + speaker + date/location +
// description + actions). Pure visual — ContentCard + Skeleton primitives. Scoped
// in `.events-theme` for the event-divider token.
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 380 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventCardSkeleton> = {
  title: "Events/EventCardSkeleton",
  component: EventCardSkeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventCardSkeleton>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
