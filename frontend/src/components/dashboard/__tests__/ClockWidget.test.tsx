import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
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
})
