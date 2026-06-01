import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { NewsCardBackground } from "./NewsCardBackground"

// Wave 196 SW2 — NewsCardBackground Storybook fixture (LEAF tier batch 2).
//
// Pure-decoration orb layer for the dashboard news card — two `absolute inset-0`
// radial-gradient spans (CSS @keyframes orb-breathe / orb-drift; mix-blend-soft-light).
// Zero props. Its `--dash-card-news-*` color tokens live under `.dashboard-theme`
// (tokens/dashboard.css:73-74), so the decorator wraps in `.dashboard-theme` + a
// `relative overflow-hidden` card host for the absolute orbs to anchor + show.
// CSS-only animation (no framer-motion → no LazyMotion).
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="dashboard-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="relative overflow-hidden rounded-2xl"
          style={{ width: 320, height: 200, background: "var(--bg-surface)" }}
        >
          <Story />
          <div className="relative z-[1] flex h-full items-center justify-center text-sm text-(--text-secondary)">
            News card surface — sky orbs breathe behind
          </div>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardBackground> = {
  title: "Dashboard/NewsCardBackground",
  component: NewsCardBackground,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsCardBackground>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
