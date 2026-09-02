import { act, renderHook } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

import { NAVBAR_SCROLL_ENTER_THRESHOLD, NAVBAR_SCROLL_EXIT_THRESHOLD } from "@/constants/scroll"
import { useScrollBehavior } from "../useScrollBehavior"

describe("useScrollBehavior", () => {
  it("renders the non-scrolled state without a browser window", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")
    Reflect.deleteProperty(globalThis, "window")

    try {
      const Probe = () => <span>{String(useScrollBehavior().isScrolled)}</span>
      expect(renderToString(<Probe />)).toContain(">false<")
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "window", descriptor)
    }
  })

  it("keeps the first client render aligned with SSR when scroll restoration is non-zero", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "scrollY")
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      value: NAVBAR_SCROLL_ENTER_THRESHOLD + 100,
    })

    try {
      const Probe = () => <span>{String(useScrollBehavior().isScrolled)}</span>
      expect(renderToString(<Probe />)).toContain(">false<")
    } finally {
      if (descriptor) {
        Object.defineProperty(window, "scrollY", descriptor)
      } else {
        Reflect.deleteProperty(window, "scrollY")
      }
    }
  })

  it("coalesces scroll events into one frame and applies hysteresis", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "scrollY")
    let scrollY = 0
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      get: () => scrollY,
    })

    try {
      const frames: FrameRequestCallback[] = []
      const requestAnimationFrame = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((callback) => {
          frames.push(callback)
          return frames.length
        })
      const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
      const { result, unmount } = renderHook(() => useScrollBehavior())
      expect(result.current.isScrolled).toBe(false)

      act(() => window.dispatchEvent(new Event("scroll")))
      act(() => window.dispatchEvent(new Event("scroll")))
      expect(requestAnimationFrame).toHaveBeenCalledOnce()
      expect(result.current.isScrolled).toBe(false)
      act(() => frames.shift()?.(0))

      scrollY = NAVBAR_SCROLL_ENTER_THRESHOLD + 1
      act(() => window.dispatchEvent(new Event("scroll")))
      expect(result.current.isScrolled).toBe(false)
      act(() => frames.shift()?.(16))
      expect(result.current.isScrolled).toBe(true)

      scrollY = NAVBAR_SCROLL_EXIT_THRESHOLD + 1
      act(() => window.dispatchEvent(new Event("scroll")))
      act(() => frames.shift()?.(32))
      expect(result.current.isScrolled).toBe(true)

      scrollY = NAVBAR_SCROLL_EXIT_THRESHOLD - 1
      act(() => window.dispatchEvent(new Event("scroll")))
      act(() => frames.shift()?.(48))
      expect(result.current.isScrolled).toBe(false)

      scrollY = NAVBAR_SCROLL_ENTER_THRESHOLD + 10
      act(() => window.dispatchEvent(new Event("scroll")))
      unmount()
      expect(cancelAnimationFrame).toHaveBeenCalled()
    } finally {
      if (descriptor) {
        Object.defineProperty(window, "scrollY", descriptor)
      } else {
        Reflect.deleteProperty(window, "scrollY")
      }
    }
  })
})
