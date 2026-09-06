import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { ClockWidget } from "../ClockWidget"

describe("ClockWidget", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(Date.prototype, "toLocaleTimeString").mockReturnValue("10:05")
    vi.spyOn(Date.prototype, "toLocaleDateString").mockReturnValue("Friday, 1 August")
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("renders locale-formatted time and refreshes it each second", () => {
    const time = vi.spyOn(Date.prototype, "toLocaleTimeString")
    render(<ClockWidget />)

    expect(screen.getByText("10:05")).toBeInTheDocument()
    expect(screen.getByText("Friday, 1 August")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(time).toHaveBeenCalledTimes(2)
  })

  it("renders a deterministic placeholder before browser hydration", () => {
    const html = renderToString(<ClockWidget />)

    expect(html).toContain('aria-busy="true"')
    expect(html).toContain("--:--")
    expect(html).not.toContain("10:05")
  })

  it("passes the deliberate locale options and cleans up its timer", () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval")
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval")
    const { unmount } = render(<ClockWidget />)

    expect(Date.prototype.toLocaleTimeString).toHaveBeenCalledWith([], {
      hour: "2-digit",
      minute: "2-digit",
    })
    expect(Date.prototype.toLocaleDateString).toHaveBeenCalledWith(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
    })

    expect(setIntervalSpy).toHaveBeenCalledTimes(1)
    const timerHandle = setIntervalSpy.mock.results[0]?.value
    unmount()
    expect(clearIntervalSpy).toHaveBeenCalledWith(timerHandle)
  })

  it("keeps the semantic dashboard styling contract", () => {
    render(<ClockWidget />)
    const clock = screen.getByText("10:05").parentElement
    expect(clock).toHaveClass("relative", "rounded-3xl", "border")
    expect(clock?.className).toContain("before:pointer-events-none")
    expect(screen.getByText("10:05")).toHaveClass("tabular-nums")
    expect(screen.getByText("Friday, 1 August")).toHaveClass("uppercase", "tracking-widest")
  })
})
