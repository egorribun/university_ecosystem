import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const sortableState = vi.hoisted(() => ({
  isDragging: false,
  setNodeRef: vi.fn(),
  pointerDown: vi.fn(),
  useSortable: vi.fn(),
}))

vi.mock("@dnd-kit/sortable", () => ({
  useSortable: (options: { id: string; disabled: boolean }) => {
    sortableState.useSortable(options)
    return {
      attributes: { "data-dnd-attribute": "true" },
      listeners: { onPointerDown: sortableState.pointerDown },
      setNodeRef: sortableState.setNodeRef,
      transform: null,
      transition: "transform 200ms ease",
      isDragging: sortableState.isDragging,
    }
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { DraggableLessonCard } from "../DraggableLessonCard"
import type { Lesson } from "../scheduleUtils"

const lesson: Lesson = {
  id: "lesson-1",
  weekday: "Monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "101",
  lesson_type: "lecture",
}

const cardProps = {
  lesson,
  isConflict: false,
  onDelete: vi.fn(),
  getLessonTypeColor: vi.fn(() => "#6366f1"),
  getLessonTypeLabel: vi.fn(() => "Lecture"),
}

beforeEach(() => {
  sortableState.isDragging = false
  sortableState.setNodeRef.mockClear()
  sortableState.pointerDown.mockClear()
  sortableState.useSortable.mockClear()
})

describe("DraggableLessonCard", () => {
  it("renders a plain lesson card when dragging is disabled", () => {
    const { container } = render(<DraggableLessonCard dragId="lesson-1" {...cardProps} />)

    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "schedule:drag.handle" })).not.toBeInTheDocument()
    expect(container.querySelector(".sched-dragging")).not.toBeInTheDocument()
    expect(sortableState.useSortable).toHaveBeenCalledWith({ id: "lesson-1", disabled: true })
  })

  it("forwards drag bindings without the dragging class while idle", () => {
    const { container } = render(
      <DraggableLessonCard dragId="lesson-1" dragEnabled {...cardProps} />
    )

    const handle = screen.getByRole("button", { name: "schedule:drag.handle" })
    fireEvent.pointerDown(handle)

    expect(handle).toHaveAttribute("data-dnd-attribute", "true")
    expect(sortableState.pointerDown).toHaveBeenCalledOnce()
    expect(container.querySelector(".relative")).not.toHaveClass("sched-dragging")
    expect(sortableState.setNodeRef).toHaveBeenCalledWith(expect.any(HTMLDivElement))
    expect(sortableState.useSortable).toHaveBeenCalledWith({ id: "lesson-1", disabled: false })
  })

  it("marks the wrapper while dnd-kit reports an active drag", () => {
    sortableState.isDragging = true

    const { container } = render(
      <DraggableLessonCard dragId="lesson-1" dragEnabled {...cardProps} />
    )

    expect(container.querySelector(".sched-dragging")).toBeInTheDocument()
  })
})
