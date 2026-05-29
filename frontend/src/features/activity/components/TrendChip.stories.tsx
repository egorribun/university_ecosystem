import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import TrendChip from "./TrendChip"

// Wave 196 SW3 — TrendChip Storybook fixture (LEAF tier batch 2).
//
// Trend badge with up/down icon + signed percentage. Renders from a single
// numeric `value` prop (returns null when value is not a number). `.activity-theme`
// supplies the `.activity-trend-icon` token. No framer-motion.
//
// Variants: Positive / Negative / Zero / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="activity-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof TrendChip> = {
  title: "Features/Activity/TrendChip",
  component: TrendChip,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof TrendChip>

export const Positive: Story = {
  args: { value: 5.2 },
  decorators: [themed(false)],
}

export const Negative: Story = {
  args: { value: -3.1 },
  decorators: [themed(false)],
}

export const Zero: Story = {
  args: { value: 0 },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { value: 5.2 },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
