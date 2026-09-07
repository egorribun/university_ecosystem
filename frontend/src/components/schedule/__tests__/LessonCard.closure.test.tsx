import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

import { getLessonAccentClass, LessonCard } from "../LessonCard"
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
  it("maps known, composite, and unknown lesson types to stable accents", () => {
    expect(getLessonAccentClass("lecture")).toBe("sched-accent-lecture")
    expect(getLessonAccentClass("PRACTICE")).toBe("sched-accent-practice")
    expect(getLessonAccentClass("lab-work")).toBe("sched-accent-lab")
    expect(getLessonAccentClass("project-seminar")).toBe("sched-accent-project")
    expect(getLessonAccentClass("seminar")).toBe("sched-accent-default")
    expect(getLessonAccentClass(null)).toBe("sched-accent-default")
    expect(getLessonAccentClass(undefined)).toBe("sched-accent-default")
  })

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

    expect(card).toHaveClass(
      "sched-conflict",
      "gap-1.5",
      "p-3",
      "mt-5",
      "sched-current-glow",
      "cursor-pointer"
    )
    expect(card).toHaveStyle({ "--sched-stagger-i": "3", "--sched-progress": "42" })
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

  it("keeps compact and non-interactive cards keyboard-safe", () => {
    const onDelete = vi.fn()
    const { rerender, container } = render(
      <LessonCard
        {...baseProps}
        lesson={makeLesson()}
        compact
        isCurrent={false}
        onDelete={onDelete}
      />
    )
    const compactCard = container.firstElementChild!
    expect(compactCard).toHaveClass("gap-1", "p-2.5")
    expect(compactCard).not.toHaveClass("cursor-pointer", "sched-current-glow", "mt-5")
    expect(compactCard).not.toHaveAttribute("role")
    expect(compactCard).toHaveStyle({ "--sched-progress": "0" })
    expect(screen.queryByLabelText("schedule:aria.deleteLesson")).not.toBeInTheDocument()

    rerender(
      <LessonCard
        {...baseProps}
        lesson={makeLesson({ lesson_type: "lab" })}
        onOpen={vi.fn()}
        isConflict={false}
        compact={false}
        isCurrent={false}
        hasBreakBefore={false}
        canEdit
      />
    )
    const fullCard = container.firstElementChild!
    expect(fullCard).toHaveClass("sched-accent-lab", "gap-1.5", "p-3", "cursor-pointer")
    expect(fullCard).not.toHaveClass("sched-conflict", "sched-current-glow", "mt-5")
    expect(fullCard).toHaveAttribute("role", "button")
    expect(screen.getByLabelText("schedule:aria.deleteLesson")).toBeInTheDocument()
  })

  it("renders teacher, room, and note details only when supplied", () => {
    const { rerender } = render(
      <LessonCard {...baseProps} lesson={makeLesson()} compact={false} hasNote />
    )
    expect(screen.getByText("Dr. Ivanova")).toBeInTheDocument()
    expect(screen.getByText("ГУК")).toBeInTheDocument()
    expect(screen.getByText("305")).toBeInTheDocument()
    expect(screen.getByTitle("schedule:notes.hasNote")).toBeInTheDocument()

    rerender(
      <LessonCard
        {...baseProps}
        lesson={makeLesson({ teacher: null, room: "101" })}
        compact={false}
        hasNote={false}
      />
    )
    expect(screen.queryByText("Dr. Ivanova")).not.toBeInTheDocument()
    expect(screen.getByText("101")).toBeInTheDocument()
    expect(screen.queryByTitle("schedule:notes.hasNote")).not.toBeInTheDocument()
  })

  it("falls back when lesson type and room are absent", () => {
    render(<LessonCard {...baseProps} lesson={makeLesson({ lesson_type: null, room: null })} />)

    expect(screen.getByText("Lesson")).toBeInTheDocument()
    expect(screen.queryByText("ГУК")).not.toBeInTheDocument()
  })

  it("matches composite lesson types to their accent", () => {
    const { container } = render(<LessonCard {...baseProps} lesson={makeLesson()} />)

    expect(container.firstElementChild).toHaveClass("sched-accent-lecture")
  })
})
