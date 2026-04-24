import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useTimeOfDay } from "../useTimeOfDay"
import type { TimePeriod } from "../useTimeOfDay"

/** Sets the fake clock to a specific hour and re-initialises the hook */
const withHour = (hour: number) => {
  vi.setSystemTime(new Date(2025, 5, 15, hour, 0, 0))
}

describe("useTimeOfDay", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ---------------------------------------------------------------------------
  // Initial period mapping
  // ---------------------------------------------------------------------------
  const HOUR_PERIOD_PAIRS: [number, TimePeriod][] = [
    [5, "dawn"],
    [6, "dawn"],
    [7, "morning"],
    [11, "morning"],
    [12, "afternoon"],
    [16, "afternoon"],
    [17, "dusk"],
    [19, "dusk"],
    [20, "night"],
    [23, "night"],
    [0, "night"],
    [4, "night"],
  ]

  it.each(HOUR_PERIOD_PAIRS)("returns '%s' at hour %i", (hour, expected) => {
    withHour(hour)
    const { result } = renderHook(() => useTimeOfDay())
    expect(result.current).toBe(expected)
  })

  // ---------------------------------------------------------------------------
  // Reactive update every minute
  // ---------------------------------------------------------------------------
  it("updates the period when the clock crosses a boundary", () => {
    // Start at 06:59 (dawn — last minute before morning)
    vi.setSystemTime(new Date(2025, 5, 15, 6, 59, 0))
    const { result } = renderHook(() => useTimeOfDay())
    expect(result.current).toBe("dawn")

    // Advance 1 minute — now 07:00 → morning
    act(() => {
      vi.setSystemTime(new Date(2025, 5, 15, 7, 0, 0))
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current).toBe("morning")
  })

  it("does not update before a full minute has elapsed", () => {
    withHour(6)
    const { result } = renderHook(() => useTimeOfDay())
    const initial = result.current

    // Advance only 30 seconds — no interval tick yet
    act(() => vi.advanceTimersByTime(30_000))
    expect(result.current).toBe(initial)
  })

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------
  it("clears the interval on unmount", () => {
    const clearSpy = vi.spyOn(global, "clearInterval")
    withHour(10)
    const { unmount } = renderHook(() => useTimeOfDay())
    unmount()
    expect(clearSpy).toHaveBeenCalledTimes(1)
  })
})
