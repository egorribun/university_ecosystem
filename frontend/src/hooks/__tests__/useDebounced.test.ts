/**
 * Wave 10 — Branch coverage for useDebounced hook.
 *
 * WHY: useDebounced is widely used across the codebase for search inputs and
 * form validation. Untested debounce timing creates silent regressions on
 * timeout changes. We cover the main branches: immediate value, delayed update,
 * and cleanup on unmount.
 */
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useDebounced } from "../useDebounced"

describe("useDebounced", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("returns the initial value immediately without waiting", () => {
    // Branch: first render — no delay applied to initial value
    const { result } = renderHook(() => useDebounced("initial", 300))
    expect(result.current).toBe("initial")
  })

  it("does not update before the delay has elapsed", () => {
    // Branch: value changes but timer has not fired
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "first" },
    })
    rerender({ value: "second" })
    act(() => {
      vi.advanceTimersByTime(150) // Half the delay
    })
    // Must still hold the old value
    expect(result.current).toBe("first")
  })

  it("updates to the new value after the delay", () => {
    // Branch: timer fires → state updates
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "first" },
    })
    rerender({ value: "second" })
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current).toBe("second")
  })

  it("resets the timer when value changes before delay", () => {
    // Branch: multiple rapid changes — only the last value is committed
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "a" },
    })
    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(100))
    rerender({ value: "c" })
    act(() => vi.advanceTimersByTime(100))
    // 200ms total — still inside debounce window
    expect(result.current).toBe("a")
    act(() => vi.advanceTimersByTime(300))
    // Only the most recent value committed
    expect(result.current).toBe("c")
  })

  it("clears the timeout on unmount (no state update after unmount)", () => {
    // Branch: cleanup path — no setState after unmount (no warnings)
    const { rerender, unmount } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: "initial" },
    })
    rerender({ value: "updated" })
    unmount()
    // Advancing timers after unmount should not throw
    expect(() => act(() => vi.advanceTimersByTime(300))).not.toThrow()
  })

  it("works correctly with a delay of 0", () => {
    // Branch: zero delay — effectively synchronous after event loop tick
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 0), {
      initialProps: { value: "x" },
    })
    rerender({ value: "y" })
    act(() => vi.advanceTimersByTime(0))
    expect(result.current).toBe("y")
  })

  it("uses 200ms for the 'search' preset", () => {
    // Branch: delay is a string preset 'search' → resolves to 200ms
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "search"), {
      initialProps: { value: "a" },
    })
    rerender({ value: "b" })
    act(() => vi.advanceTimersByTime(150))
    expect(result.current).toBe("a") // not yet committed
    act(() => vi.advanceTimersByTime(50))
    expect(result.current).toBe("b") // 200ms reached
  })

  it("uses 350ms for the 'validation' preset", () => {
    // Branch: delay is a string preset 'validation' → resolves to 350ms
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "validation"), {
      initialProps: { value: "x" },
    })
    rerender({ value: "z" })
    act(() => vi.advanceTimersByTime(300))
    expect(result.current).toBe("x") // still debouncing
    act(() => vi.advanceTimersByTime(50))
    expect(result.current).toBe("z") // 350ms reached
  })

  it("uses 300ms for the 'default' preset", () => {
    // Branch: delay is a string preset 'default' → resolves to 300ms
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, "default"), {
      initialProps: { value: "p" },
    })
    rerender({ value: "q" })
    act(() => vi.advanceTimersByTime(300))
    expect(result.current).toBe("q")
  })
})
