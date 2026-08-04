import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

import { LessonCard } from "../LessonCard"
import type { Lesson } from "../scheduleUtils"

const makeLesson = (overrides: Partial<Lesson> = {}): Lesson => ({
  id: "lesson-1",
  weekday: "monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "ГУК-305",
  lesson_type: "lecture-seminar",
  ...overrides,
})

const baseProps = {
  isConflict: false,
  onDelete: vi.fn(),
  getLessonTypeColor: vi.fn(() => "#6366f1"),
  getLessonTypeLabel: vi.fn((value?: string | null) => value ?? "Lesson"),
}

describe("LessonCard", () => {
  it("renders the rich card and handles click, keyboard, and delete actions", () => {
    const onOpen = vi.fn()
    const onDelete = vi.fn()
    render(
      <LessonCard
        {...baseProps}
        lesson={makeLesson()}
        isConflict
        isCurrent
        currentProgress={42}
        index={3}
        onOpen={onOpen}
        onDelete={onDelete}
        hasBreakBefore
        canEdit
        hasNote
      />
    )

    const card = screen.getByRole("button", { name: /Linear Algebra/ })
    expect(card).toHaveAttribute("aria-current", "time")
    expect(card).toHaveAttribute("title", "schedule:lesson.conflict")
    expect(screen.getByText("schedule:lesson.conflict")).toBeInTheDocument()
    expect(screen.getByTitle("schedule:notes.hasNote")).toBeInTheDocument()
    expect(screen.getByText("ГУК")).toBeInTheDocument()
    expect(screen.getByText("305")).toBeInTheDocument()

    fireEvent.click(card)
    fireEvent.keyDown(card, { key: "Enter" })
    fireEvent.keyDown(card, { key: " " })
    fireEvent.keyDown(card, { key: "Escape" })
    expect(onOpen).toHaveBeenCalledTimes(3)

    fireEvent.click(screen.getByRole("button", { name: "schedule:aria.deleteLesson" }))
    expect(onDelete).toHaveBeenCalledOnce()
    expect(baseProps.getLessonTypeColor).toHaveBeenCalledWith("lecture-seminar")
    expect(baseProps.getLessonTypeLabel).toHaveBeenCalledWith("lecture-seminar")
  })

  it("renders compact cards and uses the generic room/accent fallback", () => {
    const { container } = render(
      <LessonCard
        {...baseProps}
        lesson={makeLesson({
          id: "lesson-2",
          subject: "Independent Study",
          teacher: null,
          room: "101",
          lesson_type: "seminar",
        })}
        compact
      />
    )

    expect(screen.queryByRole("button", { name: /Independent Study/ })).not.toBeInTheDocument()
    expect(screen.getByText("Independent Study")).toBeInTheDocument()
    expect(screen.queryByText("schedule:notes.hasNote")).not.toBeInTheDocument()
    expect(container.firstElementChild).not.toHaveAttribute("aria-current")

    render(
      <LessonCard
        {...baseProps}
        lesson={makeLesson({ id: "lesson-3", room: "101", lesson_type: "lecture" })}
      />
    )
    expect(screen.getByText("101")).toBeInTheDocument()
  })

  it("falls back when lesson type and room are absent", () => {
    render(<LessonCard {...baseProps} lesson={makeLesson({ lesson_type: null, room: null })} />)

    expect(screen.getByText("Lesson")).toBeInTheDocument()
    expect(screen.queryByText("ГУК")).not.toBeInTheDocument()
  })
})
