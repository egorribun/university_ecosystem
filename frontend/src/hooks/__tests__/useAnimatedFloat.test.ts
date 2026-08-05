import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mediaState = vi.hoisted(() => ({ reduced: false }))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => mediaState.reduced,
}))

import { easeOutExpo, useAnimatedFloat } from "../useAnimatedFloat"

describe("useAnimatedFloat", () => {
  beforeEach(() => {
    mediaState.reduced = false
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("uses the reduced-motion value immediately and follows target updates", () => {
    mediaState.reduced = true
    const { result, rerender } = renderHook(({ target }) => useAnimatedFloat(target, 0.2), {
      initialProps: { target: 12 },
    })

    expect(result.current).toBe(12)
    rerender({ target: 7 })
    expect(result.current).toBe(7)
  })

  it("animates toward a target with requestAnimationFrame", () => {
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frames.push(callback)
      return frames.length
    })
    vi.stubGlobal("cancelAnimationFrame", vi.fn())

    const { result, unmount } = renderHook(() => useAnimatedFloat(10, 1))
    act(() => frames.shift()?.(0))
    act(() => frames.shift()?.(500))
    act(() => frames.shift()?.(1500))

    expect(result.current).toBe(10)
    unmount()
  })

  it("clamps the easing function at its endpoint", () => {
    expect(easeOutExpo(0)).toBe(0)
    expect(easeOutExpo(0.5)).toBeGreaterThan(0)
    expect(easeOutExpo(1)).toBe(1)
    expect(easeOutExpo(2)).toBe(1)
  })
})
