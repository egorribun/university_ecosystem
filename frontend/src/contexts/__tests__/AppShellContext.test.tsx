import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

import { AppShellProvider, useAppShell } from "@/contexts/AppShellContext"

const wrapper = ({ children }: { children: ReactNode }) => (
  <AppShellProvider>{children}</AppShellProvider>
)

beforeEach(() => {
  document.body.classList.remove("blurred")
  document.body.style.overflow = ""
  window.sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.classList.remove("blurred")
  document.body.style.overflow = ""
})

describe("AppShellContext", () => {
  describe("useAppShell hook", () => {
    it("throws when used outside AppShellProvider", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      expect(() => {
        renderHook(() => useAppShell())
      }).toThrow(/useAppShell must be used within an AppShellProvider/)

      errorSpy.mockRestore()
    })

    it("returns expected shape inside AppShellProvider", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      expect(result.current).toMatchObject({
        setOverlayState: expect.any(Function),
        scrollToTop: expect.any(Function),
        markScrollSnapshot: expect.any(Function),
        restoreScrollIfNeeded: expect.any(Function),
      })
    })
  })

  describe("setOverlayState", () => {
    it("adds 'blurred' class to body when blurred=true", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("modal-1", { blurred: true, scrollLocked: false })
      })

      expect(document.body.classList.contains("blurred")).toBe(true)
    })

    it("sets overflow hidden on body when scrollLocked=true", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("modal-1", { blurred: false, scrollLocked: true })
      })

      expect(document.body.style.overflow).toBe("hidden")
    })

    it("does not add 'blurred' when blurred=false", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("modal-1", { blurred: false, scrollLocked: false })
      })

      expect(document.body.classList.contains("blurred")).toBe(false)
    })

    it("aggregates overlay state — any blurred → blurred", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("overlay-a", { blurred: false, scrollLocked: false })
        result.current.setOverlayState("overlay-b", { blurred: true, scrollLocked: false })
      })

      expect(document.body.classList.contains("blurred")).toBe(true)
    })

    it("aggregates overlay state — any locked → locked", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("overlay-a", { blurred: false, scrollLocked: false })
        result.current.setOverlayState("overlay-b", { blurred: false, scrollLocked: true })
      })

      expect(document.body.style.overflow).toBe("hidden")
    })

    it("removing overlay (null state) recalculates aggregated state", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("overlay-a", { blurred: true, scrollLocked: true })
        result.current.setOverlayState("overlay-b", { blurred: true, scrollLocked: false })
      })

      expect(document.body.classList.contains("blurred")).toBe(true)

      act(() => {
        result.current.setOverlayState("overlay-a", null)
      })

      // overlay-b still has blurred=true
      expect(document.body.classList.contains("blurred")).toBe(true)

      act(() => {
        result.current.setOverlayState("overlay-b", null)
      })

      // No more overlays — blurred removed
      expect(document.body.classList.contains("blurred")).toBe(false)
      expect(document.body.style.overflow).not.toBe("hidden")
    })

    it("removing scroll-locked overlay restores previous overflow", () => {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("modal-1", { blurred: false, scrollLocked: true })
      })
      expect(document.body.style.overflow).toBe("hidden")

      act(() => {
        result.current.setOverlayState("modal-1", null)
      })
      expect(document.body.style.overflow).not.toBe("hidden")
    })
  })

  describe("scrollToTop", () => {
    it("calls scrollTo on the scroll root element", () => {
      // Create a scrollable element for getScrollRoot to find
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      scrollRoot.scrollTop = 500
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      scrollRoot.scrollTo = vi.fn()
      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop("auto")
      })

      expect(scrollRoot.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })

      document.body.removeChild(scrollRoot)
    })

    it("uses smooth behavior when no behavior specified and no reduced motion", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      scrollRoot.scrollTo = vi.fn()
      document.body.appendChild(scrollRoot)

      // Mock matchMedia to report no reduced motion preference
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop()
      })

      expect(scrollRoot.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })

      document.body.removeChild(scrollRoot)
    })

    it("uses auto behavior when reduced motion is preferred", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      scrollRoot.scrollTo = vi.fn()
      document.body.appendChild(scrollRoot)

      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: true,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop()
      })

      expect(scrollRoot.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })

      document.body.removeChild(scrollRoot)
    })

    it("defaults to smooth behavior when matchMedia throws", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      const scrollTo = vi.fn()
      Object.defineProperty(scrollRoot, "scrollTo", { value: scrollTo, configurable: true })
      document.body.appendChild(scrollRoot)
      vi.spyOn(window, "matchMedia").mockImplementation(() => {
        throw new Error("matchMedia unavailable")
      })

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop()
      })

      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
      document.body.removeChild(scrollRoot)
    })

    it("falls back to direct scrollTop when auto scrollTo throws", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 420,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      const scrollTo = vi.fn(() => {
        throw new Error("scrollTo unavailable")
      })
      Object.defineProperty(scrollRoot, "scrollTo", { value: scrollTo, configurable: true })
      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop("auto")
      })

      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })
      expect(scrollRoot.scrollTop).toBe(0)
      document.body.removeChild(scrollRoot)
    })

    it("animates through the RAF fallback when smooth scrollTo throws", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 420,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      const scrollTo = vi.fn(() => {
        throw new Error("smooth scroll unavailable")
      })
      Object.defineProperty(scrollRoot, "scrollTo", { value: scrollTo, configurable: true })
      document.body.appendChild(scrollRoot)

      const frames: FrameRequestCallback[] = []
      const requestAnimationFrame = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((callback) => {
          frames.push(callback)
          return frames.length
        })
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop("smooth")
      })

      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
      expect(requestAnimationFrame).toHaveBeenCalledTimes(1)
      const firstFrame = frames.shift()
      act(() => {
        firstFrame?.(100)
      })
      expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
      const secondFrame = frames.shift()
      act(() => {
        secondFrame?.(520)
      })
      expect(scrollRoot.scrollTop).toBe(0)
      document.body.removeChild(scrollRoot)
    })

    it("cancels a pending RAF fallback when the provider unmounts", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 420,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      Object.defineProperty(scrollRoot, "scrollTo", {
        value: vi.fn(() => {
          throw new Error("smooth scroll unavailable")
        }),
        configurable: true,
      })
      document.body.appendChild(scrollRoot)

      vi.spyOn(window, "requestAnimationFrame").mockReturnValue(17)
      const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
      const { result, unmount } = renderHook(() => useAppShell(), { wrapper })

      act(() => result.current.scrollToTop("smooth"))
      unmount()

      expect(cancelAnimationFrame).toHaveBeenCalledWith(17)
      document.body.removeChild(scrollRoot)
    })
  })

  describe("markScrollSnapshot / restoreScrollIfNeeded", () => {
    it("markScrollSnapshot stores flag when scroll position is near bottom", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 1000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 490,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.markScrollSnapshot()
      })

      expect(window.sessionStorage.getItem("__scrollTopNext")).toBe("1")

      document.body.removeChild(scrollRoot)
    })

    it("markScrollSnapshot does NOT store flag when not near bottom", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 100,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.markScrollSnapshot()
      })

      expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()

      document.body.removeChild(scrollRoot)
    })

    it("ignores sessionStorage write failures while marking a snapshot", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 1000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      Object.defineProperty(scrollRoot, "scrollTop", {
        value: 490,
        writable: true,
        configurable: true,
      })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      const setItem = vi.fn(() => {
        throw new Error("storage unavailable")
      })
      vi.spyOn(window, "sessionStorage", "get").mockReturnValue({
        setItem,
        getItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      } as unknown as Storage)
      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.markScrollSnapshot()
      })

      expect(setItem).toHaveBeenCalledWith("__scrollTopNext", "1")
      document.body.removeChild(scrollRoot)
    })

    it("restoreScrollIfNeeded consumes flag and scrolls to top", () => {
      window.sessionStorage.setItem("__scrollTopNext", "1")

      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      scrollRoot.scrollTo = vi.fn()
      document.body.appendChild(scrollRoot)

      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.restoreScrollIfNeeded()
      })

      // Flag should be consumed
      expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()

      document.body.removeChild(scrollRoot)
    })

    it("ignores sessionStorage read failures while restoring", () => {
      const getItem = vi.fn(() => {
        throw new Error("storage unavailable")
      })
      vi.spyOn(window, "sessionStorage", "get").mockReturnValue({
        setItem: vi.fn(),
        getItem,
        removeItem: vi.fn(),
        clear: vi.fn(),
      } as unknown as Storage)
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.restoreScrollIfNeeded()
      })

      expect(getItem).toHaveBeenCalledWith("__scrollTopNext")
    })

    it("runs the deferred restore frames and scrolls smoothly", () => {
      window.sessionStorage.setItem("__scrollTopNext", "1")

      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)
      const scrollTo = vi.fn()
      Object.defineProperty(scrollRoot, "scrollTo", { value: scrollTo, configurable: true })
      document.body.appendChild(scrollRoot)

      const deferredFrames: FrameRequestCallback[] = []
      const requestAnimationFrame = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((callback) => {
          deferredFrames.push(callback)
          return deferredFrames.length
        })
      vi.spyOn(window, "matchMedia").mockReturnValue({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      } as unknown as MediaQueryList)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.restoreScrollIfNeeded()
      })

      expect(requestAnimationFrame).toHaveBeenCalledTimes(1)
      const firstFrame = deferredFrames.shift()
      expect(firstFrame).toBeDefined()
      act(() => {
        firstFrame?.(0)
      })
      expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
      const secondFrame = deferredFrames.shift()
      expect(secondFrame).toBeDefined()
      act(() => {
        secondFrame?.(0)
      })
      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
      document.body.removeChild(scrollRoot)
    })

    it("restoreScrollIfNeeded does nothing when no flag is set", () => {
      const scrollRoot = document.createElement("div")
      scrollRoot.setAttribute("data-scroll-root", "")
      Object.defineProperty(scrollRoot, "scrollHeight", { value: 2000, configurable: true })
      Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
      vi.spyOn(window, "getComputedStyle").mockReturnValue({
        overflowY: "auto",
      } as CSSStyleDeclaration)

      scrollRoot.scrollTo = vi.fn()
      document.body.appendChild(scrollRoot)

      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.restoreScrollIfNeeded()
      })

      expect(scrollRoot.scrollTo).not.toHaveBeenCalled()

      document.body.removeChild(scrollRoot)
    })
  })

  describe("cleanup on unmount", () => {
    it("removes 'blurred' class and resets overflow on unmount", () => {
      const { result, unmount } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.setOverlayState("modal-1", { blurred: true, scrollLocked: true })
      })

      expect(document.body.classList.contains("blurred")).toBe(true)
      expect(document.body.style.overflow).toBe("hidden")

      unmount()

      expect(document.body.classList.contains("blurred")).toBe(false)
      expect(document.body.style.overflow).toBe("")
    })
  })
})
