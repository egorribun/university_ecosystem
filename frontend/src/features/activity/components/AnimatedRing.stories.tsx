import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import AnimatedRing from "./AnimatedRing"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme"
        style={{
          background: "var(--bg-page)",
          padding: "2rem",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof AnimatedRing> = {
  title: "Features/Activity/AnimatedRing",
  component: AnimatedRing,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    // rAF fill sweep animates 0 -> value — freeze for Chromatic.
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof AnimatedRing>

export const Percent: Story = {
  args: { value: 87, mode: "percent", ariaLabel: "Attendance 87 percent" },
  decorators: [themed(false)],
}

export const Gauge: Story = {
  args: { value: 4.6, max: 5, mode: "gauge", ariaLabel: "GPA 4.6 of 5" },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Gauge mode shows value / max with a sub-label." } },
  },
}

export const Count: Story = {
  args: { value: 12, max: 20, mode: "count", ariaLabel: "12 of 20 events attended" },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { value: 87, mode: "percent", ariaLabel: "Attendance 87 percent" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
