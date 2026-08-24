import { act, renderHook } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { NAVBAR_SCROLL_THRESHOLD } from "@/constants/scroll"
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
      value: NAVBAR_SCROLL_THRESHOLD + 100,
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

  it("updates only when the scroll threshold state changes", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "scrollY")
    let scrollY = 0
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      get: () => scrollY,
    })

    try {
      const { result, unmount } = renderHook(() => useScrollBehavior())
      expect(result.current.isScrolled).toBe(false)

      act(() => window.dispatchEvent(new Event("scroll")))
      expect(result.current.isScrolled).toBe(false)

      scrollY = NAVBAR_SCROLL_THRESHOLD + 1
      act(() => window.dispatchEvent(new Event("scroll")))
      expect(result.current.isScrolled).toBe(true)

      act(() => window.dispatchEvent(new Event("scroll")))
      expect(result.current.isScrolled).toBe(true)
      unmount()
    } finally {
      if (descriptor) {
        Object.defineProperty(window, "scrollY", descriptor)
      } else {
        Reflect.deleteProperty(window, "scrollY")
      }
    }
  })
})
