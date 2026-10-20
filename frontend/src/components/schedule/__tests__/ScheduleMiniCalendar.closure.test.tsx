import { useState } from "react"
import { act, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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

  it("uses one date tab stop and moves real focus through the controlled month", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onMonthChange = vi.fn()
    const nowTick = new Date(2026, 5, 15, 12)

    function ControlledMonthCalendar({ currentTime }: { currentTime: Date }) {
      const [controlledMonth, setControlledMonth] = useState(new Date(2026, 5, 1))
      return (
        <ScheduleMiniCalendar
          month={controlledMonth}
          nowTick={currentTime}
          onMonthChange={(nextMonth) => {
            onMonthChange(nextMonth)
            setControlledMonth(nextMonth)
          }}
        />
      )
    }

    const view = render(<ControlledMonthCalendar currentTime={nowTick} />)

    const grid = screen.getByRole("grid", { name: "June 2026" })
    const today = screen.getByRole("button", { name: "June 15, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()

    expect(today).toHaveFocus()
    expect(
      within(grid)
        .getAllByRole("button")
        .filter((button) => button.tabIndex === 0)
    ).toEqual([today])

    await user.keyboard("{ArrowRight}")
    const june16 = screen.getByRole("button", { name: "June 16, 2026" })
    expect(june16).toHaveFocus()
    expect(june16).toHaveAttribute("tabindex", "0")

    await user.keyboard("{ArrowDown}")
    expect(screen.getByRole("button", { name: "June 23, 2026" })).toHaveFocus()

    await user.keyboard("{ArrowUp}")
    expect(june16).toHaveFocus()

    await user.keyboard("{Home}")
    expect(today).toHaveFocus()

    await user.keyboard("{End}")
    const june21 = screen.getByRole("button", { name: "June 21, 2026" })
    expect(june21).toHaveFocus()
    expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()
    expect(onMonthChange).not.toHaveBeenCalled()

    view.rerender(<ControlledMonthCalendar currentTime={new Date(2026, 5, 16, 12)} />)
    expect(screen.getByRole("button", { name: "June 16, 2026" })).toHaveAttribute(
      "aria-current",
      "date"
    )
    expect(june21).toHaveFocus()
    expect(june21).toHaveAttribute("tabindex", "0")
  })

  it("moves focus into an adjacent month when an arrow crosses its boundary", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onMonthChange = vi.fn()
    const nowTick = new Date(2026, 5, 1, 12)

    function ControlledMonthCalendar() {
      const [controlledMonth, setControlledMonth] = useState(new Date(2026, 5, 1))
      return (
        <ScheduleMiniCalendar
          month={controlledMonth}
          nowTick={nowTick}
          onMonthChange={(nextMonth) => {
            onMonthChange(nextMonth)
            setControlledMonth(nextMonth)
          }}
        />
      )
    }

    render(<ControlledMonthCalendar />)

    const june1 = screen.getByRole("button", { name: "June 1, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()
    expect(june1).toHaveFocus()

    await user.keyboard("{ArrowLeft}")

    expect(onMonthChange).toHaveBeenCalledExactlyOnceWith(new Date(2026, 4, 1))
    expect(screen.getByRole("grid", { name: "May 2026" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "May 31, 2026" })).toHaveFocus()
  })

  it("moves an uncontrolled calendar across a year boundary with the focused date", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const nowTick = new Date(2026, 0, 1, 12)
    const onMonthChange = vi.fn()

    render(<ScheduleMiniCalendar nowTick={nowTick} onMonthChange={onMonthChange} />)

    const january1 = screen.getByRole("button", { name: "January 1, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()
    expect(january1).toHaveFocus()

    await user.keyboard("{ArrowLeft}")

    const december31 = screen.getByRole("button", { name: "December 31, 2025" })
    expect(screen.getByRole("grid", { name: "December 2025" })).toBeInTheDocument()
    expect(december31).toHaveFocus()
    expect(december31).toHaveAttribute("tabindex", "0")
    expect(onMonthChange).toHaveBeenCalledExactlyOnceWith(new Date(2025, 11, 1))
  })

  it("bounds Home and End to the dates in partial first and last rows", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onMonthChange = vi.fn()
    const nowTick = new Date(2026, 7, 2, 12)

    render(
      <ScheduleMiniCalendar
        month={new Date(2026, 7, 1)}
        nowTick={nowTick}
        onMonthChange={onMonthChange}
      />
    )

    const august2 = screen.getByRole("button", { name: "August 2, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()
    expect(august2).toHaveFocus()

    await user.keyboard("{Home}")
    const august1 = screen.getByRole("button", { name: "August 1, 2026" })
    expect(august1).toHaveFocus()
    await user.keyboard("{End}")
    expect(august2).toHaveFocus()

    for (let week = 0; week < 4; week += 1) {
      await user.keyboard("{ArrowDown}")
    }
    await user.keyboard("{ArrowRight}")
    const august31 = screen.getByRole("button", { name: "August 31, 2026" })
    expect(august31).toHaveFocus()
    await user.keyboard("{Home}")
    expect(august31).toHaveFocus()
    await user.keyboard("{End}")
    expect(august31).toHaveFocus()
    expect(screen.getByRole("grid", { name: "August 2026" })).toBeInTheDocument()
    expect(onMonthChange).not.toHaveBeenCalled()
  })

  it("keeps native Enter activation and ignores unrelated day keys", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onDayClick = vi.fn()
    const onMonthChange = vi.fn()
    const nowTick = new Date(2026, 5, 15, 12)

    render(
      <ScheduleMiniCalendar
        nowTick={nowTick}
        onDayClick={onDayClick}
        onMonthChange={onMonthChange}
      />
    )

    const june15 = screen.getByRole("button", { name: "June 15, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()
    expect(june15).toHaveFocus()

    await user.keyboard("x")
    expect(june15).toHaveFocus()
    expect(june15).toHaveAttribute("tabindex", "0")
    expect(onDayClick).not.toHaveBeenCalled()
    expect(onMonthChange).not.toHaveBeenCalled()

    await user.keyboard("{Enter}")
    expect(onDayClick).toHaveBeenCalledExactlyOnceWith(new Date(2026, 5, 15))
    expect(onMonthChange).not.toHaveBeenCalled()
  })

  it("keeps the visible focus and tab stop when a controlled parent declines a month change", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    const onDayClick = vi.fn()
    const onMonthChange = vi.fn()
    const month = new Date(2026, 5, 1)
    const nowTick = new Date(2026, 5, 15, 12)

    render(
      <ScheduleMiniCalendar
        month={month}
        nowTick={nowTick}
        onDayClick={onDayClick}
        onMonthChange={onMonthChange}
      />
    )

    const grid = screen.getByRole("grid", { name: "June 2026" })
    const june15 = screen.getByRole("button", { name: "June 15, 2026" })
    await user.tab()
    await user.tab()
    await user.tab()
    expect(june15).toHaveFocus()

    await user.keyboard("{ArrowUp}{ArrowUp}")
    const june1 = screen.getByRole("button", { name: "June 1, 2026" })
    expect(june1).toHaveFocus()

    await user.keyboard("{ArrowLeft}")

    expect(onMonthChange).toHaveBeenCalledExactlyOnceWith(new Date(2026, 4, 1))
    expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "May 31, 2026" })).not.toBeInTheDocument()
    expect(grid).toContainElement(june1)
    expect(june1).toHaveFocus()
    expect(june1).toHaveAttribute("tabindex", "0")
    expect(
      within(grid)
        .getAllByRole("button")
        .filter((button) => button.tabIndex === 0)
    ).toEqual([june1])
    expect(onDayClick).not.toHaveBeenCalled()
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

describe("ScheduleMiniCalendar local date rollover", () => {
  it("moves today's marker after local midnight without changing the displayed month", () => {
    vi.setSystemTime(new Date(2026, 5, 15, 23, 59, 45))
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    const timerCount = vi.getTimerCount()
    const onMonthChange = vi.fn()
    const onDayClick = vi.fn()
    let unmount: (() => void) | undefined

    try {
      const view = render(
        <ScheduleMiniCalendar onMonthChange={onMonthChange} onDayClick={onDayClick} />
      )
      unmount = view.unmount

      expect(screen.getByRole("button", { name: "June 15, 2026" })).toHaveAttribute(
        "aria-current",
        "date"
      )

      act(() => {
        vi.advanceTimersByTime(30_000)
      })

      expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()
      const yesterday = screen.getByRole("button", { name: "June 15, 2026" })
      const today = screen.getByRole("button", { name: "June 16, 2026" })
      expect(yesterday).not.toHaveAttribute("aria-current")
      expect(yesterday).not.toHaveAttribute("data-today")
      expect(today).toHaveAttribute("aria-current", "date")
      expect(today).toHaveAttribute("data-today", "true")
      expect(onMonthChange).not.toHaveBeenCalled()
      expect(onDayClick).not.toHaveBeenCalled()
    } finally {
      unmount?.()
      visibility.mockRestore()
      expect(vi.getTimerCount()).toBe(timerCount)
    }
  })

  it("preserves the displayed month at midnight until Today is explicitly requested", () => {
    vi.setSystemTime(new Date(2026, 5, 30, 23, 59, 45))
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    const timerCount = vi.getTimerCount()
    const onMonthChange = vi.fn()
    const onDayClick = vi.fn()
    let unmount: (() => void) | undefined

    try {
      const view = render(
        <ScheduleMiniCalendar onMonthChange={onMonthChange} onDayClick={onDayClick} />
      )
      unmount = view.unmount

      expect(screen.getByRole("button", { name: "June 30, 2026" })).toHaveAttribute(
        "aria-current",
        "date"
      )

      act(() => {
        vi.advanceTimersByTime(30_000)
      })

      expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()
      const yesterday = screen.getByRole("button", { name: "June 30, 2026" })
      expect(yesterday).not.toHaveAttribute("aria-current")
      expect(yesterday).not.toHaveAttribute("data-today")
      expect(onMonthChange).not.toHaveBeenCalled()
      expect(onDayClick).not.toHaveBeenCalled()

      fireEvent.click(screen.getByRole("button", { name: "common:today" }))

      expect(screen.getByRole("grid", { name: "July 2026" })).toBeInTheDocument()
      const today = screen.getByRole("button", { name: "July 1, 2026" })
      expect(today).toHaveAttribute("aria-current", "date")
      expect(today).toHaveAttribute("data-today", "true")
      expect(onMonthChange).toHaveBeenCalledExactlyOnceWith(new Date(2026, 6, 1, 0, 0, 15))
      expect(onDayClick).not.toHaveBeenCalled()
    } finally {
      unmount?.()
      visibility.mockRestore()
      expect(vi.getTimerCount()).toBe(timerCount)
    }
  })

  it("uses the supplied clock without a ticker and preserves the controlled month", () => {
    const beforeMidnight = new Date(2026, 5, 30, 23, 59, 45)
    const afterMidnight = new Date(2026, 6, 1, 0, 0, 15)
    const clickTime = new Date(2026, 6, 1, 0, 0, 25)
    const displayedMonth = new Date(2026, 5, 1)
    vi.setSystemTime(beforeMidnight)
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    const addEventListener = vi.spyOn(document, "addEventListener")
    const timerCount = vi.getTimerCount()
    const onMonthChange = vi.fn()
    const onDayClick = vi.fn()
    let unmount: (() => void) | undefined

    try {
      const view = render(
        <ScheduleMiniCalendar
          month={displayedMonth}
          nowTick={beforeMidnight}
          onMonthChange={onMonthChange}
          onDayClick={onDayClick}
        />
      )
      unmount = view.unmount

      expect(screen.getByRole("button", { name: "June 30, 2026" })).toHaveAttribute(
        "aria-current",
        "date"
      )
      expect(vi.getTimerCount()).toBe(timerCount)

      vi.setSystemTime(afterMidnight)
      view.rerender(
        <ScheduleMiniCalendar
          month={displayedMonth}
          nowTick={afterMidnight}
          onMonthChange={onMonthChange}
          onDayClick={onDayClick}
        />
      )

      expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()
      const yesterday = screen.getByRole("button", { name: "June 30, 2026" })
      expect(yesterday).not.toHaveAttribute("aria-current")
      expect(yesterday).not.toHaveAttribute("data-today")
      expect(onMonthChange).not.toHaveBeenCalled()
      expect(onDayClick).not.toHaveBeenCalled()
      expect(vi.getTimerCount()).toBe(timerCount)
      expect(
        addEventListener.mock.calls.filter(([type]) => type === "visibilitychange")
      ).toHaveLength(0)

      vi.setSystemTime(clickTime)
      fireEvent.click(screen.getByRole("button", { name: "common:today" }))

      expect(onMonthChange).toHaveBeenCalledExactlyOnceWith(clickTime)
      expect(onDayClick).not.toHaveBeenCalled()
      expect(screen.getByRole("grid", { name: "June 2026" })).toBeInTheDocument()

      view.rerender(
        <ScheduleMiniCalendar
          month={clickTime}
          nowTick={afterMidnight}
          onMonthChange={onMonthChange}
          onDayClick={onDayClick}
        />
      )

      expect(screen.getByRole("grid", { name: "July 2026" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "July 1, 2026" })).toHaveAttribute(
        "aria-current",
        "date"
      )
      expect(vi.getTimerCount()).toBe(timerCount)
    } finally {
      unmount?.()
      addEventListener.mockRestore()
      visibility.mockRestore()
      expect(vi.getTimerCount()).toBe(timerCount)
    }
  })
})
