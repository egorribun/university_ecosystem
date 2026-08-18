import { fireEvent, render, screen } from "@testing-library/react"
import type { ElementType, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const scheduleState = vi.hoisted(() => ({
  current: {
    data: undefined as unknown[] | undefined,
    isLoading: false,
    isFetching: false,
  },
}))

const translationState = vi.hoisted(() => ({ useArrays: true }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) => {
      if (
        options?.returnObjects &&
        translationState.useArrays &&
        (key === "dashboard:weekDays.display" || key === "dashboard:weekDays.raw")
      ) {
        return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
      }
      return key
    },
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    ...props
  }: { children?: ReactNode; to?: unknown } & Record<string, unknown>) => (
    <a href={typeof to === "string" && to.length > 0 ? to : "/schedule"} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => scheduleState.current,
}))

vi.mock("@/utils/scheduleUtils", () => ({
  fmtTime: (value: string) => value,
  nowParity: () => "odd",
  parseMinutes: (value: string) => {
    const [hours = Number.NaN, minutes = Number.NaN] = value.split(":").map(Number)
    return Number.isFinite(hours) && Number.isFinite(minutes) ? hours * 60 + minutes : null
  },
}))

vi.mock("@/components/ui", () => {
  const Card = ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <article {...props}>{children}</article>
  )
  const Badge = ({ label }: { label: string }) => <span>{label}</span>
  const Button = ({
    as: Component = "button",
    children,
    ...props
  }: { as?: ElementType; children?: ReactNode } & Record<string, unknown>) => (
    <Component {...props}>{children}</Component>
  )
  const ProgressBar = ({ value, ariaLabel }: { value: number; ariaLabel: string }) => (
    <progress aria-label={ariaLabel} max={100} value={value} />
  )
  const Skeleton = ({ width, height }: { width: number | string; height: number }) => (
    <span data-testid="schedule-skeleton" data-width={width} data-height={height} />
  )
  return { Badge, Button, Card, ProgressBar, Skeleton }
})

import { ScheduleCard } from "../ScheduleCard"

const dayNames = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

const lessonFor = (time: Date, overrides: Record<string, unknown> = {}) => ({
  id: "lesson-1",
  subject: "Algorithms",
  teacher: "Dr. Ada",
  room: "A-101",
  lesson_type: "Lecture",
  weekday: dayNames[time.getDay()],
  start_time: "10:00",
  end_time: "11:00",
  parity: "both",
  ...overrides,
})

const renderCard = (props: Record<string, unknown> = {}) =>
  render(<ScheduleCard time={new Date(2026, 6, 31, 10, 30)} {...props} />)

describe("ScheduleCard", () => {
  beforeEach(() => {
    scheduleState.current = { data: undefined, isLoading: false, isFetching: false }
    translationState.useArrays = true
  })

  it("gates loading to student accounts with a group", () => {
    scheduleState.current = { data: undefined, isLoading: true, isFetching: false }

    renderCard({ userRole: "student", userGroupId: "group-1" })

    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "true")
    expect(screen.getAllByTestId("schedule-skeleton")).toHaveLength(9)
  })

  it("does not show a loading state for non-students or missing groups", () => {
    scheduleState.current = { data: undefined, isLoading: true, isFetching: false }

    renderCard({ userRole: "teacher", userGroupId: "group-1" })

    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "false")
    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()
  })

  it("renders the current lesson, progress, and sorted matching lessons", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, { id: "late", start_time: "12:00", end_time: "13:00" }),
        lessonFor(time, { id: "current", subject: "Databases" }),
        lessonFor(time, { id: "even", parity: "even", subject: "Even-only" }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Databases").length).toBeGreaterThan(0)
    expect(screen.getByRole("progressbar")).toHaveValue(50)
    expect(screen.getByText("dashboard:now")).toBeInTheDocument()
    expect(screen.getByText("Algorithms")).toBeInTheDocument()
    expect(screen.getAllByText("dashboard:lessonMeta").length).toBeGreaterThan(0)
    expect(screen.queryByText("Even-only")).not.toBeInTheDocument()
  })

  it("renders the next lesson when no lesson is currently active", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, { id: "next", subject: "Operating Systems", start_time: "12:00" }),
        lessonFor(time, {
          id: "later",
          subject: "Networks",
          start_time: "14:00",
          end_time: "15:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Operating Systems").length).toBeGreaterThan(0)
    expect(screen.getByText("dashboard:next")).toBeInTheDocument()
    expect(screen.getByText("Networks")).toBeInTheDocument()
  })

  it("uses the English fallback weekday arrays and shows an empty day", () => {
    translationState.useArrays = false
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [lessonFor(time, { weekday: "monday" })],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()
  })

  it("handles missing role/group and malformed weekday/time payloads safely", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [lessonFor(time, { weekday: undefined })],
      isLoading: false,
      isFetching: false,
    }
    const { rerender } = renderCard()
    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()

    scheduleState.current = {
      data: [lessonFor(time, { id: "malformed", start_time: "bad", end_time: "bad" })],
      isLoading: false,
      isFetching: false,
    }
    rerender(
      <ScheduleCard time={time} userRole="student" userGroupId="group-1" className="malformed" />
    )
    expect(screen.getAllByText("Algorithms").length).toBeGreaterThan(0)

    scheduleState.current = {
      data: [
        lessonFor(time, { id: "current" }),
        lessonFor(time, { id: "invalid-next", start_time: "bad", end_time: "bad" }),
      ],
      isLoading: false,
      isFetching: false,
    }
    rerender(
      <ScheduleCard time={time} userRole="student" userGroupId="group-1" className="current" />
    )
    expect(screen.getByText("dashboard:now")).toBeInTheDocument()

    scheduleState.current = {
      data: [lessonFor(time, { id: "invalid-only", start_time: "bad", end_time: "bad" })],
      isLoading: false,
      isFetching: false,
    }
    rerender(
      <ScheduleCard time={time} userRole="student" userGroupId="group-1" className="invalid" />
    )
    expect(screen.getAllByText("Algorithms").length).toBeGreaterThan(0)
  })

  it("marks background refetches and handles navigation keyboard contracts", () => {
    scheduleState.current = {
      data: [lessonFor(new Date(2026, 6, 31, 10, 30))],
      isLoading: false,
      isFetching: true,
    }

    renderCard({ userRole: "student", userGroupId: "group-1" })

    const card = screen.getByRole("article")
    expect(card).toHaveAttribute("data-refetching", "true")
    const link = screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" })
    fireEvent.pointerDown(link)
    fireEvent.keyDown(link, { key: "Enter" })
    fireEvent.keyDown(link, { key: " " })
    fireEvent.keyDown(link, { key: "Spacebar" })
    fireEvent.keyDown(link, { key: "Escape" })
  })

  it("absorbs a rejected schedule route warmup", async () => {
    vi.doMock("@/pages/Schedule", () => {
      throw new Error("route chunk unavailable")
    })
    renderCard({ userRole: "student", userGroupId: "group-1" })

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" }))
    await Promise.resolve()
  })
})
