import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { EventsEmptyState } from "./EventsEmptyState"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="events-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", minHeight: "60vh" }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof EventsEmptyState> = {
  title: "Events/EventsEmptyState",
  component: EventsEmptyState,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventsEmptyState>

export const Active: Story = {
  args: { tab: "active", onTabChange: () => {} },
  decorators: [themed(false)],
}

export const Archive: Story = {
  args: { tab: "archive", onTabChange: () => {} },
  decorators: [themed(false)],
}

export const MyEvents: Story = {
  args: { tab: "my", onTabChange: () => {} },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "The 'my' tab omits the cross-tab CTA button." } } },
}

export const DarkMode: Story = {
  args: { tab: "active", onTabChange: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
