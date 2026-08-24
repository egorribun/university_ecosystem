import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import type { PointerEvent } from "react"

import { useSwipe } from "./useSwipe"

/**
 * Tests for the velocity-aware swipe-detection hook.
 *
 * The hook exposes four pointer handlers (down/up/cancel/leave). It
 * triggers ``onSwipeLeft`` / ``onSwipeRight`` when a pointer-down →
 * pointer-up sequence:
 *  - is primarily horizontal (|dx| > |dy|);
 *  - completes within ``timeout`` (default 500 ms);
 *  - covers ≥ ``threshold`` (default 50 px) OR has ≥ ``minVelocity``
 *    px/ms (default 0.3 — catches fast short swipes).
 *
 * We pin Date.now via vi.useFakeTimers so timing is deterministic.
 */

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-05-15T00:00:00Z"))
})

afterEach(() => {
  vi.useRealTimers()
})

function pointerEvent(x: number, y: number): PointerEvent {
  return { clientX: x, clientY: y } as unknown as PointerEvent
}

describe("useSwipe — basic detection", () => {
  it("triggers onSwipeRight on a long fast horizontal +x swipe", () => {
    const onSwipeRight = vi.fn()
    const onSwipeLeft = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight, onSwipeLeft }))

    result.current.onPointerDown(pointerEvent(0, 0))
    vi.advanceTimersByTime(50) // fast — well within timeout
    result.current.onPointerUp(pointerEvent(120, 5))

    expect(onSwipeRight).toHaveBeenCalledOnce()
    expect(onSwipeLeft).not.toHaveBeenCalled()
  })

  it("triggers onSwipeLeft on a long fast horizontal -x swipe", () => {
    const onSwipeLeft = vi.fn()
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight, onSwipeLeft }))

    result.current.onPointerDown(pointerEvent(200, 0))
    vi.advanceTimersByTime(50)
    result.current.onPointerUp(pointerEvent(80, 5))

    expect(onSwipeLeft).toHaveBeenCalledOnce()
    expect(onSwipeRight).not.toHaveBeenCalled()
  })

  it("does not trigger when pointer-down was never recorded", () => {
    const onSwipeLeft = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeLeft }))

    // pointerUp without preceding pointerDown — nothing happens.
    result.current.onPointerUp(pointerEvent(120, 0))
    expect(onSwipeLeft).not.toHaveBeenCalled()
  })
})

describe("useSwipe — gating conditions", () => {
  it("rejects when vertical movement dominates", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight }))

    result.current.onPointerDown(pointerEvent(0, 0))
    vi.advanceTimersByTime(50)
    // dx=60 but dy=120 — primarily vertical, must reject.
    result.current.onPointerUp(pointerEvent(60, 120))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })

  it("rejects when total time exceeds the configured timeout", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight, timeout: 200 }))

    result.current.onPointerDown(pointerEvent(0, 0))
    vi.advanceTimersByTime(300) // > timeout
    result.current.onPointerUp(pointerEvent(200, 0))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })

  it("triggers below threshold when velocity is high enough", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() =>
      useSwipe({
        onSwipeRight,
        threshold: 100, // very high threshold
        minVelocity: 0.3, // 0.3 px/ms
      })
    )

    // 30px in 50ms → 0.6 px/ms → exceeds minVelocity even though
    // distance < threshold.
    result.current.onPointerDown(pointerEvent(0, 0))
    vi.advanceTimersByTime(50)
    result.current.onPointerUp(pointerEvent(30, 0))

    expect(onSwipeRight).toHaveBeenCalledOnce()
  })

  it("rejects below both threshold and velocity", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() =>
      useSwipe({
        onSwipeRight,
        threshold: 100,
        minVelocity: 0.3,
      })
    )

    // 20px in 200ms → 0.1 px/ms → below both thresholds.
    result.current.onPointerDown(pointerEvent(0, 0))
    vi.advanceTimersByTime(200)
    result.current.onPointerUp(pointerEvent(20, 0))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })

  it("treats a zero-duration gesture as zero velocity", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() =>
      useSwipe({ onSwipeRight, threshold: 100, minVelocity: 0.3 })
    )

    result.current.onPointerDown(pointerEvent(0, 0))
    result.current.onPointerUp(pointerEvent(20, 0))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })
})

describe("useSwipe — cancel paths", () => {
  it("clears the recorded start on pointer-cancel", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight }))

    result.current.onPointerDown(pointerEvent(0, 0))
    result.current.onPointerCancel(pointerEvent(0, 0))
    // Following pointerUp must be a no-op.
    result.current.onPointerUp(pointerEvent(120, 0))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })

  it("clears the recorded start on pointer-leave", () => {
    const onSwipeRight = vi.fn()
    const { result } = renderHook(() => useSwipe({ onSwipeRight }))

    result.current.onPointerDown(pointerEvent(0, 0))
    result.current.onPointerLeave(pointerEvent(0, 0))
    result.current.onPointerUp(pointerEvent(120, 0))

    expect(onSwipeRight).not.toHaveBeenCalled()
  })
})
