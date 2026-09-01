import { fireEvent, render, screen, within } from "@testing-library/react"
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
const translationCalls = vi.hoisted(() => ({
  entries: [] as Array<{ key: string; options?: Record<string, unknown> }>,
}))
const translationNamespaces = vi.hoisted(() => ({ calls: [] as unknown[] }))
const parseMinutesCalls = vi.hoisted(() => ({ values: [] as string[] }))
const { preloadRoute, routerState } = vi.hoisted(() => {
  const routePreload = vi.fn()
  return { preloadRoute: routePreload, routerState: { current: { preloadRoute: routePreload } } }
})

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationNamespaces.calls.push(namespaces)
    return {
      t: (key: string, options?: Record<string, unknown>) => {
        translationCalls.entries.push({ key, options })
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
    }
  },
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
  useRouter: () => routerState.current,
}))

vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => scheduleState.current,
}))

vi.mock("@/utils/scheduleUtils", () => ({
  fmtTime: (value: string) => value,
  nowParity: () => "odd",
  parseMinutes: (value: string) => {
    parseMinutesCalls.values.push(value)
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

import { calculateLessonProgress, findNextLesson, ScheduleCard } from "../ScheduleCard"

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
    translationCalls.entries = []
    translationNamespaces.calls = []
    parseMinutesCalls.values = []
    routerState.current = { preloadRoute }
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
    expect(screen.queryByText("dashboard:noClasses")).not.toBeInTheDocument()
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
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

  it("passes an empty string to the time parser for each missing bound", () => {
    const time = new Date(2026, 6, 31, 9, 0)
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "missing-start",
          subject: "Missing start",
          start_time: undefined,
          end_time: "11:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    const first = render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)
    expect(parseMinutesCalls.values).toContain("")
    first.unmount()

    parseMinutesCalls.values = []
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "missing-end",
          subject: "Missing end",
          start_time: "12:00",
          end_time: undefined,
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)
    expect(parseMinutesCalls.values).toContain("")
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
    expect(screen.queryByText("dashboard:next")).not.toBeInTheDocument()
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
    expect(screen.getAllByText("Networks").length).toBeGreaterThan(0)
  })

  it("selects the first lesson after the active interval and skips overlaps, adjacency, and malformed bounds", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    const current = lessonFor(time, { id: "current", subject: "Current lesson" })
    const overlap = lessonFor(time, {
      id: "overlap",
      subject: "Overlapping lesson",
      start_time: "10:45",
      end_time: "11:30",
    })
    const adjacent = lessonFor(time, {
      id: "adjacent",
      subject: "Adjacent lesson",
      start_time: "11:00",
      end_time: "12:00",
    })
    const malformed = lessonFor(time, {
      id: "malformed",
      subject: "Malformed candidate",
      start_time: "bad",
      end_time: "12:00",
    })
    const later = lessonFor(time, {
      id: "later",
      subject: "First non-overlapping lesson",
      start_time: "12:30",
      end_time: "13:30",
    })

    expect(
      findNextLesson([current, overlap, adjacent, malformed, later], current, 10 * 60 + 30)
    ).toBe(later)
  })

  it("keeps a lesson that starts now out of the next slot when no current lesson is supplied", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    const startsNow = lessonFor(time, {
      id: "starts-now",
      subject: "Starts now",
      start_time: "10:30",
      end_time: "11:30",
    })
    const later = lessonFor(time, {
      id: "later",
      subject: "Later lesson",
      start_time: "12:00",
      end_time: "13:00",
    })

    expect(findNextLesson([startsNow, later], null, 10 * 60 + 30)).toBe(later)
  })

  it("clamps lesson progress to the validated interval", () => {
    const bounds = { start: 10 * 60, end: 11 * 60 }

    expect(calculateLessonProgress(null, 10 * 60 + 30)).toBe(0)
    expect(calculateLessonProgress(bounds, 9 * 60)).toBe(0)
    expect(calculateLessonProgress(bounds, 10 * 60 + 30)).toBe(50)
    expect(calculateLessonProgress(bounds, 12 * 60)).toBe(100)
  })

  it("does not promote malformed times to current or next lessons", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "bad-time",
          subject: "Malformed time",
          start_time: "bad",
          end_time: "11:00",
        }),
        lessonFor(time, {
          id: "valid-next",
          subject: "Valid next lesson",
          start_time: "12:00",
          end_time: "13:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Malformed time").length).toBeGreaterThan(0)
    expect(screen.queryByText("dashboard:now")).not.toBeInTheDocument()
    const nextBadge = screen.getByText("dashboard:next")
    expect(within(nextBadge.parentElement!).getByText("Valid next lesson")).toBeInTheDocument()
    expect(within(nextBadge.parentElement!).queryByText("Malformed time")).not.toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
  })

  it("rejects an invalid end time even when the start time is valid", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "bad-end",
          subject: "Malformed end",
          start_time: "10:00",
          end_time: "bad",
        }),
        lessonFor(time, {
          id: "valid-next",
          subject: "Valid next after malformed end",
          start_time: "12:00",
          end_time: "13:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.queryByText("dashboard:now")).not.toBeInTheDocument()
    const nextBadge = screen.getByText("dashboard:next")
    expect(
      within(nextBadge.parentElement!).getByText("Valid next after malformed end")
    ).toBeInTheDocument()
    expect(within(nextBadge.parentElement!).queryByText("Malformed end")).not.toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
  })

  it("does not promote a zero-length interval to the next lesson", () => {
    const time = new Date(2026, 6, 31, 9, 0)
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "zero-length",
          subject: "Zero-length interval",
          start_time: "10:00",
          end_time: "10:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getByText("Zero-length interval")).toBeInTheDocument()
    expect(screen.queryByText("dashboard:next")).not.toBeInTheDocument()
    expect(screen.queryByText("dashboard:now")).not.toBeInTheDocument()
  })

  it("normalizes uppercase backend weekdays and filters parity", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, { id: "upper", subject: "Uppercase weekday", weekday: "MONDAY" }),
        lessonFor(time, { id: "odd", subject: "Odd parity", parity: "odd" }),
        lessonFor(time, { id: "even", subject: "Even parity", parity: "even" }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.getAllByText("Uppercase weekday").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Odd parity").length).toBeGreaterThan(0)
    expect(screen.queryByText("Even parity")).not.toBeInTheDocument()
  })

  it("accepts every English backend weekday name", () => {
    dayNames.forEach((weekday, index) => {
      const time = new Date(2026, 6, 26 + index, 10, 30)
      scheduleState.current = {
        data: [lessonFor(time, { id: weekday, subject: `Lesson ${weekday}`, weekday })],
        isLoading: false,
        isFetching: false,
      }

      const { unmount } = render(
        <ScheduleCard time={time} userRole="student" userGroupId="group-1" />
      )
      expect(screen.getAllByText(`Lesson ${weekday}`).length).toBeGreaterThan(0)
      unmount()
    })
  })

  it("sorts matching lessons and preserves metadata interpolation", () => {
    const time = new Date(2026, 6, 31, 8, 30)
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "late",
          subject: "Later subject",
          start_time: "11:00",
          end_time: "12:00",
          teacher: "Prof. Later",
          room: "B-202",
        }),
        lessonFor(time, {
          id: "early",
          subject: "Earlier subject",
          start_time: "09:00",
          end_time: "10:00",
          teacher: "Dr. Early",
          room: "A-101",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    const { container } = render(
      <ScheduleCard time={time} userRole="student" userGroupId="group-1" />
    )
    const listItems = Array.from(container.querySelectorAll("ul > li"))
    expect(listItems).toHaveLength(2)
    expect(screen.queryByText("dashboard:noClasses")).not.toBeInTheDocument()
    expect(screen.getByRole("list")).toBeInTheDocument()
    expect(listItems[0]).toHaveClass("dash-list-item", "px-0", "py-0")
    expect(listItems[0]?.firstElementChild).toHaveClass(
      "list-item-blue",
      "list-item-blue-hover",
      "flex",
      "flex-col",
      "cursor-default"
    )
    expect(listItems[0]).toHaveTextContent("Earlier subject")
    expect(listItems[1]).toHaveTextContent("Later subject")

    const metadataCalls = translationCalls.entries.filter(
      (entry) => entry.key === "dashboard:lessonMeta"
    )
    expect(metadataCalls).toEqual(
      expect.arrayContaining([
        { key: "dashboard:lessonMeta", options: { teacher: "Dr. Early", room: "A-101" } },
        { key: "dashboard:lessonMeta", options: { teacher: "Prof. Later", room: "B-202" } },
      ])
    )
  })

  it("keeps dashboard shell classes and refetch state stable", () => {
    const time = new Date(2026, 6, 31, 10, 30)
    scheduleState.current = {
      data: [lessonFor(time)],
      isLoading: false,
      isFetching: false,
    }

    render(
      <ScheduleCard
        time={time}
        userRole="student"
        userGroupId="group-1"
        className="custom-card"
        style={{ color: "red" }}
        data-fade="true"
      />
    )

    const card = screen.getByRole("article")
    expect(card).toHaveClass(
      "glass-noise",
      "refetch-shimmer",
      "dash-border-shimmer",
      "dash-panel-schedule",
      "custom-card"
    )
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "false")
    expect(card).toHaveAttribute("data-fade", "true")
    expect(card).toHaveStyle({ color: "rgb(255, 0, 0)" })
    expect(screen.getByRole("heading")).toHaveClass("font-extrabold")
    expect(screen.getByRole("heading")).toHaveAttribute(
      "style",
      expect.stringContaining("font-size: clamp(1.35rem, 2.5vw, 1.75rem)")
    )
    expect(screen.getByText("dashboard:fullSchedule")).toBeInTheDocument()
    expect(translationNamespaces.calls).toContainEqual(["dashboard", "common"])
    expect(screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" })).toHaveClass(
      "btn-dash",
      "whitespace-nowrap",
      "px-5",
      "transition-transform",
      "duration-base",
      "hover:-translate-y-0.5"
    )
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

  it("uses every source English weekday when translated arrays are unavailable", () => {
    translationState.useArrays = false

    dayNames.forEach((weekday, index) => {
      const time = new Date(2026, 6, 26 + index, 10, 30)
      scheduleState.current = {
        data: [lessonFor(time, { id: `fallback-${weekday}`, subject: `Fallback ${weekday}` })],
        isLoading: false,
        isFetching: false,
      }

      const { unmount } = render(
        <ScheduleCard time={time} userRole="student" userGroupId="group-1" />
      )
      expect(screen.getAllByText(`Fallback ${weekday}`).length).toBeGreaterThan(0)
      unmount()
    })
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

  it("keeps English backend weekday aliases when the locale uses non-English names", () => {
    translationState.displayOverride = [
      "воскресенье",
      "понедельник",
      "вторник",
      "среда",
      "четверг",
      "пятница",
      "суббота",
    ]
    translationState.rawOverride = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"]

    dayNames.forEach((weekday, index) => {
      const time = new Date(2026, 6, 26 + index, 10, 30)
      scheduleState.current = {
        data: [lessonFor(time, { id: `english-${weekday}`, subject: `English ${weekday}` })],
        isLoading: false,
        isFetching: false,
      }

      const { unmount } = render(
        <ScheduleCard time={time} userRole="student" userGroupId="group-1" />
      )
      expect(screen.getAllByText(`English ${weekday}`).length).toBeGreaterThan(0)
      unmount()
    })
  })

  it("rejects an empty weekday while a translated label happens to contain filler text", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    translationState.displayOverride = [
      "воскресенье",
      "Stryker was here!",
      "вторник",
      "среда",
      "четверг",
      "пятница",
      "суббота",
    ]
    translationState.rawOverride = [...translationState.displayOverride]
    scheduleState.current = {
      data: [
        lessonFor(time, { id: "empty-weekday", subject: "Empty weekday", weekday: undefined }),
      ],
      isLoading: false,
      isFetching: false,
    }

    render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

    expect(screen.queryByText("Empty weekday")).not.toBeInTheDocument()
    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()
  })

  it("recomputes the weekday map when locale labels change during a mounted card", () => {
    const time = new Date(2026, 6, 27, 10, 30)
    translationState.displayOverride = [
      "воскресенье",
      "старый-понедельник",
      "вторник",
      "среда",
      "четверг",
      "пятница",
      "суббота",
    ]
    translationState.rawOverride = [...translationState.displayOverride]
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "old-weekday",
          subject: "Old localized lesson",
          weekday: "старый-понедельник",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    const { rerender } = render(
      <ScheduleCard time={time} userRole="student" userGroupId="group-1" />
    )
    expect(screen.getAllByText("Old localized lesson").length).toBeGreaterThan(0)

    translationState.displayOverride = [
      "воскресенье",
      "новый-понедельник",
      "вторник",
      "среда",
      "четверг",
      "пятница",
      "суббота",
    ]
    translationState.rawOverride = [...translationState.displayOverride]
    scheduleState.current = {
      data: [
        lessonFor(time, {
          id: "new-weekday",
          subject: "New localized lesson",
          weekday: "новый-понедельник",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }
    rerender(
      <ScheduleCard time={new Date(time.getTime())} userRole="student" userGroupId="group-1" />
    )

    expect(screen.getAllByText("New localized lesson").length).toBeGreaterThan(0)
    expect(screen.queryByText("dashboard:noClasses")).not.toBeInTheDocument()
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

  it("updates the next lesson when the clock moves past the first candidate", () => {
    const firstTime = new Date(2026, 6, 27, 9, 0)
    const secondTime = new Date(2026, 6, 27, 11, 30)
    scheduleState.current = {
      data: [
        lessonFor(firstTime, { id: "first-next", subject: "First next", start_time: "10:00" }),
        lessonFor(firstTime, {
          id: "second-next",
          subject: "Second next",
          start_time: "12:00",
          end_time: "13:00",
        }),
      ],
      isLoading: false,
      isFetching: false,
    }

    const { rerender } = render(
      <ScheduleCard time={firstTime} userRole="student" userGroupId="group-1" />
    )
    expect(screen.getByText("dashboard:next")).toBeInTheDocument()
    expect(screen.getAllByText("First next").length).toBeGreaterThan(0)

    rerender(<ScheduleCard time={secondTime} userRole="student" userGroupId="group-1" />)
    const nextBadge = screen.getByText("dashboard:next")
    expect(within(nextBadge.parentElement!).getByText("Second next")).toBeInTheDocument()
    expect(within(nextBadge.parentElement!).queryByText("First next")).not.toBeInTheDocument()
  })

  it("updates current lesson progress when the clock moves within the same interval", () => {
    const firstTime = new Date(2026, 6, 27, 10, 15)
    const secondTime = new Date(2026, 6, 27, 10, 45)
    scheduleState.current = {
      data: [lessonFor(firstTime, { id: "progress", start_time: "10:00", end_time: "11:00" })],
      isLoading: false,
      isFetching: false,
    }

    const { rerender } = render(
      <ScheduleCard time={firstTime} userRole="student" userGroupId="group-1" />
    )
    expect(screen.getByRole("progressbar")).toHaveValue(25)

    rerender(<ScheduleCard time={secondTime} userRole="student" userGroupId="group-1" />)
    expect(screen.getByRole("progressbar")).toHaveValue(75)
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

  it("refreshes the route preloader when the router object changes", () => {
    const firstPreload = vi.fn().mockResolvedValue(undefined)
    const secondPreload = vi.fn().mockResolvedValue(undefined)
    routerState.current = { preloadRoute: firstPreload }

    const { rerender } = renderCard({ userRole: "student", userGroupId: "group-1" })
    routerState.current = { preloadRoute: secondPreload }
    rerender(<ScheduleCard time={new Date(2026, 6, 31, 10, 30)} />)

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" }))
    expect(secondPreload).toHaveBeenCalledWith({ to: "/schedule" })
    expect(firstPreload).not.toHaveBeenCalled()
  })

  it("absorbs a rejected schedule route warmup", async () => {
    preloadRoute.mockRejectedValueOnce(new Error("route chunk unavailable"))
    renderCard({ userRole: "student", userGroupId: "group-1" })

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.openFullSchedule" }))
    await Promise.resolve()
    expect(preloadRoute).toHaveBeenCalledWith({ to: "/schedule" })
  })
})
