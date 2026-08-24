import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useClock } from "@/hooks/useClock"

describe("useClock", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-08-14T10:20:30.250"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("aligns the first tick to a minute and then updates every minute", () => {
    const { result, unmount } = renderHook(() => useClock("en-US"))
    expect(result.current.hh).toBe("10")
    expect(result.current.mm).toBe("20")
    expect(result.current.time.getSeconds()).toBe(0)

    act(() => vi.advanceTimersByTime(29_750))
    expect(result.current.mm).toBe("21")

    act(() => vi.advanceTimersByTime(60_000))
    expect(result.current.mm).toBe("22")
    unmount()
  })

  it("cleans up safely before the minute-alignment timeout fires", () => {
    const { unmount } = renderHook(() => useClock("ru-RU"))
    expect(() => unmount()).not.toThrow()
  })
})
