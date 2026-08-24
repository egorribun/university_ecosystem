import { fireEvent, render, screen } from "@testing-library/react"
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
vi.mock("@/components/schedule/FlipCountdown", () => ({
  FlipCountdown: ({ targetMinutes }: { targetMinutes: number }) => (
    <span data-testid="flip-countdown">{targetMinutes}</span>
  ),
}))

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
        timeLeftText="10 minutes"
        timeLeftShort="10m"
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

  it("shows next-lesson metadata, countdown, and the remaining-time chip", () => {
    render(
      <ScheduleHeader
        {...baseProps}
        nextLesson={lesson({ subject: "Soon Seminar", start_time: "10:15" })}
        timeLeftText="15 minutes"
        timeLeftShort="15m"
      />
    )

    expect(screen.getByText("Soon Seminar")).toBeInTheDocument()
    expect(screen.getByLabelText("15 minutes")).toHaveTextContent("15m")
    expect(screen.getByTestId("flip-countdown")).toHaveTextContent("615")
  })

  it("shows a day-complete message when nothing is current or next", () => {
    render(<ScheduleHeader {...baseProps} />)
    expect(screen.getByText("schedule:dayComplete")).toBeInTheDocument()
  })

  it("uses the empty-day message when there are no lessons", () => {
    render(<ScheduleHeader {...baseProps} todayLessons={[]} />)
    expect(screen.getByText("schedule:summary.noMoreToday")).toBeInTheDocument()
  })

  it("treats an omitted lesson list as an empty day", () => {
    render(<ScheduleHeader {...baseProps} todayLessons={undefined} />)
    expect(screen.getByText("schedule:summary.noMoreToday")).toBeInTheDocument()
  })

  it("uses the standard duration for lessons with invalid times", () => {
    render(
      <ScheduleHeader
        {...baseProps}
        todayLessons={[lesson({ start_time: "invalid", end_time: "also-invalid" })]}
      />
    )

    expect(screen.getByText("schedule:dayComplete")).toBeInTheDocument()
  })

  it("uses the compact progress ring on mobile", () => {
    mediaMock.mockReturnValue(true)
    render(
      <ScheduleHeader
        {...baseProps}
        currentLesson={lesson({ subject: "Mobile Lecture" })}
        currentProgress={40}
      />
    )

    expect(screen.getByText("Mobile Lecture")).toBeInTheDocument()
  })

  it("fires onOpenSettings when the controls button is clicked", async () => {
    const user = userEvent.setup()
    const onOpenSettings = vi.fn()
    render(<ScheduleHeader {...baseProps} onOpenSettings={onOpenSettings} />)
    await user.click(screen.getByRole("button", { name: "schedule:toolbar.settings" }))
    expect(onOpenSettings).toHaveBeenCalledOnce()
  })

  it("renders and updates the group selector for teachers", () => {
    const setSelectedGroup = vi.fn()
    render(
      <ScheduleHeader
        {...baseProps}
        groups={[...baseProps.groups, { id: "g2", name: "CS-2025" }]}
        setSelectedGroup={setSelectedGroup}
        user={
          { id: "1", email: "t@u.edu", full_name: "Teacher", role: "teacher" } as unknown as User
        }
      />
    )
    expect(screen.getByText("schedule:form.groupLabel")).toBeInTheDocument()

    const selector = screen.getByRole("combobox")
    fireEvent.click(selector)
    fireEvent.mouseDown(screen.getByRole("option", { name: "CS-2025" }))
    expect(setSelectedGroup).toHaveBeenCalledWith("g2")
  })

  it("normalizes an empty teacher group selection to null", () => {
    const setSelectedGroup = vi.fn()
    render(
      <ScheduleHeader
        {...baseProps}
        groups={[{ id: "", name: "No group" }]}
        selectedGroup={null}
        setSelectedGroup={setSelectedGroup}
        user={
          { id: "1", email: "t@u.edu", full_name: "Teacher", role: "teacher" } as unknown as User
        }
      />
    )

    const selector = screen.getByRole("combobox")
    fireEvent.click(selector)
    fireEvent.mouseDown(screen.getByRole("option", { name: "No group" }))
    expect(setSelectedGroup).toHaveBeenCalledWith(null)
  })

  it("omits the settings control when no callback is supplied", () => {
    render(<ScheduleHeader {...baseProps} onOpenSettings={undefined} />)
    expect(screen.queryByRole("button", { name: "schedule:toolbar.settings" })).toBeNull()
  })
})
