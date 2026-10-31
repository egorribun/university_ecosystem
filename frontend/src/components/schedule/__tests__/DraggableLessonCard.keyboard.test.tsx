import { closestCenter, DndContext } from "@dnd-kit/core"
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

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

function renderLesson(dragEnabled: boolean) {
  const onDragStart = vi.fn()
  const onDragCancel = vi.fn()
  const onDragEnd = vi.fn()
  const onDelete = vi.fn()
  render(
    <DndContext onDragStart={onDragStart} onDragCancel={onDragCancel} onDragEnd={onDragEnd}>
      <SortableContext items={[lesson.id]} strategy={verticalListSortingStrategy}>
        <DraggableLessonCard
          dragId={lesson.id}
          dragEnabled={dragEnabled}
          lesson={lesson}
          isConflict={false}
          canEdit
          onDelete={onDelete}
          getLessonTypeColor={() => "#6366f1"}
          getLessonTypeLabel={() => "Lecture"}
        />
      </SortableContext>
    </DndContext>
  )
  return { onDragStart, onDragCancel, onDragEnd, onDelete }
}

describe("DraggableLessonCard keyboard access", () => {
  it.each([
    ["Space", " "],
    ["Enter", "{Enter}"],
  ])("focuses the handle with Tab and starts a real drag with %s", async (_name, key) => {
    const user = userEvent.setup()
    const { onDragStart, onDragCancel } = renderLesson(true)
    const handle = screen.getByRole("button", { name: "Drag lesson" })

    await user.tab()
    expect(handle).toHaveFocus()
    expect(handle).toHaveAttribute("aria-disabled", "false")
    expect(handle).toHaveClass("focus-visible:opacity-100")
    expect(handle).toHaveClass("min-h-[44px]", "min-w-[44px]")

    await user.keyboard(key)
    expect(onDragStart).toHaveBeenCalledOnce()
    expect(onDragStart).toHaveBeenCalledWith(
      expect.objectContaining({ active: expect.objectContaining({ id: lesson.id }) })
    )

    await user.keyboard("{Escape}")
    expect(onDragCancel).toHaveBeenCalledOnce()
  })

  it("omits the drag handle when disabled without affecting the delete control", async () => {
    const user = userEvent.setup()
    const { onDragStart, onDelete } = renderLesson(false)
    expect(screen.queryByRole("button", { name: "Drag lesson" })).not.toBeInTheDocument()

    await user.tab()
    expect(screen.getByRole("button", { name: "Delete lesson" })).toHaveFocus()
    await user.keyboard(" ")
    expect(onDelete).toHaveBeenCalledOnce()
    expect(onDragStart).not.toHaveBeenCalled()
  })

  it("moves a lesson over the next card and drops it using the default keyboard sensor", async () => {
    const otherLesson = { ...lesson, id: "lesson-2", subject: "Geometry" }
    const nativeRect = HTMLElement.prototype.getBoundingClientRect
    const measure = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: HTMLElement) {
        if (this.classList.contains("relative")) {
          if (this.querySelector("#lesson-card-lesson-1")) return new DOMRect(0, 0, 100, 20)
          if (this.querySelector("#lesson-card-lesson-2")) return new DOMRect(0, 50, 100, 20)
        }
        return nativeRect.call(this)
      })
    try {
      const user = userEvent.setup()
      const onDragEnd = vi.fn()
      render(
        <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext
            items={[lesson.id, otherLesson.id]}
            strategy={verticalListSortingStrategy}
          >
            {[lesson, otherLesson].map((item) => (
              <DraggableLessonCard
                key={item.id}
                dragId={item.id}
                dragEnabled
                lesson={item}
                isConflict={false}
                onDelete={() => {}}
                getLessonTypeColor={() => "#6366f1"}
                getLessonTypeLabel={() => "Lecture"}
              />
            ))}
          </SortableContext>
        </DndContext>
      )

      const [firstHandle] = screen.getAllByRole("button", { name: "Drag lesson" })
      await user.tab()
      expect(firstHandle).toHaveFocus()
      await user.keyboard(" ")
      await user.keyboard("{ArrowDown}{ArrowDown}")
      await user.keyboard(" ")

      expect(onDragEnd).toHaveBeenCalledOnce()
      expect(onDragEnd).toHaveBeenCalledWith(
        expect.objectContaining({
          active: expect.objectContaining({ id: lesson.id }),
          over: expect.objectContaining({ id: otherLesson.id }),
        })
      )
    } finally {
      measure.mockRestore()
    }
  })

  it.each([
    ["mouse", "mouse", "[MouseLeft>]", "[/MouseLeft]"],
    ["touch", "TouchA", "[TouchA>]", "[/TouchA]"],
  ])(
    "still starts and ends a %s pointer drag",
    async (pointerType, pointerName, press, release) => {
      const user = userEvent.setup()
      const { onDragStart, onDragEnd } = renderLesson(true)
      const handle = screen.getByRole("button", { name: "Drag lesson" })

      await user.pointer([
        { keys: press, target: handle, coords: { clientX: 10, clientY: 10 } },
        { pointerName, target: handle, coords: { clientX: 20, clientY: 20 } },
        { keys: release, target: handle },
      ])

      expect(onDragStart).toHaveBeenCalledOnce()
      expect(onDragStart).toHaveBeenCalledWith(
        expect.objectContaining({
          active: expect.objectContaining({ id: lesson.id }),
          activatorEvent: expect.objectContaining({ pointerType }),
        })
      )
      expect(onDragEnd).toHaveBeenCalledOnce()
      expect(onDragEnd).toHaveBeenCalledWith(
        expect.objectContaining({ delta: expect.objectContaining({ x: 10, y: 10 }) })
      )
    }
  )
})
