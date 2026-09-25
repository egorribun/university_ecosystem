import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const calls = vi.hoisted(() => ({
  namespaces: [] as unknown[][],
  sortableItems: [] as string[][],
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown[]) => {
    calls.namespaces.push(namespaces)
    return {
      t: (key: string) => key,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("@dnd-kit/core", () => ({
  closestCenter: vi.fn(),
  DndContext: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock("@dnd-kit/sortable", () => ({
  SortableContext: ({ items, children }: { items: string[]; children: ReactNode }) => {
    calls.sortableItems.push(items)
    return <div data-testid="sortable-items">{children}</div>
  },
  verticalListSortingStrategy: {},
}))

vi.mock("@/components/schedule/LessonCard", () => ({
  LessonCard: ({
    lesson,
    currentProgress,
  }: {
    lesson: { id: string; subject: string }
    currentProgress?: number
  }) => (
    <div data-testid={`lesson-${lesson.id}`} data-progress={String(currentProgress ?? 0)}>
      {lesson.subject}
    </div>
  ),
}))

vi.mock("@/components/schedule/DraggableLessonCard", () => ({
  DraggableLessonCard: ({
    lesson,
    currentProgress,
  }: {
    lesson: { id: string; subject: string }
    currentProgress?: number
  }) => (
    <div data-testid={`drag-lesson-${lesson.id}`} data-progress={String(currentProgress ?? 0)}>
      {lesson.subject}
    </div>
  ),
}))

vi.mock("@/components/feedback/OfflineFallback", () => ({
  default: ({ onRetry }: { onRetry: () => void }) => (
    <button type="button" onClick={onRetry}>
      schedule:offline.retry
    </button>
  ),
}))

import { DayColumn } from "@/components/schedule/DayColumn"
import type { Lesson } from "@/components/schedule/scheduleUtils"

const lesson = (id: string, start = "09:00"): Lesson => ({
  id,
  weekday: "monday",
  parity: "both",
  start_time: start,
  end_time: "10:30",
  subject: id,
  teacher: "Teacher",
  room: "101",
  lesson_type: "lecture",
  group_id: "g1",
})

const baseProps = {
  day: "monday",
  label: "Monday",
  lessons: [lesson("l1"), lesson("l2", "11:00")],
  isToday: false,
  isOnline: true,
  hasSchedule: true,
  userRole: "teacher",
  conflictedIds: new Set<string>(),
  notesMap: new Map<string, boolean>(),
  onAdd: vi.fn(),
  onLessonDelete: vi.fn(),
  onRetry: vi.fn(),
  getLessonTypeColor: () => "#123456",
  getLessonTypeLabel: (value?: string | null) => value ?? "Lesson",
}

beforeEach(() => {
  calls.namespaces.length = 0
  calls.sortableItems.length = 0
})

afterEach(() => {
  vi.useRealTimers()
})

describe("DayColumn mutation contracts", () => {
  it("keeps translation namespaces and lesson-id memoization observable", () => {
    const { rerender } = render(<DayColumn {...baseProps} />)

    expect(calls.namespaces).toEqual(expect.arrayContaining([["schedule", "common"], ["schedule"]]))
    expect(calls.sortableItems.at(-1)).toEqual(["l1", "l2"])

    rerender(<DayColumn {...baseProps} lessons={[lesson("l3")]} />)
    expect(calls.sortableItems.at(-1)).toEqual(["l3"])
  })

  it("does not render a break marker when adjacent lessons have no gap", () => {
    render(<DayColumn {...baseProps} lessons={[lesson("l1", "09:00"), lesson("l2", "09:00")]} />)
    expect(screen.queryByText("schedule:break")).not.toBeInTheDocument()
  })

  it("keeps role, count, class, id, aria, and empty-state contracts distinct", () => {
    const parentClick = vi.fn()
    const onAdd = vi.fn()
    document.body.addEventListener("click", parentClick)
    const { rerender } = render(
      <DayColumn {...baseProps} lessons={[]} isToday userRole="admin" onAdd={onAdd} />
    )

    const panel = screen.getByRole("tabpanel")
    expect(panel).toHaveAttribute("id", "day-panel-monday")
    expect(panel).toHaveAttribute("aria-labelledby", "day-tab-monday")
    expect(panel).toHaveClass("sched-today-col", "p-5")
    expect(screen.getByLabelText("schedule:aria.addLesson")).toBeInTheDocument()
    expect(screen.getByText("schedule:mobile.noLessons")).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText("schedule:aria.addLesson"))
    expect(onAdd).toHaveBeenCalledOnce()
    expect(parentClick).not.toHaveBeenCalled()
    document.body.removeEventListener("click", parentClick)

    rerender(
      <DayColumn
        {...baseProps}
        lessons={[lesson("l3")]}
        isToday={false}
        userRole="student"
        compact
      />
    )
    expect(screen.getByRole("tabpanel")).toHaveClass("sched-heat-light", "p-4")
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.queryByLabelText("schedule:aria.addLesson")).not.toBeInTheDocument()
  })

  it("only selects the offline fallback for an offline unscheduled day", () => {
    const { rerender } = render(
      <DayColumn {...baseProps} lessons={[]} isOnline={false} hasSchedule={false} />
    )
    expect(screen.getByRole("button", { name: "schedule:offline.retry" })).toBeInTheDocument()

    rerender(<DayColumn {...baseProps} lessons={[]} isOnline={false} hasSchedule />)
    expect(screen.queryByRole("button", { name: "schedule:offline.retry" })).not.toBeInTheDocument()
    expect(screen.getByText("schedule:mobile.noLessons")).toBeInTheDocument()

    rerender(<DayColumn {...baseProps} lessons={[]} isOnline hasSchedule={false} />)
    expect(screen.queryByRole("button", { name: "schedule:offline.retry" })).not.toBeInTheDocument()
  })

  it("renders completion announcement and all confetti markers exactly once", () => {
    vi.useFakeTimers()
    render(<DayColumn {...baseProps} isToday dayComplete />)

    expect(screen.getByRole("status")).toHaveTextContent("schedule:dayComplete")
    expect(document.querySelectorAll(".sched-confetti-dot")).toHaveLength(6)
    act(() => vi.advanceTimersByTime(2000))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
