import { renderHook, act } from "@testing-library/react"
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest"
import { useTilt } from "../useTilt"
import React from "react"

describe("useTilt", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Mock requestAnimationFrame and cancelAnimationFrame
    vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
      return setTimeout(fn, 16)
    })
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      clearTimeout(id)
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("returns appropriate initial style depending on disabled option", () => {
    const { result: enabledResult } = renderHook(() => useTilt({ disabled: false }))
    expect(enabledResult.current.style).toEqual({
      willChange: "transform",
      transition: "transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
    })

    const { result: disabledResult } = renderHook(() => useTilt({ disabled: true }))
    expect(disabledResult.current.style).toEqual({})
  })

  it("does not transform onMouseMove or onMouseLeave when disabled", () => {
    const { result } = renderHook(() => useTilt({ disabled: true }))
    const el = document.createElement("div")
    result.current.ref(el)

    const event = { clientX: 100, clientY: 100 } as React.MouseEvent
    result.current.onMouseMove(event)
    act(() => {
      vi.advanceTimersByTime(16)
    })
    expect(el.style.transform).toBe("")

    result.current.onMouseLeave()
    expect(el.style.transform).toBe("")
  })

  it("applies transforms onMouseMove and resets onMouseLeave when enabled", () => {
    const { result } = renderHook(() => useTilt({ max: 10, scale: 1.05 }))
    const el = document.createElement("div")

    // Mock getBoundingClientRect
    el.getBoundingClientRect = () => ({
      left: 10,
      top: 10,
      width: 100,
      height: 100,
      right: 110,
      bottom: 110,
      x: 10,
      y: 10,
      toJSON: () => {},
    })

    result.current.ref(el)

    // Center is at X = 10 + 50 = 60, Y = 10 + 50 = 60
    // Mouse at clientX = 80, clientY = 40
    // normX = (80 - 60) / 50 = 0.4
    // normY = (40 - 60) / 50 = -0.4
    // rotateY = 0.4 * 10 = 4
    // rotateX = -(-0.4) * 10 = 4
    const event = { clientX: 80, clientY: 40 } as React.MouseEvent
    result.current.onMouseMove(event)

    act(() => {
      vi.advanceTimersByTime(16)
    })

    expect(el.style.transform).toContain("rotateX(4.00deg)")
    expect(el.style.transform).toContain("rotateY(4.00deg)")
    expect(el.style.transform).toContain("scale3d(1.05, 1.05, 1)")

    // Resets on mouse leave
    result.current.onMouseLeave()
    expect(el.style.transform).toBe("")
  })

  it("cancels animation frame on unmount", () => {
    const { result, unmount } = renderHook(() => useTilt())
    const el = document.createElement("div")
    el.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      right: 100,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => {},
    })
    result.current.ref(el)

    const cancelSpy = vi.spyOn(window, "clearTimeout")
    result.current.onMouseMove({ clientX: 50, clientY: 50 } as React.MouseEvent)

    unmount()
    expect(cancelSpy).toHaveBeenCalled()
    cancelSpy.mockRestore()
  })
})
