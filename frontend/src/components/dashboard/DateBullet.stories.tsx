import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { DateBullet } from "./DateBullet"

// Wave 196 SW2 — DateBullet Storybook fixture (LEAF tier batch 2).
//
// Circular day/month badge (premium radial-gradient bg via `.date-bullet-premium`)
// wrapped in a Tooltip. Renders from `date` + `locale` + `size` props; month
// abbreviation is locale-aware via Intl.DateTimeFormat. No framer-motion, no theme
// scope (global brand tokens).
//
// Variants: Default / Compact / NoDate (em-dash fallback) / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof DateBullet> = {
  title: "Dashboard/DateBullet",
  component: DateBullet,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DateBullet>

export const Default: Story = {
  args: { date: "2026-06-15T14:00:00Z", locale: "en-US", size: "default" },
  decorators: [themed(false)],
}

export const Compact: Story = {
  args: { date: "2026-06-15T14:00:00Z", locale: "en-US", size: "compact" },
  decorators: [themed(false)],
}

export const NoDate: Story = {
  args: { locale: "en-US", size: "default" },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { date: "2026-06-15T14:00:00Z", locale: "en-US", size: "default" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
