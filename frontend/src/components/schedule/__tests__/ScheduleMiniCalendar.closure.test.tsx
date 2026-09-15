import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}))

import { ScheduleMiniCalendar } from "../ScheduleMiniCalendar"

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-06-15T12:00:00"))
})

afterEach(() => {
  vi.useRealTimers()
})

describe("ScheduleMiniCalendar", () => {
  it("renders the current month, marks lesson days, and emits day clicks", () => {
    const onDayClick = vi.fn()

    render(
      <ScheduleMiniCalendar
        lessonDays={new Set([15])}
        onDayClick={onDayClick}
        className="custom-calendar"
      />
    )

    expect(screen.getByText("June 2026")).toBeInTheDocument()
    expect(screen.getByRole("grid").parentElement).toHaveClass("custom-calendar")

    const today = screen.getByRole("button", { name: "June 15, 2026" })
    expect(today).toHaveAttribute("data-has-lessons", "true")
    expect(today).toHaveAttribute("data-today", "true")
    expect(today).toHaveAttribute("aria-current", "date")

    fireEvent.click(today)
    expect(onDayClick).toHaveBeenCalledWith(new Date(2026, 5, 15))
  })

  it("navigates between months and can return to today", () => {
    const onMonthChange = vi.fn()
    render(<ScheduleMiniCalendar onMonthChange={onMonthChange} />)

    fireEvent.click(screen.getByRole("button", { name: "common:next" }))
    expect(screen.getByText("July 2026")).toBeInTheDocument()
    expect(onMonthChange).toHaveBeenLastCalledWith(new Date(2026, 6, 1))
    expect(screen.getByRole("button", { name: "common:today" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:prev" }))
    expect(screen.getByText("June 2026")).toBeInTheDocument()
    expect(onMonthChange).toHaveBeenLastCalledWith(new Date(2026, 5, 1))

    fireEvent.click(screen.getByRole("button", { name: "common:next" }))
    fireEvent.click(screen.getByRole("button", { name: "common:today" }))
    expect(screen.getByText("June 2026")).toBeInTheDocument()
    expect(onMonthChange).toHaveBeenLastCalledWith(new Date("2026-06-15T12:00:00"))
  })

  it("supports a controlled month and Sunday offsets", () => {
    const { container } = render(<ScheduleMiniCalendar month={new Date(2026, 10, 1)} />)

    expect(screen.getByText("November 2026")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "common:today" })).toBeInTheDocument()
    expect(screen.getAllByRole("gridcell")).toHaveLength(36)
    expect(screen.getAllByRole("row")).toHaveLength(6)
    expect(screen.getByRole("button", { name: "November 1, 2026" }).parentElement).toHaveAttribute(
      "aria-colindex",
      "7"
    )
    expect(screen.getByRole("button", { name: "November 30, 2026" })).not.toHaveAttribute(
      "data-has-lessons"
    )
    expect(screen.getByRole("button", { name: "November 15, 2026" })).not.toHaveAttribute(
      "aria-current"
    )

    const weekdayHeader = container.querySelector(".mb-1.grid.grid-cols-7")
    expect([...weekdayHeader!.children].map((node) => node.textContent)).toEqual([
      "M",
      "T",
      "W",
      "T",
      "F",
      "S",
      "S",
    ])
  })

  it("keeps optional callbacks safe and handles month boundaries and leap days", () => {
    const { rerender } = render(<ScheduleMiniCalendar month={new Date(2026, 0, 1)} />)
    // Drop the controlled prop so the navigation callback can update the
    // component's internal month state.
    rerender(<ScheduleMiniCalendar />)

    expect(() => fireEvent.click(screen.getByRole("button", { name: "common:prev" }))).not.toThrow()
    expect(screen.getByText("December 2025")).toBeInTheDocument()
    expect(() =>
      fireEvent.click(screen.getByRole("button", { name: "December 15, 2025" }))
    ).not.toThrow()

    rerender(<ScheduleMiniCalendar month={new Date(2028, 1, 1)} />)
    expect(screen.getByText("February 2028")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "February 29, 2028" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "February 30, 2028" })).not.toBeInTheDocument()
  })

  it("renders an accessible loading skeleton without requiring callbacks", () => {
    render(<ScheduleMiniCalendar isLoading />)

    expect(screen.getByRole("grid")).toHaveAttribute("aria-busy", "true")
    expect(screen.getAllByRole("presentation")).toHaveLength(35)
    expect(screen.queryAllByRole("gridcell")).toHaveLength(0)
  })
})
