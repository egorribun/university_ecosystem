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
        data-testid="drag-first"
        onClick={() => onDragEnd({ active: { id: "l2" }, over: { id: "l1" } })}
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
        data-current={props.isCurrent ? "true" : "false"}
        data-draggable="false"
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
      <div
        id={`lesson-card-${lesson.id}`}
        data-progress={String(props.currentProgress ?? 0)}
        data-current={props.isCurrent ? "true" : "false"}
        data-draggable="true"
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
vi.mock("@/components/feedback/OfflineFallback", () => ({
  default: ({ onRetry }: { onRetry?: () => void }) => (
    <button type="button" onClick={onRetry}>
      schedule:offline.retry
    </button>
  ),
}))

import { DayColumn, getDayHeatClass, shouldCelebrateDay } from "@/components/schedule/DayColumn"
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

  it("keeps heatmap thresholds and celebration eligibility exact", () => {
    expect(getDayHeatClass(0)).toBe("")
    expect(getDayHeatClass(1)).toBe("sched-heat-light")
    expect(getDayHeatClass(2)).toBe("sched-heat-light")
    expect(getDayHeatClass(3)).toBe("sched-heat-medium")
    expect(getDayHeatClass(4)).toBe("sched-heat-medium")
    expect(getDayHeatClass(5)).toBe("sched-heat-heavy")
    expect(getDayHeatClass(6)).toBe("sched-heat-heavy")

    expect(shouldCelebrateDay(true, true, 1, false)).toBe(true)
    expect(shouldCelebrateDay(false, true, 1, false)).toBe(false)
    expect(shouldCelebrateDay(true, false, 1, false)).toBe(false)
    expect(shouldCelebrateDay(true, true, 0, false)).toBe(false)
    expect(shouldCelebrateDay(true, true, 1, true)).toBe(false)
  })

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
    await user.click(screen.getByTestId("drag-first"))
    await user.click(screen.getByTestId("drag-unknown"))
    expect(onLessonReorder).toHaveBeenCalledWith("l1", 1)
    expect(onLessonReorder).toHaveBeenCalledWith("l2", 0)
    expect(onLessonReorder).toHaveBeenCalledTimes(2)
    expect(screen.getByText("schedule:break")).toBeInTheDocument()
    expect(document.getElementById("lesson-card-l1")).toHaveAttribute("data-current", "false")
    expect(document.getElementById("lesson-card-l2")).toHaveAttribute("data-current", "true")
  })

  it("uses the explicit current progress while keeping inactive cards at zero", () => {
    render(<DayColumn {...baseProps} currentLessonId="l2" currentProgress={42} />)

    expect(document.getElementById("lesson-card-l1")).toHaveAttribute("data-progress", "0")
    expect(document.getElementById("lesson-card-l2")).toHaveAttribute("data-progress", "42")
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

    rerender(<DayColumn {...baseProps} lessons={[LESSONS[0]!]} isToday={false} />)
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-heat-light")

    rerender(<DayColumn {...baseProps} lessons={[]} isToday={false} />)
    expect(screen.getByRole("tabpanel")).not.toHaveClass(
      "sched-heat-heavy",
      "sched-heat-medium",
      "sched-heat-light"
    )

    rerender(
      <DayColumn {...baseProps} lessons={LESSONS} isToday dayComplete currentProgress={50} />
    )
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("schedule:dayComplete")
    )
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-today-col")
    expect(screen.getByRole("tabpanel")).not.toHaveClass("sched-heat-light")
    unmount()
  })

  it("separates viewer rendering, editor roles, and empty-state branches", async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const { rerender } = render(
      <DayColumn {...baseProps} lessons={[]} userRole="teacher" onAdd={onAdd} />
    )

    expect(screen.getByLabelText("schedule:aria.addLesson")).toBeInTheDocument()
    expect(screen.getByText("schedule:mobile.noLessons")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "schedule:offline.retry" })).not.toBeInTheDocument()
    expect(screen.queryByText("0")).not.toBeInTheDocument()
    await user.click(screen.getByLabelText("schedule:aria.addLesson"))
    expect(onAdd).toHaveBeenCalledTimes(1)

    rerender(<DayColumn {...baseProps} lessons={LESSONS} userRole="student" />)
    expect(screen.queryByTestId("drag-known")).not.toBeInTheDocument()
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.getByRole("tabpanel")).toHaveAttribute("id", "day-panel-monday")

    rerender(<DayColumn {...baseProps} lessons={[]} userRole="admin" />)
    expect(screen.getByLabelText("schedule:aria.addLesson")).toBeInTheDocument()
    rerender(<DayColumn {...baseProps} lessons={[]} userRole="student" isOnline={false} />)
    expect(screen.getByText("schedule:mobile.noLessons")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "schedule:offline.retry" })).not.toBeInTheDocument()
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
    act(() => vi.advanceTimersByTime(1999))
    expect(screen.getByRole("status")).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
