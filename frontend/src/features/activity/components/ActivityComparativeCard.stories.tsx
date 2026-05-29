import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ActivityComparativeCard } from "./ActivityComparativeCard"

// Wave 196 SW3 — ActivityComparativeCard Storybook fixture (LEAF tier batch 2).
//
// Period-over-period comparison card (current vs previous + signed delta with
// up/down/neutral icon). Renders from props alone (label/current/previous/delta/
// format/colorVar). `.activity-theme` supplies `--activity-positive/negative-accent`.
// No framer-motion. `colorVar` is a CSS-var string for the headline value.
//
// Variants: Positive / Negative / Neutral / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", width: 280 }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof ActivityComparativeCard> = {
  title: "Features/Activity/ActivityComparativeCard",
  component: ActivityComparativeCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityComparativeCard>

export const Positive: Story = {
  args: {
    label: "Attendance",
    current: 94,
    previous: 88,
    delta: 6.8,
    format: "percent",
    colorVar: "var(--activity-present-accent)",
  },
  decorators: [themed(false)],
}

export const Negative: Story = {
  args: {
    label: "Participation",
    current: 4,
    previous: 7,
    delta: -42.9,
    format: "count",
    colorVar: "var(--activity-participation-accent)",
  },
  decorators: [themed(false)],
}

export const Neutral: Story = {
  args: {
    label: "Grade average",
    current: 4.5,
    previous: 4.5,
    delta: 0,
    format: "decimal",
    colorVar: "var(--activity-grade-accent)",
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: {
    label: "Attendance",
    current: 94,
    previous: 88,
    delta: 6.8,
    format: "percent",
    colorVar: "var(--activity-present-accent)",
  },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
