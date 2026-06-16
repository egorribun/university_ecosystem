import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock } = vi.hoisted(() => ({ mediaMock: vi.fn() }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaMock() }))

import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import type { User } from "@/types/User"

const lesson = (over: Partial<Lesson>): Lesson => ({
  id: "l1",
  weekday: "monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "ГУК-305",
  lesson_type: "lecture",
  ...over,
})

const baseProps = {
  user: { id: "1", email: "s@u.edu", full_name: "Test", role: "student" } as unknown as User,
  groups: [{ id: "g1", name: "CS-2024" }],
  selectedGroup: "g1",
  setSelectedGroup: vi.fn(),
  currentLesson: null,
  nextLesson: null,
  timeLeftText: "",
  timeLeftShort: "",
  currentProgress: 0,
  todayLessons: [lesson({})],
  nowTick: new Date("2026-06-15T10:00:00"),
  onOpenSettings: vi.fn(),
}

describe("ScheduleHeader", () => {
  beforeEach(() => {
    mediaMock.mockReset()
    mediaMock.mockReturnValue(false) // desktop
  })

  it("renders the student title and a current-lesson card", () => {
    render(
      <ScheduleHeader
        {...baseProps}
        currentLesson={lesson({ subject: "Active Lecture" })}
        currentProgress={40}
      />
    )
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("schedule:title.student")
    expect(screen.getByText("schedule:chips.current")).toBeInTheDocument()
    expect(screen.getByText("Active Lecture")).toBeInTheDocument()
  })

  it("renders a next-lesson card when there is no current lesson", () => {
    render(
      <ScheduleHeader
        {...baseProps}
        nextLesson={lesson({ subject: "Upcoming Seminar", start_time: "15:00" })}
      />
    )
    expect(screen.getByText("schedule:chips.next")).toBeInTheDocument()
    expect(screen.getByText("Upcoming Seminar")).toBeInTheDocument()
  })

  it("shows a day-complete message when nothing is current or next", () => {
    render(<ScheduleHeader {...baseProps} />)
    expect(screen.getByText("schedule:dayComplete")).toBeInTheDocument()
  })

  it("fires onOpenSettings when the controls button is clicked", async () => {
    const user = userEvent.setup()
    const onOpenSettings = vi.fn()
    render(<ScheduleHeader {...baseProps} onOpenSettings={onOpenSettings} />)
    await user.click(screen.getByRole("button", { name: "schedule:toolbar.settings" }))
    expect(onOpenSettings).toHaveBeenCalledOnce()
  })

  it("renders the group selector for teachers", () => {
    render(
      <ScheduleHeader
        {...baseProps}
        user={
          { id: "1", email: "t@u.edu", full_name: "Teacher", role: "teacher" } as unknown as User
        }
      />
    )
    expect(screen.getByText("schedule:form.groupLabel")).toBeInTheDocument()
  })
})
