import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { ScheduleListView } from "@/components/schedule/ScheduleListView"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import type { User } from "@/types/User"

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

type Props = React.ComponentProps<typeof ScheduleListView>

const baseProps: Props = {
  schedule: LESSONS,
  weekdayBackend: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
  weekdayLabels: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  hasToday: true,
  todayIdx: 0,
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

function ContextProbe() {
  const { addDay, activeDialog } = useSchedulePage()
  return <div data-testid="schedule-context-probe">{`${addDay ?? ""}:${activeDialog ?? ""}`}</div>
}

function renderView(props: Props = baseProps, includeProbe = false) {
  return render(
    <SchedulePageProvider>
      <ScheduleListView {...props} />
      {includeProbe && <ContextProbe />}
    </SchedulePageProvider>
  )
}

beforeEach(() => {
  useScheduleUIStore.setState({ compactMode: false })
})

describe("ScheduleListView", () => {
  it("renders day headings and lesson subjects grouped by day", () => {
    renderView()
    expect(screen.getByRole("heading", { name: "Monday" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Tuesday" })).toBeInTheDocument()
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.getByText("Discrete Mathematics")).toBeInTheDocument()
  })

  it("renders the empty state when there are no lessons", () => {
    renderView({ ...baseProps, schedule: [] })
    expect(screen.getByText("schedule:list.noLessons")).toBeInTheDocument()
  })

  it("renders an offline fallback when offline with no cached schedule", () => {
    renderView({ ...baseProps, schedule: [], rawSchedule: [], isOnline: false })
    expect(screen.queryByText("schedule:list.noLessons")).not.toBeInTheDocument()
  })

  it("renders breaks and lesson state indicators while wiring editor actions", async () => {
    const user = userEvent.setup()
    const onDeleteLesson = vi.fn()
    const sameDaySchedule = [LESSONS[0]!, { ...LESSONS[1]!, weekday: "monday" }]

    renderView(
      {
        ...baseProps,
        schedule: sameDaySchedule,
        rawSchedule: sameDaySchedule,
        weekdayLabels: [],
        user: { role: "teacher" } as unknown as User,
        conflictedIds: new Set(["l1"]),
        currentLesson: sameDaySchedule[1]!,
        currentProgress: 42,
        notesMap: new Map([["l2", true]]),
        onDeleteLesson,
      },
      true
    )

    expect(screen.getByText("schedule:break")).toBeInTheDocument()
    expect(screen.getByText("schedule:lesson.conflict")).toBeInTheDocument()
    expect(screen.getByTitle("schedule:notes.hasNote")).toBeInTheDocument()

    const currentCard = document.getElementById("lesson-card-l2")
    expect(currentCard).toHaveAttribute("aria-current", "time")
    expect(currentCard?.getAttribute("style")).toContain("--sched-progress: 42")

    await user.click(screen.getAllByRole("button", { name: "schedule:actions.addLesson" })[0]!)
    expect(screen.getByTestId("schedule-context-probe")).toHaveTextContent("monday:add")

    await user.click(screen.getAllByRole("button", { name: "schedule:aria.deleteLesson" })[0]!)
    expect(onDeleteLesson).toHaveBeenCalledWith("l1")
  })

  it("defaults current progress to zero when the current lesson has no progress", () => {
    renderView({
      ...baseProps,
      currentLesson: LESSONS[0]!,
      // The hook's runtime data can transiently omit progress even though its public type is numeric.
      currentProgress: undefined as unknown as number,
    })

    expect(document.getElementById("lesson-card-l1")).toHaveAttribute("aria-current", "time")
    expect(document.getElementById("lesson-card-l1")?.getAttribute("style")).toContain(
      "--sched-progress: 0"
    )
  })
})
