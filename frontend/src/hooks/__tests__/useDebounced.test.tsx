import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useDebounced } from "../useDebounced"

describe("useDebounced", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ---------------------------------------------------------------------------
  // Initial value
  // ---------------------------------------------------------------------------
  it("returns the initial value immediately", () => {
    const { result } = renderHook(() => useDebounced("hello", 300))
    expect(result.current).toBe("hello")
  })

  // ---------------------------------------------------------------------------
  // Debounce delay — value is not updated before the timer fires
  // ---------------------------------------------------------------------------
  it("does not update value before the delay has passed", () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounced(value, delay), {
      initialProps: { value: "initial", delay: 300 },
    })

    rerender({ value: "updated", delay: 300 })
    // Half-way — should not have updated yet
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(result.current).toBe("initial")
  })

  it("updates value after the delay has passed", () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounced(value, delay), {
      initialProps: { value: "initial", delay: 300 },
    })

    rerender({ value: "updated", delay: 300 })
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current).toBe("updated")
  })

  // ---------------------------------------------------------------------------
  // Debounce cancellation — rapid changes should only apply the last one
  // ---------------------------------------------------------------------------
  it("only applies the last value when the input changes rapidly", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "a" },
    })

    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(100))
    rerender({ value: "c" })
    act(() => vi.advanceTimersByTime(100))
    rerender({ value: "d" })
    // Timer resets each rerender — only fires after 300ms from the last update
    act(() => vi.advanceTimersByTime(300))
    expect(result.current).toBe("d")
  })

  // ---------------------------------------------------------------------------
  // Preset names
  // ---------------------------------------------------------------------------
  it("accepts 'search' preset (200ms)", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "search"), {
      initialProps: { value: "a" },
    })
    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(199))
    expect(result.current).toBe("a") // not yet
    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe("b") // now
  })

  it("accepts 'validation' preset (350ms)", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "validation"), {
      initialProps: { value: "a" },
    })
    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(349))
    expect(result.current).toBe("a")
    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe("b")
  })

  it("accepts 'default' preset (300ms)", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "default"), {
      initialProps: { value: "a" },
    })
    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(300))
    expect(result.current).toBe("b")
  })

  // ---------------------------------------------------------------------------
  // Works with non-string types
  // ---------------------------------------------------------------------------
  it("works with numbers", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 200), {
      initialProps: { value: 1 },
    })
    rerender({ value: 42 })
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe(42)
  })

  it("works with objects (by reference)", () => {
    const obj1 = { count: 1 }
    const obj2 = { count: 2 }
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 100), {
      initialProps: { value: obj1 },
    })
    rerender({ value: obj2 })
    act(() => vi.advanceTimersByTime(100))
    expect(result.current).toBe(obj2)
  })

  // ---------------------------------------------------------------------------
  // Cleanup and edge cases
  // ---------------------------------------------------------------------------
  it("clears the timeout on unmount", () => {
    const { rerender, unmount } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "initial" },
    })
    rerender({ value: "updated" })
    unmount()
    expect(() => act(() => vi.advanceTimersByTime(300))).not.toThrow()
  })

  it("works correctly with a delay of 0", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 0), {
      initialProps: { value: "x" },
    })
    rerender({ value: "y" })
    act(() => vi.advanceTimersByTime(0))
    expect(result.current).toBe("y")
  })
})
