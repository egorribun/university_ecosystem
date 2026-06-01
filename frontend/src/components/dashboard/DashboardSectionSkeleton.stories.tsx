import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { DashboardSectionSkeleton } from "./DashboardSectionSkeleton"

// Wave 196 SW2 — DashboardSectionSkeleton Storybook fixture (LEAF tier batch 2).
//
// Loading skeleton for the dashboard's schedule / news / events cards. Deterministic
// (fixed row counts), renders from the `type` prop alone. No framer-motion, no theme
// scope (matte card + Skeleton shimmer are global). Distinct from the existing
// `Skeletons.stories.tsx` aggregate (which covers feed *card* skeletons, not these
// dashboard *section* skeletons).
//
// Variants: Schedule / News / Events / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem", width: 380 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof DashboardSectionSkeleton> = {
  title: "Dashboard/DashboardSectionSkeleton",
  component: DashboardSectionSkeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DashboardSectionSkeleton>

export const Schedule: Story = {
  args: { type: "schedule" },
  decorators: [themed(false)],
}

export const News: Story = {
  args: { type: "news" },
  decorators: [themed(false)],
}

export const Events: Story = {
  args: { type: "events" },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { type: "schedule" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
