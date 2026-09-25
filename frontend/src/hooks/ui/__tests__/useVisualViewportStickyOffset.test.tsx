import { act, renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useVisualViewportStickyOffset } from "../useVisualViewportStickyOffset"

describe("useVisualViewportStickyOffset", () => {
  it("leaves the element unchanged when the visual viewport is unavailable", () => {
    const original = Object.getOwnPropertyDescriptor(window, "visualViewport")
    Object.defineProperty(window, "visualViewport", { configurable: true, value: null })

    try {
      const element = document.createElement("div")
      const { unmount } = renderHook(() => useVisualViewportStickyOffset({ current: element }))
      expect(element.style.getPropertyValue("--visual-viewport-offset-top")).toBe("")
      unmount()
    } finally {
      if (original) Object.defineProperty(window, "visualViewport", original)
      else Reflect.deleteProperty(window, "visualViewport")
    }
  })

  it("coalesces viewport changes, ignores unchanged offsets, and cleans up", () => {
    const original = Object.getOwnPropertyDescriptor(window, "visualViewport")
    const viewport = Object.assign(new EventTarget(), { offsetTop: -5 })
    const addListener = vi.spyOn(viewport, "addEventListener")
    const removeListener = vi.spyOn(viewport, "removeEventListener")
    Object.defineProperty(window, "visualViewport", { configurable: true, value: viewport })

    const frames = new Map<number, FrameRequestCallback>()
    let nextFrame = 0
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      const id = ++nextFrame
      frames.set(id, callback)
      return id
    })
    const cancelFrame = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(id)
    })

    try {
      const missingElement = renderHook(() => useVisualViewportStickyOffset({ current: null }))
      expect(addListener).not.toHaveBeenCalled()
      missingElement.unmount()

      const element = document.createElement("div")
      const { unmount } = renderHook(() => useVisualViewportStickyOffset({ current: element }))
      expect(element.style.getPropertyValue("--visual-viewport-offset-top")).toBe("0px")
      expect(addListener).toHaveBeenCalledTimes(2)

      viewport.offsetTop = 132
      act(() => {
        viewport.dispatchEvent(new Event("scroll"))
        viewport.dispatchEvent(new Event("resize"))
      })
      expect(frames.size).toBe(1)
      act(() => {
        const [id, callback] = [...frames][0]!
        frames.delete(id)
        callback(0)
      })
      expect(element.style.getPropertyValue("--visual-viewport-offset-top")).toBe("132px")

      act(() => window.dispatchEvent(new Event("scroll")))
      act(() => {
        const [id, callback] = [...frames][0]!
        frames.delete(id)
        callback(0)
      })
      expect(element.style.getPropertyValue("--visual-viewport-offset-top")).toBe("132px")

      viewport.offsetTop = 80
      act(() => viewport.dispatchEvent(new Event("resize")))
      expect(frames.size).toBe(1)
      unmount()
      expect(cancelFrame).toHaveBeenCalled()
      expect(frames.size).toBe(0)
      expect(removeListener).toHaveBeenCalledTimes(2)
      expect(element.style.getPropertyValue("--visual-viewport-offset-top")).toBe("")
    } finally {
      vi.restoreAllMocks()
      if (original) Object.defineProperty(window, "visualViewport", original)
      else Reflect.deleteProperty(window, "visualViewport")
    }
  })
})
