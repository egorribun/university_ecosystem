import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { AttendanceStats, GradeStats, ParticipationStats } from "../types"
import { ActivityMotivation } from "./ActivityMotivation"

// Wave 198 SW5 — ActivityMotivation Storybook fixture (pure-props).
//
// A streak chip (flame) + a context-dependent encouragement message derived from
// attendance %, grade trend, and participation count. Renders nothing until
// hasInitiallyLoaded. No m.* → no LazyMotion; `.activity-theme` for the streak token.
//
// Variants: Excellent (high % + streak) / Default (lower % message) / DarkMode.

const ATTENDANCE_HIGH: AttendanceStats = {
  percent: 96,
  present: 48,
  total: 50,
  trend: 4,
  periodLabel: "last 90 days",
  periodKey: "90d",
  recent: [
    { date: "2026-05-28", status: "present", course: "Calculus" },
    { date: "2026-05-27", status: "present", course: "Physics" },
    { date: "2026-05-26", status: "present", course: "Chemistry" },
    { date: "2026-05-25", status: "present", course: "History" },
  ],
}
const GRADES: GradeStats = { average: 4.6, scale: "5", trend: 2, recent: [] }
const PARTICIPATION: ParticipationStats = { events: 6, hours: 18, groups: 2, trend: 1, recent: [] }

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

const meta: Meta<typeof ActivityMotivation> = {
  title: "Activity/ActivityMotivation",
  component: ActivityMotivation,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    attendance: ATTENDANCE_HIGH,
    grades: GRADES,
    participation: PARTICIPATION,
    hasInitiallyLoaded: true,
  },
}

export default meta
type Story = StoryObj<typeof ActivityMotivation>

export const Excellent: Story = {
  decorators: [themed(false)],
}

export const Default: Story = {
  args: {
    attendance: { ...ATTENDANCE_HIGH, percent: 72, recent: [] },
    grades: { ...GRADES, trend: -1 },
    participation: { ...PARTICIPATION, events: 1 },
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
