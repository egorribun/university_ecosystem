import { createElement, type ComponentProps, type ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

const mockedDayColumn = vi.hoisted(() => vi.fn())

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
vi.mock("@/components/schedule/DayColumn", () => ({
  DayColumn: (props: Record<string, unknown>) => {
    mockedDayColumn(props)
    return createElement(
      "section",
      { "data-testid": `stub-day-${String(props.day)}` },
      createElement("h2", null, props.label as ReactNode)
    )
  },
}))

import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { SchedulePageProvider } from "@/contexts/SchedulePageContext"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import type { User } from "@/types/User"

type Props = ComponentProps<typeof ScheduleMobileView>

const LESSONS: Lesson[] = [
  {
    id: "monday-lesson",
    weekday: "monday",
    parity: "both",
    start_time: "09:00",
    end_time: "10:30",
    subject: "Linear Algebra",
  },
]

const baseProps: Props = {
  schedule: LESSONS,
  weekdayBackend: ["monday", "tuesday"],
  weekdayLabels: ["Monday", "Tuesday"],
  weekdayShort: ["Mon", "Tue"],
  hasToday: true,
  todayIdx: 0,
  getDayLabel: (day: string) => day,
  rawSchedule: LESSONS,
  refresh: vi.fn(),
  user: null as User | null,
  conflictedIds: new Set<string>(),
  isOnline: true,
  onDeleteLesson: vi.fn(),
  getLessonTypeColor: () => "#6366f1",
  getLessonTypeLabel: (value?: string | null) => value ?? "Lesson",
  currentLesson: null,
  currentProgress: 0,
  notesMap: new Map<string, boolean>(),
  todayComplete: true,
}

function renderView(props: Props = baseProps) {
  return render(
    <SchedulePageProvider>
      <ScheduleMobileView {...props} />
    </SchedulePageProvider>
  )
}

afterEach(() => {
  mockedDayColumn.mockClear()
  useScheduleUIStore.setState({ weekOffset: 0 })
})

describe("ScheduleMobileView mutation contracts", () => {
  it("passes completion only to today's active panel and keeps optional refs safe", async () => {
    const user = userEvent.setup()
    renderView()

    const firstCall = mockedDayColumn.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(firstCall.day).toBe("monday")
    expect(firstCall.isToday).toBe(true)
    expect(firstCall.dayComplete).toBe(true)
    expect(screen.getByTestId("stub-day-monday")).toBeInTheDocument()

    // The stub deliberately does not attach the ref callback. A tab switch
    // must still succeed because scrolling an unmounted panel is optional.
    await expect(user.click(screen.getByRole("tab", { name: /Tue/ }))).resolves.toBeUndefined()

    const secondCall = mockedDayColumn.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(secondCall.day).toBe("tuesday")
    expect(secondCall.isToday).toBe(false)
    expect(secondCall.dayComplete).toBe(false)
  })

  it("does not mark a non-today panel complete when the completion flag is true", () => {
    renderView({ ...baseProps, hasToday: false, todayIdx: -1, todayComplete: true })

    const call = mockedDayColumn.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(call.isToday).toBe(false)
    expect(call.dayComplete).toBe(false)
  })
})
