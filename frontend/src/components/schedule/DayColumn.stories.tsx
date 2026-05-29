import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { DayColumn } from "./DayColumn"
import type { Lesson } from "./scheduleUtils"

// Wave 196 SW1 — DayColumn Storybook fixture (LEAF tier batch 2).
//
// Single-day vertical card stack for the mobile schedule view. Heaviest LEAF
// in the batch (18 props) but renders entirely from props + the `.schedule-theme`
// token scope (matches Schedule.tsx:212). Stories use `userRole="student"` so
// `canEdit` is false → the inner LessonList returns a plain <div> WITHOUT
// @dnd-kit's DndContext (PERF-70-06), keeping the story provider-free.
// No framer-motion — the day-complete confetti is pure CSS, so no LazyMotion.
//
// Variants: Default (3 lessons) / Today (current-lesson glow) / EmptyDay
// (EmptyState) / Offline (OfflineFallback) / DarkMode.

const lessons: Lesson[] = [
  {
    id: "l1",
    weekday: "Monday",
    parity: "both",
    start_time: "09:00",
    end_time: "10:30",
    subject: "Linear Algebra",
    teacher: "Dr. Ivanova",
    room: "ГУК-305",
    lesson_type: "lecture",
  },
  {
    id: "l2",
    weekday: "Monday",
    parity: "both",
    start_time: "10:45",
    end_time: "12:15",
    subject: "Discrete Mathematics",
    teacher: "Prof. Petrov",
    room: "ЛК-201",
    lesson_type: "practice",
  },
  {
    id: "l3",
    weekday: "Monday",
    parity: "both",
    start_time: "13:00",
    end_time: "14:30",
    subject: "Algorithms Lab",
    teacher: "Dr. Smirnova",
    room: "ЦИТ-410",
    lesson_type: "lab",
  },
]

const typeColor = (val?: string | null) => {
  switch (val) {
    case "lecture":
      return "#6366f1"
    case "practice":
      return "#10b981"
    case "lab":
      return "#f59e0b"
    default:
      return "#64748b"
  }
}

const typeLabel = (val?: string | null) => {
  switch (val) {
    case "lecture":
      return "Lecture"
    case "practice":
      return "Practice"
    case "lab":
      return "Lab"
    default:
      return "Lesson"
  }
}

const baseArgs = {
  day: "mon",
  label: "Monday",
  lessons,
  isToday: false,
  isOnline: true,
  hasSchedule: true,
  userRole: "student",
  conflictedIds: new Set<string>(),
  compact: false,
  dayComplete: false,
  notesMap: new Map<string, boolean>(),
  onAdd: () => {},
  onLessonDelete: () => {},
  onRetry: () => {},
  getLessonTypeColor: typeColor,
  getLessonTypeLabel: typeLabel,
} satisfies Partial<React.ComponentProps<typeof DayColumn>>

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="schedule-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 380 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof DayColumn> = {
  title: "Schedule/DayColumn",
  component: DayColumn,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DayColumn>

export const Default: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const Today: Story = {
  args: { ...baseArgs, isToday: true, currentLessonId: "l2", currentProgress: 60 },
  decorators: [themed(false)],
}

export const EmptyDay: Story = {
  args: { ...baseArgs, label: "Sunday", day: "sun", lessons: [] },
  decorators: [themed(false)],
}

export const Offline: Story = {
  args: { ...baseArgs, lessons: [], isOnline: false, hasSchedule: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs, isToday: true, currentLessonId: "l2", currentProgress: 60 },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
