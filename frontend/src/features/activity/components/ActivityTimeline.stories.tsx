import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { AttendanceStats, GradeStats, ParticipationStats } from "../types"
import { ActivityTimeline } from "./ActivityTimeline"

// Wave 198 SW5 — ActivityTimeline Storybook fixture (pure-props).
//
// Merges the recent attendance/grade/participation arrays into one date-sorted
// feed of ActivityTimelineItem rows. `attendanceStatusLabel` + `formatDate` are
// simple fn props. No network. Renders nothing until hasInitiallyLoaded; shows a
// "no activity" empty state when all recents are empty. m.*/stagger → LazyMotion;
// `.activity-theme` for tokens.
//
// Variants: Default (merged feed) / Empty / DarkMode.

const ATTENDANCE: AttendanceStats = {
  percent: 90,
  present: 45,
  total: 50,
  trend: 2,
  periodLabel: "last 90 days",
  periodKey: "90d",
  recent: [
    { date: "2026-05-28", status: "present", course: "Calculus" },
    { date: "2026-05-26", status: "late", course: "Physics" },
    { date: "2026-05-22", status: "absent", course: "Biology" },
  ],
}
const GRADES: GradeStats = {
  average: 4.5,
  scale: "5",
  trend: 1,
  recent: [
    { course: "Calculus", score: 5, max: 5, date: "2026-05-27" },
    { course: "Chemistry", score: 4, max: 5, date: "2026-05-23" },
  ],
}
const PARTICIPATION: ParticipationStats = {
  events: 4,
  hours: 12,
  groups: 2,
  trend: 0,
  recent: [
    { title: "Hackathon 2026", date: "2026-05-25", role: "Participant" },
    { title: "Open Day Volunteer", date: "2026-05-20" },
  ],
}

const noopLabel = (status: "present" | "absent" | "late") => status
const identityDate = (date: string) => date

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="activity-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 520 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof ActivityTimeline> = {
  title: "Activity/ActivityTimeline",
  component: ActivityTimeline,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    attendance: ATTENDANCE,
    grades: GRADES,
    participation: PARTICIPATION,
    hasInitiallyLoaded: true,
    attendanceStatusLabel: noopLabel,
    formatDate: identityDate,
  },
}

export default meta
type Story = StoryObj<typeof ActivityTimeline>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Empty: Story = {
  args: { attendance: null, grades: null, participation: null },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
