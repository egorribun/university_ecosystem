import { act, cleanup, renderHook } from "@testing-library/react"
import { StrictMode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useClock } from "@/hooks/useClock"

const initialTime = new Date("2026-08-14T10:20:30.250")

function installClockFixture() {
  const wasFake = vi.isFakeTimers()
  const previousTime = Date.now()
  if (!wasFake) vi.useFakeTimers()

  const timeoutDescriptor = Object.getOwnPropertyDescriptor(window, "setTimeout")!
  const intervalDescriptor = Object.getOwnPropertyDescriptor(window, "setInterval")!
  const setTimeout = window.setTimeout.bind(window)
  const setInterval = window.setInterval.bind(window)
  const clearTimeout = window.clearTimeout.bind(window)
  const clearInterval = window.clearInterval.bind(window)
  const timeouts = new Set<number>()
  const intervals = new Set<number>()

  // Keep real fake-clock scheduling. These handles are only a teardown fallback
  // after the ownership assertions, including when a negative control leaks.
  Object.defineProperty(window, "setTimeout", {
    ...timeoutDescriptor,
    value: (...args: Parameters<Window["setTimeout"]>) => {
      const id = setTimeout(...args)
      timeouts.add(id)
      return id
    },
  })
  Object.defineProperty(window, "setInterval", {
    ...intervalDescriptor,
    value: (...args: Parameters<Window["setInterval"]>) => {
      const id = setInterval(...args)
      intervals.add(id)
      return id
    },
  })
  vi.setSystemTime(initialTime)

  return () => {
    const errors: unknown[] = []
    const steps = [
      cleanup,
      ...Array.from(timeouts, (id) => () => clearTimeout(id)),
      ...Array.from(intervals, (id) => () => clearInterval(id)),
      () => Object.defineProperty(window, "setTimeout", timeoutDescriptor),
      () => Object.defineProperty(window, "setInterval", intervalDescriptor),
      () => (wasFake ? vi.setSystemTime(previousTime) : vi.useRealTimers()),
    ]
    for (const step of steps) {
      try {
        step()
      } catch (error) {
        errors.push(error)
      }
    }
    if (errors.length) throw new AggregateError(errors, "useClock timer fixture cleanup failed")
  }
}

describe("useClock timer ownership", () => {
  let restoreClock: () => void

  beforeEach(() => {
    restoreClock = installClockFixture()
  })

  afterEach(() => restoreClock())

  it.each([
    { phase: "before minute alignment", elapsed: 0 },
    { phase: "after the interval starts", elapsed: 29_750 },
  ])("unmounts $phase without cancelling another owner's timer", ({ elapsed }) => {
    const unrelatedTick = vi.fn()
    window.setTimeout(unrelatedTick, 120_000)
    const timersBeforeMount = vi.getTimerCount()
    const { unmount } = renderHook(() => useClock("en-US"))

    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
    act(() => vi.advanceTimersByTime(elapsed))
    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)

    unmount()
    expect(vi.getTimerCount()).toBe(timersBeforeMount)
    act(() => vi.advanceTimersByTime(120_000 - elapsed))
    expect(unrelatedTick).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(timersBeforeMount - 1)
  })

  it("releases every timer across repeated mounts before and after alignment", () => {
    const timersBeforeMount = vi.getTimerCount()

    for (const elapsed of [0, 29_750, 0, 29_750]) {
      vi.setSystemTime(initialTime)
      const { unmount } = renderHook(() => useClock("en-US"))
      expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
      act(() => vi.advanceTimersByTime(elapsed))
      expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
      unmount()
      expect(vi.getTimerCount()).toBe(timersBeforeMount)
    }

    act(() => vi.advanceTimersByTime(180_000))
    expect(vi.getTimerCount()).toBe(timersBeforeMount)
  })

  it("keeps one ticking clock through locale changes and releases it on unmount", () => {
    const timersBeforeMount = vi.getTimerCount()
    const { result, rerender, unmount } = renderHook(({ locale }) => useClock(locale), {
      initialProps: { locale: "en-US" },
    })
    const englishDate = result.current.dateStr

    rerender({ locale: "ru-RU" })
    expect(result.current.dateStr).not.toBe(englishDate)
    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
    act(() => vi.advanceTimersByTime(29_750))
    expect(result.current.mm).toBe("21")
    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)

    rerender({ locale: "en-US" })
    expect(result.current.dateStr).toBe(englishDate)
    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
    act(() => vi.advanceTimersByTime(60_000))
    expect(result.current.mm).toBe("22")

    unmount()
    expect(vi.getTimerCount()).toBe(timersBeforeMount)
  })

  it("owns only one timer after StrictMode replays the effect", () => {
    const timersBeforeMount = vi.getTimerCount()
    const { result, unmount } = renderHook(() => useClock("en-US"), { wrapper: StrictMode })

    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)
    act(() => vi.advanceTimersByTime(29_750))
    expect(result.current.mm).toBe("21")
    expect(vi.getTimerCount()).toBe(timersBeforeMount + 1)

    unmount()
    expect(vi.getTimerCount()).toBe(timersBeforeMount)
    act(() => vi.advanceTimersByTime(120_000))
    expect(vi.getTimerCount()).toBe(timersBeforeMount)
  })
})
