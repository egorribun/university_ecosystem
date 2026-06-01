import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { EventSearchBar } from "./EventSearchBar"

const noop = () => {}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 560, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const baseArgs = {
  search: "",
  onSearchChange: noop,
  dateRange: "" as const,
  onDateRangeChange: noop,
  location: "",
  onLocationChange: noop,
}

const meta: Meta<typeof EventSearchBar> = {
  title: "Events/EventSearchBar",
  component: EventSearchBar,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventSearchBar>

export const Default: Story = { args: baseArgs, decorators: [themed(false)] }

export const WithQuery: Story = {
  args: { ...baseArgs, search: "festival" },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "Active query reveals the clear (×) button." } } },
}

export const FiltersActive: Story = {
  args: { ...baseArgs, dateRange: "week" as const },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Active date filter shows the brand dot on the filter trigger." },
    },
  },
}

export const DarkMode: Story = {
  args: baseArgs,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
