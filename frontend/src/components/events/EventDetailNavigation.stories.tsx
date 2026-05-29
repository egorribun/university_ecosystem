import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { EventDetailNavigation } from "./EventDetailNavigation"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 768, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventDetailNavigation> = {
  title: "Events/EventDetailNavigation",
  component: EventDetailNavigation,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventDetailNavigation>

export const Both: Story = {
  args: {
    prevId: "ev-1",
    nextId: "ev-3",
    prevTitle: "Orientation Week Kickoff",
    nextTitle: "Hackathon Finals 2026",
  },
  decorators: [themed(false)],
}

export const OnlyNext: Story = {
  args: { prevId: null, nextId: "ev-3", prevTitle: null, nextTitle: "Hackathon Finals 2026" },
  decorators: [themed(false)],
}

export const OnlyPrev: Story = {
  args: { prevId: "ev-1", nextId: null, prevTitle: "Orientation Week Kickoff", nextTitle: null },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...Both.args },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
