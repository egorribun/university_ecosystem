import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { DashboardLesson } from "@/hooks/useDashboardSchedule"
import { ScheduleTimeline } from "./ScheduleTimeline"

// Wave 198 SW6 — ScheduleTimeline Storybook fixture (dashboard, pure-props).
//
// Horizontal 8:00–20:00 timeline of today's lessons with a "now" indicator + hover
// tooltips. `minutesNow` is a plain number prop (deterministic, not Date-derived),
// so the now-line position is stable. No m.*; dashboard tokens are global.
//
// Variants: Default (mid-day, lesson in progress) / DarkMode.

const LESSONS: DashboardLesson[] = [
  {
    id: "l1",
    subject: "Calculus",
    teacher: "Dr. Ivanova",
    room: "ГУК-305",
    lesson_type: "lecture",
    weekday: "Mon",
    start_time: "09:00",
    end_time: "10:30",
    parity: "both",
  },
  {
    id: "l2",
    subject: "Physics Lab",
    teacher: "Dr. Petrov",
    room: "ЛК-12",
    lesson_type: "lab",
    weekday: "Mon",
    start_time: "10:45",
    end_time: "12:15",
    parity: "both",
  },
  {
    id: "l3",
    subject: "Academic English",
    teacher: "Ms. Smith",
    room: "А-201",
    lesson_type: "seminar",
    weekday: "Mon",
    start_time: "13:00",
    end_time: "14:30",
    parity: "both",
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 560, maxWidth: "100%" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ScheduleTimeline> = {
  title: "Dashboard/ScheduleTimeline",
  component: ScheduleTimeline,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    lessons: LESSONS,
    minutesNow: 660, // 11:00 — during the Physics Lab block
    currentLesson: LESSONS[1],
    nextLesson: LESSONS[2],
  },
}

export default meta
type Story = StoryObj<typeof ScheduleTimeline>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
