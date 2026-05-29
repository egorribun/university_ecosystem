import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ActivityTimelineItem } from "./ActivityTimelineItem"
import type { TimelineEntry } from "../types"

// Wave 196 SW3 — ActivityTimelineItem Storybook fixture (LEAF tier batch 2).
//
// A single entry in the merged activity feed (attendance / grade / participation
// discriminated union). Renders from `entry` + `formatDate` + `attendanceStatusLabel`
// + `staggerIndex` props; the colored status dot + icon are derived from the entry
// type/status. `.activity-theme` supplies the `--activity-*-accent` dot colors.
// CSS stagger (no framer-motion). Identity formatters keep the story deterministic.
//
// Variants: AttendancePresent / Grade / Participation / DarkMode.

const fmtDate = (d: string) => d
const statusLabel = (s: "present" | "absent" | "late") => s

const attendance: TimelineEntry = {
  type: "attendance",
  date: "2026-05-20",
  course: "Linear Algebra",
  status: "present",
}
const grade: TimelineEntry = {
  type: "grade",
  date: "2026-05-19",
  course: "Discrete Mathematics",
  score: 92,
  max: 100,
}
const participation: TimelineEntry = {
  type: "participation",
  date: "2026-05-18",
  title: "Spring Hackathon 2026",
  role: "Team Lead",
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", width: 360 }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof ActivityTimelineItem> = {
  title: "Features/Activity/ActivityTimelineItem",
  component: ActivityTimelineItem,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityTimelineItem>

export const AttendancePresent: Story = {
  args: {
    entry: attendance,
    formatDate: fmtDate,
    attendanceStatusLabel: statusLabel,
    staggerIndex: 0,
  },
  decorators: [themed(false)],
}

export const Grade: Story = {
  args: { entry: grade, formatDate: fmtDate, attendanceStatusLabel: statusLabel, staggerIndex: 1 },
  decorators: [themed(false)],
}

export const Participation: Story = {
  args: {
    entry: participation,
    formatDate: fmtDate,
    attendanceStatusLabel: statusLabel,
    staggerIndex: 2,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { entry: grade, formatDate: fmtDate, attendanceStatusLabel: statusLabel, staggerIndex: 0 },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
