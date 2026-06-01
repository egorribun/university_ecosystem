import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { SchedulePageProvider } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { ScheduleListView } from "./ScheduleListView"

// Wave 197 SW5 — ScheduleListView Storybook fixture (CONTEXT-tier, medium).
//
// Chronological flat list of the week's lessons. Props are
// Pick<ReturnType<useScheduleData>> + display helpers (same set as the desktop
// table). Real <SchedulePageProvider> for useSchedulePage(); Zustand stores
// global. user=null → read-only.
//
// Variants: Default / DarkMode.

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
const WEEKDAY_LABELS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]

const LESSONS: Lesson[] = [
  {
    id: "l1",
    weekday: "monday",
    parity: "both",
    start_time: "09:00",
    end_time: "10:30",
    subject: "Линейная алгебра",
    teacher: "Иванова Е.А.",
    room: "ГУК-305",
    lesson_type: "lecture",
    group_id: "g1",
  },
  {
    id: "l2",
    weekday: "monday",
    parity: "both",
    start_time: "10:40",
    end_time: "12:10",
    subject: "Программирование",
    teacher: "Петров И.С.",
    room: "ЛК-201",
    lesson_type: "practice",
    group_id: "g1",
  },
  {
    id: "l3",
    weekday: "wednesday",
    parity: "odd",
    start_time: "13:00",
    end_time: "14:30",
    subject: "Базы данных",
    teacher: "Сидоров А.В.",
    room: "ЦИТ-110",
    lesson_type: "lab",
    group_id: "g1",
  },
  {
    id: "l4",
    weekday: "thursday",
    parity: "both",
    start_time: "09:00",
    end_time: "10:30",
    subject: "Иностранный язык",
    teacher: "Кузнецова О.Н.",
    room: "А-229",
    lesson_type: "seminar",
    group_id: "g1",
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <SchedulePageProvider>
      <div className={dark ? "dark" : undefined}>
        <div
          className="schedule-theme"
          style={{ background: "var(--bg-page)", padding: "1rem", minHeight: 480 }}
        >
          <Story />
        </div>
      </div>
    </SchedulePageProvider>
  )
}

const meta: Meta<typeof ScheduleListView> = {
  title: "Schedule/ScheduleListView",
  component: ScheduleListView,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    schedule: LESSONS,
    rawSchedule: LESSONS,
    weekdayBackend: WEEKDAYS,
    weekdayLabels: WEEKDAY_LABELS,
    hasToday: true,
    todayIdx: 0,
    conflictedIds: new Set<string>(),
    user: null,
    refresh: () => {},
    currentLesson: null,
    currentProgress: 0,
    isOnline: true,
    onDeleteLesson: () => {},
    getLessonTypeColor: () => "var(--lt-lecture-badge)",
    getLessonTypeLabel: (val) => val ?? "Lecture",
    notesMap: new Map<string, boolean>(),
  },
}

export default meta
type Story = StoryObj<typeof ScheduleListView>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
