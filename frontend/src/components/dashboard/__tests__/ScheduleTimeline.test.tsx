import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useCountUp", () => ({
  useCountUp: (n: number) => ({ ref: { current: null }, value: n }),
}))

import { ScheduleTimeline } from "@/components/dashboard/ScheduleTimeline"
import type { DashboardLesson } from "@/hooks/useDashboardSchedule"

const LESSONS: DashboardLesson[] = [
  {
    id: "l1",
    subject: "Linear Algebra",
    teacher: "Dr. Ivanova",
    room: "ГУК-305",
    lesson_type: "lecture",
    weekday: "monday",
    start_time: "09:00",
    end_time: "10:30",
    parity: "both",
  },
  {
    id: "l2",
    subject: "Discrete Mathematics",
    teacher: "Prof. Petrov",
    room: "ЛК-201",
    lesson_type: "practice",
    weekday: "monday",
    start_time: "10:45",
    end_time: "12:15",
    parity: "both",
  },
]

const baseProps = {
  lessons: LESSONS,
  minutesNow: 600,
  currentLesson: null,
  nextLesson: null,
}

describe("ScheduleTimeline", () => {
  it("renders a lesson block per in-range lesson", () => {
    render(<ScheduleTimeline {...baseProps} />)
    expect(screen.getByRole("img", { name: /Linear Algebra/ })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /Discrete Mathematics/ })).toBeInTheDocument()
  })

  it("renders the now-indicator legend", () => {
    render(<ScheduleTimeline {...baseProps} />)
    expect(screen.getByText("dashboard:now")).toBeInTheDocument()
  })

  it("renders the lesson-count legend when lessons are present", () => {
    render(<ScheduleTimeline {...baseProps} />)
    expect(screen.getByText(/dashboard:timeline\.lessonCount/)).toBeInTheDocument()
  })

  it("renders a current-lesson block when a lesson is current", () => {
    render(<ScheduleTimeline {...baseProps} currentLesson={LESSONS[0]!} />)
    expect(screen.getByRole("img", { name: /Linear Algebra/ })).toBeInTheDocument()
  })

  it("renders no lesson blocks when there are no lessons", () => {
    render(<ScheduleTimeline {...baseProps} lessons={[]} />)
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(screen.getByText("dashboard:now")).toBeInTheDocument()
  })
})
