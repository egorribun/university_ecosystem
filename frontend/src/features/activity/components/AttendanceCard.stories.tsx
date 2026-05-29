import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { AttendanceStats } from "../types"
import { AttendanceCard } from "./AttendanceCard"

// Wave 198 SW5 — AttendanceCard Storybook fixture (activity card, pure-props).
//
// CardShell + AnimatedRing (percent) + TrendChip + ProgressBar + SkeletonMorph.
// No network. AnimatedRing uses m.* → LazyMotion; `.activity-theme` for tokens.
//
// Variants: Default / Loading / DarkMode.

const ATTENDANCE: AttendanceStats = {
  percent: 92,
  present: 46,
  total: 50,
  trend: 3,
  periodLabel: "last 90 days",
  periodKey: "90d",
  recent: [
    { date: "2026-05-28", status: "present", course: "Calculus" },
    { date: "2026-05-27", status: "present", course: "Physics" },
    { date: "2026-05-26", status: "late", course: "Chemistry" },
  ],
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="activity-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div className="activity-card-matte" style={{ width: 420 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof AttendanceCard> = {
  title: "Activity/AttendanceCard",
  component: AttendanceCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { attendance: ATTENDANCE, hasInitiallyLoaded: true, ringSize: 88 },
}

export default meta
type Story = StoryObj<typeof AttendanceCard>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Loading: Story = {
  args: { hasInitiallyLoaded: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
