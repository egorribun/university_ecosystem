import { beforeEach, describe, expect, it, vi } from "vitest"
import { getScrollRoot, smoothToTop, markIfFromBottom } from "../scrollUtils"

describe("scrollUtils", () => {
  beforeEach(() => {
    document.body.innerHTML = ""
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  describe("getScrollRoot", () => {
    it("returns element with [data-scroll-root] if present", () => {
      const div = document.createElement("div")
      div.setAttribute("data-scroll-root", "")
      div.style.overflowY = "auto"
      Object.defineProperties(div, {
        clientHeight: { value: 100, configurable: true },
        scrollHeight: { value: 200, configurable: true },
      })
      document.body.appendChild(div)

      expect(getScrollRoot()).toBe(div)
    })

    it("ignores a non-scrolling layout marker", () => {
      const marker = document.createElement("div")
      marker.setAttribute("data-scroll-root", "")
      document.body.appendChild(marker)

      expect(getScrollRoot()).toBe(document.scrollingElement || document.documentElement)
    })

    it("evaluates candidates and returns the first scrollable candidate", () => {
      const main = document.createElement("main")
      document.body.appendChild(main)

      // Stub clientHeight & scrollHeight
      Object.defineProperties(main, {
        clientHeight: { value: 100, configurable: true },
        scrollHeight: { value: 200, configurable: true },
      })

      // Stub getComputedStyle to return overflowY = "auto"
      vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
        if (el === main) {
          return { overflowY: "auto" } as CSSStyleDeclaration
        }
        return {} as CSSStyleDeclaration
      })

      expect(getScrollRoot()).toBe(main)
    })

    it("falls back to document.scrollingElement or document.documentElement", () => {
      const root = getScrollRoot()
      expect(root).toBe(document.scrollingElement || document.documentElement)
    })
  })

  describe("smoothToTop", () => {
    it("uses scrollTo method if available and successful", () => {
      const el = document.createElement("div")
      el.scrollTo = vi.fn()

      smoothToTop(el)
      expect(el.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
    })

    it("uses requestAnimationFrame fallback animation if scrollTo is not supported or throws", () => {
      const el = document.createElement("div")
      el.scrollTop = 100
      // Delete scrollTo to trigger the catch block
      // @ts-expect-error - deleting scrollTo to test fallback
      delete el.scrollTo

      // Mock requestAnimationFrame to run immediately
      let rafCallback: FrameRequestCallback | null = null
      vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
        rafCallback = cb
        return 1
      })

      smoothToTop(el)
      expect(window.requestAnimationFrame).toHaveBeenCalled()

      // Execute animation step
      if (rafCallback) {
        // First frame: timestamp = 1000 (must be non-zero so t0 is set correctly)
        ;(rafCallback as FrameRequestCallback)(1000)
        // Next frame: timestamp = 1210 (halfway through 420ms duration)
        if (rafCallback) {
          ;(rafCallback as FrameRequestCallback)(1210)
          expect(el.scrollTop).toBeLessThan(100)
        }
        // Final frame: timestamp = 1500 (beyond 420ms)
        if (rafCallback) {
          ;(rafCallback as FrameRequestCallback)(1500)
          expect(el.scrollTop).toBe(0)
        }
      }
    })

    it("jumps immediately without RAF when reduced motion requests auto behavior", () => {
      const el = document.createElement("div")
      el.scrollTop = 100
      el.scrollTo = vi.fn(() => {
        throw new Error("unsupported")
      })
      const raf = vi.spyOn(window, "requestAnimationFrame")

      smoothToTop(el, "auto")

      expect(el.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })
      expect(el.scrollTop).toBe(0)
      expect(raf).not.toHaveBeenCalled()
    })
  })

  describe("markIfFromBottom", () => {
    it("sets __scrollTopNext in sessionStorage if scrolled near bottom", () => {
      const mockEl = document.createElement("div")
      mockEl.style.overflowY = "auto"
      Object.defineProperties(mockEl, {
        scrollTop: { value: 180, configurable: true },
        clientHeight: { value: 100, configurable: true },
        scrollHeight: { value: 300, configurable: true }, // near bottom threshold = 24
      })

      // Mock getScrollRoot to return mockEl
      vi.spyOn(document, "querySelector").mockImplementation((selector) => {
        if (selector === "[data-scroll-root]") return mockEl
        return null
      })

      markIfFromBottom()
      expect(sessionStorage.getItem("__scrollTopNext")).toBe("1")
    })

    it("does not set __scrollTopNext if not near bottom", () => {
      const mockEl = document.createElement("div")
      mockEl.style.overflowY = "auto"
      Object.defineProperties(mockEl, {
        scrollTop: { value: 50, configurable: true },
        clientHeight: { value: 100, configurable: true },
        scrollHeight: { value: 300, configurable: true },
      })

      vi.spyOn(document, "querySelector").mockImplementation((selector) => {
        if (selector === "[data-scroll-root]") return mockEl
        return null
      })

      markIfFromBottom()
      expect(sessionStorage.getItem("__scrollTopNext")).toBeNull()
    })
  })

  describe("scroll ownership detection", () => {
    const makeElement = (
      tag: string,
      overflowY: string,
      scrollHeight: number,
      clientHeight = 100
    ) => {
      const el = document.createElement(tag)
      el.style.overflowY = overflowY
      Object.defineProperties(el, {
        clientHeight: { value: clientHeight, configurable: true },
        scrollHeight: { value: scrollHeight, configurable: true },
      })
      document.body.appendChild(el)
      return el
    }
    const fallbackRoot = () => document.scrollingElement || document.documentElement

    it("accepts a marker with overflow-y scroll", () => {
      const marker = makeElement("div", "scroll", 200)
      marker.setAttribute("data-scroll-root", "")
      expect(getScrollRoot()).toBe(marker)
    })

    it("rejects overflowing content that is not a scroll container", () => {
      const marker = makeElement("div", "visible", 200)
      marker.setAttribute("data-scroll-root", "")
      expect(getScrollRoot()).toBe(fallbackRoot())
    })

    it("rejects a scroll container whose content fits exactly", () => {
      const marker = makeElement("div", "auto", 100, 100)
      marker.setAttribute("data-scroll-root", "")
      expect(getScrollRoot()).toBe(fallbackRoot())
    })

    it("skips a non-scrollable main element", () => {
      makeElement("main", "visible", 100, 100)
      expect(getScrollRoot()).toBe(fallbackRoot())
    })
  })

  describe("smoothToTop animation fallback", () => {
    it("eases from the start position to the top over 420ms and then stops", () => {
      const el = document.createElement("div")
      Object.defineProperty(el, "scrollTo", {
        value: () => {
          throw new Error("unsupported")
        },
      })
      Object.defineProperty(el, "scrollTop", { value: 100, writable: true })
      const frames: FrameRequestCallback[] = []
      vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
        frames.push(cb)
        return frames.length
      })

      smoothToTop(el)
      expect(frames).toHaveLength(1)

      frames[0]!(1000)
      expect(el.scrollTop).toBe(100)
      expect(frames).toHaveLength(2)

      frames[1]!(1210)
      // p = 0.5 -> eased = 1 - 0.5^3 = 0.875 -> round(100 * 0.125)
      expect(el.scrollTop).toBe(13)
      expect(frames).toHaveLength(3)

      frames[2]!(1420)
      expect(el.scrollTop).toBe(0)
      expect(frames).toHaveLength(3)
    })
  })

  describe("markIfFromBottom threshold", () => {
    it("treats a position exactly at the 24px threshold as near the bottom", () => {
      const root = document.createElement("div")
      root.setAttribute("data-scroll-root", "")
      root.style.overflowY = "auto"
      Object.defineProperties(root, {
        scrollTop: { value: 176, configurable: true },
        clientHeight: { value: 100, configurable: true },
        scrollHeight: { value: 300, configurable: true },
      })
      document.body.appendChild(root)

      markIfFromBottom()

      expect(sessionStorage.getItem("__scrollTopNext")).toBe("1")
    })
  })
})
