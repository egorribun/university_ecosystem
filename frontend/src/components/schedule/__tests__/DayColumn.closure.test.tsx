import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@dnd-kit/core", () => ({
  closestCenter: vi.fn(),
  DndContext: ({
    children,
    onDragEnd,
  }: {
    children: ReactNode
    onDragEnd: (event: unknown) => void
  }) => (
    <div>
      {children}
      <button
        type="button"
        data-testid="drag-no-over"
        onClick={() => onDragEnd({ active: { id: "l1" }, over: null })}
      />
      <button
        type="button"
        data-testid="drag-same"
        onClick={() => onDragEnd({ active: { id: "l1" }, over: { id: "l1" } })}
      />
      <button
        type="button"
        data-testid="drag-known"
        onClick={() => onDragEnd({ active: { id: "l1" }, over: { id: "l2" } })}
      />
      <button
        type="button"
        data-testid="drag-unknown"
        onClick={() => onDragEnd({ active: { id: "l1" }, over: { id: "missing" } })}
      />
    </div>
  ),
}))
vi.mock("@dnd-kit/sortable", () => ({
  SortableContext: ({ children }: { children: ReactNode }) => <>{children}</>,
  verticalListSortingStrategy: {},
}))

vi.mock("@/components/schedule/LessonCard", () => ({
  LessonCard: (props: Record<string, unknown>) => {
    const lesson = props.lesson as { id: string; subject: string }
    return (
      <div
        id={`lesson-card-${lesson.id}`}
        aria-current={props.isCurrent ? "time" : undefined}
        data-progress={String(props.currentProgress ?? 0)}
      >
        <span>{lesson.subject}</span>
        {Boolean(props.isConflict) && <span>schedule:lesson.conflict</span>}
        {Boolean(props.hasNote) && <span title="schedule:notes.hasNote">note</span>}
        {Boolean(props.canEdit) && (
          <button
            type="button"
            aria-label="schedule:aria.deleteLesson"
            onClick={props.onDelete as () => void}
          >
            delete
          </button>
        )}
      </div>
    )
  },
}))
vi.mock("@/components/schedule/DraggableLessonCard", () => ({
  DraggableLessonCard: (props: Record<string, unknown>) => {
    const lesson = props.lesson as { id: string; subject: string }
    return (
      <div id={`lesson-card-${lesson.id}`} data-progress={String(props.currentProgress ?? 0)}>
        <span>{lesson.subject}</span>
        {Boolean(props.isConflict) && <span>schedule:lesson.conflict</span>}
        {Boolean(props.hasNote) && <span title="schedule:notes.hasNote">note</span>}
        {Boolean(props.canEdit) && (
          <button
            type="button"
            aria-label="schedule:aria.deleteLesson"
            onClick={props.onDelete as () => void}
          >
            delete
          </button>
        )}
      </div>
    )
  },
}))
vi.mock("@/components/feedback/OfflineFallback", () => ({
  default: ({ onRetry }: { onRetry?: () => void }) => (
    <button type="button" onClick={onRetry}>
      schedule:offline.retry
    </button>
  ),
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
  userRole: "teacher",
  conflictedIds: new Set(["l1"]),
  notesMap: new Map([["l2", true]]),
  onAdd: vi.fn(),
  onLessonDelete: vi.fn(),
  onRetry: vi.fn(),
  getLessonTypeColor: () => "#6366f1",
  getLessonTypeLabel: (v?: string | null) => v ?? "Lesson",
}

describe("DayColumn closure paths", () => {
  afterEach(() => vi.useRealTimers())

  it("renders the offline fallback and forwards its retry action", async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(
      <DayColumn
        {...baseProps}
        lessons={[]}
        isOnline={false}
        hasSchedule={false}
        onRetry={onRetry}
      />
    )

    await user.click(screen.getByRole("button", { name: "schedule:offline.retry" }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("covers current-progress fallback, note/conflict/delete, and drag-end guards", async () => {
    const user = userEvent.setup()
    const onDeleteLesson = vi.fn()
    const onLessonReorder = vi.fn()
    render(
      <DayColumn
        {...baseProps}
        currentLessonId="l2"
        currentProgress={undefined}
        onLessonDelete={onDeleteLesson}
        onLessonReorder={onLessonReorder}
      />
    )

    expect(screen.getByText("schedule:lesson.conflict")).toBeInTheDocument()
    expect(screen.getByTitle("schedule:notes.hasNote")).toBeInTheDocument()
    expect(document.getElementById("lesson-card-l2")).toHaveAttribute("data-progress", "0")

    fireEvent.click(screen.getAllByRole("button", { name: "schedule:aria.deleteLesson" })[0]!)
    expect(onDeleteLesson).toHaveBeenCalledWith("l1")

    await user.click(screen.getByTestId("drag-no-over"))
    await user.click(screen.getByTestId("drag-same"))
    await user.click(screen.getByTestId("drag-known"))
    await user.click(screen.getByTestId("drag-unknown"))
    expect(onLessonReorder).toHaveBeenCalledWith("l1", 1)
    expect(onLessonReorder).toHaveBeenCalledTimes(1)
  })

  it("covers heavy/medium heatmaps, compact/today styling, and completion confetti", async () => {
    const manyLessons = Array.from({ length: 5 }, (_, index) => ({
      ...LESSONS[index % LESSONS.length]!,
      id: `heat-${index}`,
      start_time: `0${9 + index}:00`,
    }))
    const { rerender, unmount } = render(
      <DayColumn
        {...baseProps}
        lessons={manyLessons}
        isToday={false}
        compact
        currentProgress={25}
      />
    )
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-heat-heavy", "p-4")

    const mediumLessons = manyLessons.slice(0, 3)
    rerender(<DayColumn {...baseProps} lessons={mediumLessons} isToday={false} />)
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-heat-medium")

    rerender(
      <DayColumn {...baseProps} lessons={LESSONS} isToday dayComplete currentProgress={50} />
    )
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("schedule:dayComplete")
    )
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-today-col")
    unmount()
  })

  it("does not reorder when no reorder callback is supplied", async () => {
    const user = userEvent.setup()
    render(<DayColumn {...baseProps} onLessonReorder={undefined} />)
    await user.click(screen.getByTestId("drag-known"))
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
  })

  it("hides completion confetti after its announcement window", () => {
    vi.useFakeTimers()
    render(<DayColumn {...baseProps} isToday dayComplete />)

    expect(screen.getByRole("status")).toHaveTextContent("schedule:dayComplete")
    act(() => vi.advanceTimersByTime(2000))

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
