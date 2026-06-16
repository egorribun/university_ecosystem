import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { ScheduleListView } from "@/components/schedule/ScheduleListView"
import { SchedulePageProvider } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"

const LESSONS: Lesson[] = [
  {
    id: "l1",
    weekday: "monday",
    parity: "both",
    start_time: "09:00",
    end_time: "10:30",
    subject: "Linear Algebra",
    teacher: "Dr. Ivanova",
    room: "ГУК-305",
    lesson_type: "lecture",
    group_id: "g1",
  },
  {
    id: "l2",
    weekday: "tuesday",
    parity: "both",
    start_time: "10:45",
    end_time: "12:15",
    subject: "Discrete Mathematics",
    teacher: "Prof. Petrov",
    room: "ЛК-201",
    lesson_type: "practice",
    group_id: "g1",
  },
]

const baseProps = {
  schedule: LESSONS,
  weekdayBackend: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
  weekdayLabels: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  hasToday: true,
  todayIdx: 0,
  rawSchedule: LESSONS,
  refresh: vi.fn(),
  user: null,
  conflictedIds: new Set<string>(),
  isOnline: true,
  onDeleteLesson: vi.fn(),
  getLessonTypeColor: () => "#6366f1",
  getLessonTypeLabel: (v?: string | null) => v ?? "Lesson",
  currentLesson: null,
  currentProgress: 0,
  notesMap: new Map<string, boolean>(),
}

function renderView(props = baseProps) {
  return render(
    <SchedulePageProvider>
      <ScheduleListView {...props} />
    </SchedulePageProvider>
  )
}

describe("ScheduleListView", () => {
  it("renders day headings and lesson subjects grouped by day", () => {
    renderView()
    expect(screen.getByRole("heading", { name: "Monday" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Tuesday" })).toBeInTheDocument()
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.getByText("Discrete Mathematics")).toBeInTheDocument()
  })

  it("renders the empty state when there are no lessons", () => {
    renderView({ ...baseProps, schedule: [] })
    expect(screen.getByText("schedule:list.noLessons")).toBeInTheDocument()
  })

  it("renders an offline fallback when offline with no cached schedule", () => {
    renderView({ ...baseProps, schedule: [], rawSchedule: [], isOnline: false })
    expect(screen.queryByText("schedule:list.noLessons")).not.toBeInTheDocument()
  })
})
