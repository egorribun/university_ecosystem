import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useScheduleClock } from "../useScheduleClock"

function mockVisibilityState(initial: DocumentVisibilityState) {
  const original = Object.getOwnPropertyDescriptor(document, "visibilityState")
  let state = initial
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  })
  return {
    set(value: DocumentVisibilityState) {
      state = value
    },
    restore() {
      if (original) {
        Object.defineProperty(document, "visibilityState", original)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
    },
  }
}

describe("useScheduleClock", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-15T09:30:00.000Z"))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("does not create an interval or visibility listener while disabled", () => {
    const timersBefore = vi.getTimerCount()
    const addListener = vi.spyOn(document, "addEventListener")
    const rendered = renderHook(() => useScheduleClock(false))
    try {
      expect(vi.getTimerCount()).toBe(timersBefore)
      expect(addListener.mock.calls.some(([type]) => type === "visibilitychange")).toBe(false)
    } finally {
      rendered.unmount()
    }
    expect(vi.getTimerCount()).toBe(timersBefore)
  })

  it("refreshes immediately when enabled after time advances", () => {
    const before = new Date("2026-07-15T09:30:00.000Z")
    const after = new Date("2026-07-15T09:31:00.000Z")
    const timersBefore = vi.getTimerCount()
    const visibility = mockVisibilityState("visible")
    const useClock = ({ enabled }: { enabled: boolean }) => useScheduleClock(enabled)
    const rendered = renderHook(useClock, { initialProps: { enabled: false } })
    try {
      expect(rendered.result.current.getTime()).toBe(before.getTime())
      vi.setSystemTime(after)
      rendered.rerender({ enabled: true })
      expect(rendered.result.current.getTime()).toBe(after.getTime())
      expect(vi.getTimerCount()).toBe(timersBefore + 1)
    } finally {
      rendered.unmount()
      visibility.restore()
    }
    expect(vi.getTimerCount()).toBe(timersBefore)
  })

  it("updates when an enabled ticker crosses an epoch minute", () => {
    const initial = new Date("2026-07-15T09:29:45.000Z")
    vi.setSystemTime(initial)
    const visibility = mockVisibilityState("visible")
    const rendered = renderHook(() => useScheduleClock())
    try {
      expect(rendered.result.current.getTime()).toBe(initial.getTime())
      act(() => vi.advanceTimersByTime(30_000))
      expect(rendered.result.current.getTime()).toBe(initial.getTime() + 30_000)
    } finally {
      rendered.unmount()
      visibility.restore()
    }
  })

  it("keeps the same Date within the same epoch minute", () => {
    const initial = new Date("2026-07-15T09:30:05.000Z")
    vi.setSystemTime(initial)
    const visibility = mockVisibilityState("visible")
    const rendered = renderHook(() => useScheduleClock())
    const initialTick = rendered.result.current
    try {
      act(() => vi.advanceTimersByTime(30_000))
      expect(rendered.result.current).toBe(initialTick)
      expect(rendered.result.current.getTime()).toBe(initial.getTime())
    } finally {
      rendered.unmount()
      visibility.restore()
    }
  })

  it("pauses hidden ticks and refreshes immediately when visible", () => {
    const initial = new Date("2026-07-15T09:29:45.000Z")
    vi.setSystemTime(initial)
    const visibility = mockVisibilityState("hidden")
    const rendered = renderHook(() => useScheduleClock())
    const initialTick = rendered.result.current
    try {
      act(() => {
        vi.advanceTimersByTime(30_000)
        document.dispatchEvent(new Event("visibilitychange"))
      })
      expect(rendered.result.current).toBe(initialTick)
      visibility.set("visible")
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      expect(rendered.result.current.getTime()).toBe(initial.getTime() + 30_000)
    } finally {
      rendered.unmount()
      visibility.restore()
    }
  })

  it("refreshes after a hidden day at the same wall-clock minute", () => {
    const before = new Date(2026, 6, 15, 9, 30)
    const after = new Date(2026, 6, 16, 9, 30)
    vi.setSystemTime(before)
    const visibility = mockVisibilityState("hidden")
    const rendered = renderHook(() => useScheduleClock())
    try {
      expect(rendered.result.current.getTime()).toBe(before.getTime())
      vi.setSystemTime(after)
      visibility.set("visible")
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      expect(rendered.result.current.getTime()).toBe(after.getTime())
    } finally {
      rendered.unmount()
      visibility.restore()
    }
  })

  it("clears its interval and visibility listener on unmount", () => {
    const timersBefore = vi.getTimerCount()
    const visibility = mockVisibilityState("visible")
    const removeListener = vi.spyOn(document, "removeEventListener")
    const rendered = renderHook(() => useScheduleClock())
    try {
      expect(vi.getTimerCount()).toBe(timersBefore + 1)
    } finally {
      rendered.unmount()
      visibility.restore()
    }
    expect(vi.getTimerCount()).toBe(timersBefore)
    expect(removeListener.mock.calls.some(([type]) => type === "visibilitychange")).toBe(true)
  })
})
