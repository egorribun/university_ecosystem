import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

import { useHaptics } from "./useHaptics"

/**
 * useHaptics — thin wrapper over ``navigator.vibrate`` that maps a
 * symbolic style ('light' / 'medium' / 'heavy' / 'success' / 'warning'
 * / 'error') to a duration or pattern.
 *
 * Coverage:
 *  - each style produces the documented vibrate argument;
 *  - default style 'light' triggers when called without args;
 *  - hook gracefully degrades when navigator.vibrate is undefined;
 *  - the returned trigger function reference is stable across renders.
 */

let vibrateMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  vibrateMock = vi.fn().mockReturnValue(true)
  vi.stubGlobal("navigator", { ...navigator, vibrate: vibrateMock })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useHaptics — style → vibrate mapping", () => {
  it.each([
    ["light", 10],
    ["medium", 20],
    ["heavy", 40],
  ] as const)("triggers a single-tap '%s' as %d ms", (style, expected) => {
    const { result } = renderHook(() => useHaptics())
    result.current.trigger(style)
    expect(vibrateMock).toHaveBeenCalledWith(expected)
  })

  it.each([
    ["success", [10, 50, 10]],
    ["warning", [30, 100, 30]],
    ["error", [50, 50, 50, 50, 50]],
  ] as const)("triggers a pattern for '%s'", (style, pattern) => {
    const { result } = renderHook(() => useHaptics())
    result.current.trigger(style)
    expect(vibrateMock).toHaveBeenCalledWith(pattern)
  })

  it("defaults to 'light' when called without an argument", () => {
    const { result } = renderHook(() => useHaptics())
    result.current.trigger()
    expect(vibrateMock).toHaveBeenCalledWith(10)
  })
})

describe("useHaptics — graceful degradation", () => {
  it("is a no-op when navigator.vibrate is missing", () => {
    vi.stubGlobal("navigator", {})
    const { result } = renderHook(() => useHaptics())
    // Must NOT throw — even when navigator.vibrate is undefined.
    expect(() => result.current.trigger("error")).not.toThrow()
  })
})

describe("useHaptics — function identity", () => {
  it("returns a stable trigger reference across re-renders (useCallback)", () => {
    const { result, rerender } = renderHook(() => useHaptics())
    const first = result.current.trigger
    rerender()
    expect(result.current.trigger).toBe(first)
  })
})
