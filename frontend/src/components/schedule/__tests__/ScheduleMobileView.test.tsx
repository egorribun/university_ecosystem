import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))

import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
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
  weekdayShort: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  hasToday: true,
  todayIdx: 0,
  getDayLabel: (v: string) => v,
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
      <ScheduleMobileView {...props} />
    </SchedulePageProvider>
  )
}

describe("ScheduleMobileView", () => {
  it("renders a day tab per weekday", () => {
    renderView()
    expect(screen.getAllByRole("tab")).toHaveLength(baseProps.weekdayBackend.length)
  })

  it("renders the active day's lessons in the day column", () => {
    renderView()
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
  })

  it("switches the active day when another tab is clicked", async () => {
    const user = userEvent.setup()
    renderView()
    await user.click(screen.getByRole("tab", { name: /Tue/ }))
    expect(screen.getByText("Discrete Mathematics")).toBeInTheDocument()
  })
})
