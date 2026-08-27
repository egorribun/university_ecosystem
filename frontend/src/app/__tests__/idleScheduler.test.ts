import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { getIdleScheduler, scheduleIdleFallback } from "../idleScheduler"

describe("idle scheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    Reflect.deleteProperty(window, "requestIdleCallback")
  })

  it("provides a deadline-compatible timeout fallback", () => {
    const callback = vi.fn((deadline: IdleDeadline) => {
      expect(deadline.didTimeout).toBe(true)
      expect(deadline.timeRemaining()).toBe(0)
    })

    const timerId = scheduleIdleFallback(callback, { timeout: 10 })
    vi.advanceTimersByTime(9)
    expect(callback).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)

    expect(timerId).toBeDefined()
    expect(callback).toHaveBeenCalledOnce()
  })

  it("uses the native idle callback when available", () => {
    const native = vi.fn(() => 7)
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: native,
    })

    const scheduler = getIdleScheduler()
    const callback = vi.fn()
    const options = { timeout: 25 }

    expect(scheduler(callback, options)).toBe(7)
    expect(native).toHaveBeenCalledWith(callback, options)
  })

  it("falls back when native idle callbacks are unavailable", () => {
    Reflect.deleteProperty(window, "requestIdleCallback")
    expect(getIdleScheduler()).toBe(scheduleIdleFallback)
  })
})
