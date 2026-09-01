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

const translationState = vi.hoisted(() => ({
  useArrays: true,
  displayOverride: undefined as string[] | undefined,
  rawOverride: undefined as string[] | undefined,
}))
const preloadRoute = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) => {
      if (
        options?.returnObjects &&
        translationState.useArrays &&
        (key === "dashboard:weekDays.display" || key === "dashboard:weekDays.raw")
      ) {
        if (key === "dashboard:weekDays.display" && translationState.displayOverride) {
          return translationState.displayOverride
        }
        if (key === "dashboard:weekDays.raw" && translationState.rawOverride) {
          return translationState.rawOverride
        }
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
  useRouter: () => ({ preloadRoute }),
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
    translationState.displayOverride = undefined
    translationState.rawOverride = undefined
    preloadRoute.mockReset()
    preloadRoute.mockResolvedValue(undefined)
  })

  it("does not mount perpetual decorative animations", () => {
    const { container } = renderCard()

    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector(".dash-orb-reactive")).toBeNull()
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

  it("keeps cached lessons visible while a student schedule refetches", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [lessonFor(time, { subject: "Cached lesson" })],
      isLoading: true,
      isFetching: true,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    const card = screen.getByRole("article")
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "false")
    expect(screen.queryByTestId("schedule-skeleton")).not.toBeInTheDocument()
    expect(screen.getAllByText("Cached lesson").length).toBeGreaterThan(0)
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

  it("matches a localized display weekday when the translated arrays are complete", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    translationState.displayOverride = [
      "воскресенье",
      "понедельник",
      "вторник",
      "среда",
      "четверг",
      "пятница",
      "суббота",
    ]
    scheduleState.current = {
      data: [lessonFor(time, { weekday: "понедельник", subject: "Localized display" })],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Localized display").length).toBeGreaterThan(0)
  })

  it("matches a localized raw weekday when the translated arrays are complete", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    translationState.rawOverride = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"]
    scheduleState.current = {
      data: [lessonFor(time, { weekday: "пн", subject: "Localized raw" })],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Localized raw").length).toBeGreaterThan(0)
  })

  it("rejects translated weekday arrays with the wrong length", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    translationState.displayOverride = ["вс", "пн", "вт", "ср", "чт", "пт"]
    translationState.rawOverride = ["sun", "mon", "tue", "wed", "thu", "fri"]
    scheduleState.current = {
      data: [lessonFor(time, { weekday: "пн", subject: "Malformed translation" })],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.queryByText("Malformed translation")).not.toBeInTheDocument()
    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()
  })

  it("treats lesson intervals as half-open at their start and end", () => {
    const lessonTime = new Date(2026, 6, 27, 10, 0)
    scheduleState.current = {
      data: [lessonFor(lessonTime, { subject: "Boundary lesson" })],
      isLoading: false,
      isFetching: false,
    }

    const { rerender } = render(
      <ScheduleCard time={lessonTime} userRole="student" userGroupId="group-1" />
    )
    expect(screen.getByText("dashboard:now")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveValue(0)

    const lessonEnd = new Date(2026, 6, 27, 11, 0)
    rerender(<ScheduleCard time={lessonEnd} userRole="student" userGroupId="group-1" />)
    expect(screen.queryByText("dashboard:now")).not.toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
    expect(screen.getByText("Boundary lesson")).toBeInTheDocument()
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
    preloadRoute.mockRejectedValueOnce(new Error("route chunk unavailable"))
    renderCard({ userRole: "student", userGroupId: "group-1" })

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" }))
    await Promise.resolve()
    expect(preloadRoute).toHaveBeenCalledWith({ to: "/schedule" })
  })
})
