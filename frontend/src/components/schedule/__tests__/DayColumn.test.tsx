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

import { DayColumn } from "@/components/schedule/DayColumn"
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
    weekday: "monday",
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
  day: "monday",
  label: "Monday",
  lessons: LESSONS,
  isToday: false,
  isOnline: true,
  hasSchedule: true,
  userRole: "student",
  conflictedIds: new Set<string>(),
  notesMap: new Map<string, boolean>(),
  onAdd: vi.fn(),
  onLessonDelete: vi.fn(),
  onRetry: vi.fn(),
  getLessonTypeColor: () => "#6366f1",
  getLessonTypeLabel: (v?: string | null) => v ?? "Lesson",
}

describe("DayColumn", () => {
  it("renders the day label, count badge, and lesson subjects", () => {
    render(<DayColumn {...baseProps} />)
    expect(screen.getByRole("heading", { name: "Monday" })).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.getByText("Discrete Mathematics")).toBeInTheDocument()
  })

  it("renders the empty state when there are no lessons", () => {
    render(<DayColumn {...baseProps} lessons={[]} />)
    expect(screen.getByText("schedule:mobile.noLessons")).toBeInTheDocument()
  })

  it("renders an offline fallback when offline with no cached schedule", () => {
    render(<DayColumn {...baseProps} lessons={[]} isOnline={false} hasSchedule={false} />)
    expect(screen.queryByText("schedule:mobile.noLessons")).not.toBeInTheDocument()
  })

  it("shows an add button and fires onAdd for editors", async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<DayColumn {...baseProps} userRole="admin" onAdd={onAdd} />)
    await user.click(screen.getByLabelText("schedule:aria.addLesson"))
    expect(onAdd).toHaveBeenCalledOnce()
  })

  it("hides the add button for students", () => {
    render(<DayColumn {...baseProps} />)
    expect(screen.queryByLabelText("schedule:aria.addLesson")).not.toBeInTheDocument()
  })
})
