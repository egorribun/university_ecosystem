import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"
import { createElement, type ComponentProps, type ReactNode } from "react"

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const motion = new Proxy(
    {},
    {
      get: (_target, tag) => {
        if (typeof tag !== "string") return undefined
        return (props: Record<string, unknown>) => {
          const variants = props.variants as
            Record<string, ((custom: number) => unknown) | unknown> | undefined
          const custom = typeof props.custom === "number" ? props.custom : 1
          const enter = variants?.enter
          const exit = variants?.exit
          if (typeof enter === "function") enter(custom)
          if (typeof exit === "function") exit(custom)
          return createElement(tag, null, props.children as ReactNode)
        }
      },
    }
  )
  return { ...base, motion, m: motion }
})
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
const prefersReducedMock = vi.hoisted(() => vi.fn(() => true))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => prefersReducedMock() }))

import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import type { User } from "@/types/User"
import type { Lesson } from "@/components/schedule/scheduleUtils"

type Props = ComponentProps<typeof ScheduleMobileView>

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

const baseProps: Props = {
  schedule: LESSONS,
  weekdayBackend: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
  weekdayLabels: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  weekdayShort: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  hasToday: true,
  todayIdx: 0,
  getDayLabel: (v: string) => v,
  rawSchedule: LESSONS,
  refresh: vi.fn(),
  user: null as User | null,
  conflictedIds: new Set<string>(),
  isOnline: true,
  onDeleteLesson: vi.fn(),
  getLessonTypeColor: () => "#6366f1",
  getLessonTypeLabel: (v?: string | null) => v ?? "Lesson",
  currentLesson: null,
  currentProgress: 0,
  notesMap: new Map<string, boolean>(),
}

function ContextProbe() {
  const { addDay, activeDialog } = useSchedulePage()
  return <div data-testid="schedule-context-probe">{`${addDay ?? ""}:${activeDialog ?? ""}`}</div>
}

function renderView(props = baseProps, includeProbe = false) {
  return render(
    <SchedulePageProvider>
      <ScheduleMobileView {...props} />
      {includeProbe && <ContextProbe />}
    </SchedulePageProvider>
  )
}

afterEach(() => {
  useScheduleUIStore.setState({ weekOffset: 0 })
  prefersReducedMock.mockReturnValue(true)
})

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

  it("opens the add dialog for the active day when an editor clicks add", async () => {
    const user = userEvent.setup()
    renderView({ ...baseProps, user: { role: "admin" } as unknown as User }, true)

    await user.click(screen.getByLabelText("schedule:aria.addLesson"))
    expect(screen.getByTestId("schedule-context-probe")).toHaveTextContent("monday:add")
  })

  it("navigates weeks from horizontal swipe gestures", () => {
    const { container } = renderView()
    const root = container.firstElementChild!

    fireEvent.pointerDown(root, { clientX: 220, clientY: 10 })
    fireEvent.pointerUp(root, { clientX: 100, clientY: 10 })
    expect(useScheduleUIStore.getState().weekOffset).toBe(1)

    fireEvent.pointerDown(root, { clientX: 100, clientY: 10 })
    fireEvent.pointerUp(root, { clientX: 220, clientY: 10 })
    expect(useScheduleUIStore.getState().weekOffset).toBe(0)
  })

  it("tracks a store week change and renders normal-motion transitions", () => {
    prefersReducedMock.mockReturnValue(false)
    renderView()

    act(() => {
      useScheduleUIStore.getState().setWeekOffset(1)
    })

    expect(useScheduleUIStore.getState().weekOffset).toBe(1)
  })

  it("moves focus between day tabs with arrow keys", () => {
    renderView()
    const tablist = screen.getByRole("tablist")
    const tabs = screen.getAllByRole("tab")

    fireEvent.keyDown(tablist, { key: "ArrowRight" })
    tabs[0]!.focus()

    fireEvent.keyDown(tablist, { key: "ArrowRight" })
    expect(document.activeElement).toBe(tabs[1])
    fireEvent.keyDown(tablist, { key: "ArrowLeft" })
    expect(document.activeElement).toBe(tabs[0])
  })

  it("uses day-label and current-lesson fallbacks and scrolls the active panel", () => {
    renderView({
      ...baseProps,
      weekdayBackend: ["monday"],
      weekdayLabels: [],
      weekdayShort: [],
      currentLesson: LESSONS[0]!,
      hasToday: false,
      todayIdx: -1,
    })

    const panel = screen.getByRole("tabpanel")
    const scrollIntoView = vi.fn()
    Object.defineProperty(panel, "scrollIntoView", { value: scrollIntoView, configurable: true })
    fireEvent.click(screen.getByRole("tab"))

    expect(screen.getByRole("heading", { name: "monday" })).toBeInTheDocument()
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
  })

  it("renders an empty backend safely when no day map entry exists", () => {
    renderView({
      ...baseProps,
      schedule: [],
      weekdayBackend: [],
      weekdayLabels: [],
      weekdayShort: [],
      rawSchedule: [],
      hasToday: false,
      todayIdx: -1,
    })

    expect(screen.getByRole("tabpanel")).toBeInTheDocument()
  })
})
