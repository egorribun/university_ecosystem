import { describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"

import { useSwipeGesture } from "./useSwipeGesture"

/**
 * Tests for the touch-driven drawer-close gesture hook.
 *
 * The hook tracks a single finger's clientX delta from touchStart.
 * Movement is only recorded in the configured close direction
 * (positive delta when ``direction="right"``, negative when "left");
 * other directions are clamped to dragOffset=0. On touchEnd, if the
 * absolute delta exceeds ``threshold``, ``onSwipeClose`` fires.
 *
 * When ``enabled=false`` the hook becomes inert — no offset, no callback.
 */

const touch = (clientX: number) =>
  ({
    touches: [{ clientX }],
  }) as unknown as React.TouchEvent

describe("useSwipeGesture — disabled", () => {
  it("ignores all events when enabled=false", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        onSwipeClose,
        enabled: false,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(100))
      result.current.handlers.onTouchMove(touch(300))
      result.current.handlers.onTouchEnd()
    })

    expect(result.current.dragOffset).toBe(0)
    expect(result.current.isDragging).toBe(false)
    expect(onSwipeClose).not.toHaveBeenCalled()
  })
})

describe("useSwipeGesture — direction='right'", () => {
  it("records positive delta on rightward drag", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(100))
    })
    expect(result.current.isDragging).toBe(true)

    act(() => {
      result.current.handlers.onTouchMove(touch(150))
    })
    expect(result.current.dragOffset).toBe(50)
  })

  it("ignores leftward drag (only close-direction movement counts)", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(100))
    })
    act(() => {
      result.current.handlers.onTouchMove(touch(40)) // delta = -60
    })
    expect(result.current.dragOffset).toBe(0)
  })

  it("fires onSwipeClose past threshold and resets state", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        threshold: 80,
        onSwipeClose,
        enabled: true,
      })
    )

    // Each handler must run in its own act() block so the previous
    // setState (e.g. setIsDragging(true)) takes effect before the
    // next handler reads it from its closure.
    act(() => {
      result.current.handlers.onTouchStart(touch(0))
    })
    act(() => {
      result.current.handlers.onTouchMove(touch(120))
    })
    expect(result.current.dragOffset).toBe(120)

    act(() => {
      result.current.handlers.onTouchEnd()
    })
    expect(onSwipeClose).toHaveBeenCalledOnce()
    expect(result.current.dragOffset).toBe(0)
    expect(result.current.isDragging).toBe(false)
  })

  it("does not fire below threshold; just resets", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        threshold: 80,
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(0))
    })
    act(() => {
      result.current.handlers.onTouchMove(touch(40))
    })
    act(() => {
      result.current.handlers.onTouchEnd()
    })
    expect(onSwipeClose).not.toHaveBeenCalled()
    expect(result.current.dragOffset).toBe(0)
  })
})

describe("useSwipeGesture — direction='left'", () => {
  it("records negative delta on leftward drag", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "left",
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(200))
    })
    act(() => {
      result.current.handlers.onTouchMove(touch(50))
    })
    expect(result.current.dragOffset).toBe(-150)
  })

  it("fires onSwipeClose when |delta| exceeds threshold", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "left",
        threshold: 80,
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(200))
    })
    act(() => {
      result.current.handlers.onTouchMove(touch(50)) // delta = -150
    })
    act(() => {
      result.current.handlers.onTouchEnd()
    })
    expect(onSwipeClose).toHaveBeenCalledOnce()
  })
})

describe("useSwipeGesture — empty touches list", () => {
  it("ignores touchStart with no touches", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({
        direction: "right",
        onSwipeClose,
        enabled: true,
      })
    )

    act(() => {
      result.current.handlers.onTouchStart({
        touches: [],
      } as unknown as React.TouchEvent)
    })
    expect(result.current.isDragging).toBe(false)
  })

  it("ignores touchMove with no touches after dragging starts", () => {
    const onSwipeClose = vi.fn()
    const { result } = renderHook(() =>
      useSwipeGesture({ direction: "right", onSwipeClose, enabled: true })
    )

    act(() => {
      result.current.handlers.onTouchStart(touch(100))
    })
    act(() => {
      result.current.handlers.onTouchMove({ touches: [] } as unknown as React.TouchEvent)
    })

    expect(result.current.dragOffset).toBe(0)
    expect(result.current.isDragging).toBe(true)
  })
})
