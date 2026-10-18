import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useMinuteClock } from "../useMinuteClock"

const START = "2026-08-09T12:00:00.000Z"

describe("useMinuteClock", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(START))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("starts at the current time and advances once per minute", () => {
    const { result } = renderHook(() => useMinuteClock())
    expect(result.current).toBe(Date.parse(START))

    act(() => {
      vi.advanceTimersByTime(59_999)
    })
    expect(result.current).toBe(Date.parse(START))

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe(Date.parse("2026-08-09T12:01:00.000Z"))
  })

  it("stops its timer when the component unmounts", () => {
    const clearSpy = vi.spyOn(window, "clearInterval")
    const { unmount } = renderHook(() => useMinuteClock())

    unmount()

    expect(clearSpy).toHaveBeenCalledOnce()
    clearSpy.mockRestore()
  })
})
