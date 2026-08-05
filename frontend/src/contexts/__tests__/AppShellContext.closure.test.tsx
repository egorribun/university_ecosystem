import { act, renderHook } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AppShellProvider, useAppShell } from "@/contexts/AppShellContext"

const wrapper = ({ children }: PropsWithChildren) => <AppShellProvider>{children}</AppShellProvider>

afterEach(() => {
  vi.restoreAllMocks()
  document.body.classList.remove("blurred")
  document.body.style.overflow = ""
  window.sessionStorage.clear()
})

describe("AppShellContext — defensive scroll branches", () => {
  it("uses smooth scrolling when matchMedia is unavailable and only the document root remains", () => {
    const originalMatchMedia = window.matchMedia
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: undefined,
    })

    const scrollTo = vi.fn()
    Object.defineProperty(document.documentElement, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      overflowY: "visible",
    } as CSSStyleDeclaration)

    try {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.scrollToTop()
      })

      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: originalMatchMedia,
      })
    }
  })

  it("returns safely when scroll restoration has no document root target", () => {
    window.sessionStorage.setItem("__scrollTopNext", "1")
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      overflowY: "visible",
    } as CSSStyleDeclaration)
    vi.spyOn(document, "documentElement", "get").mockReturnValue(null as unknown as HTMLElement)
    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")

    const { result } = renderHook(() => useAppShell(), { wrapper })

    act(() => {
      result.current.restoreScrollIfNeeded()
    })

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()
    expect(requestAnimationFrame).not.toHaveBeenCalled()
  })

  it("no-ops scroll-to-top and snapshot marking when no scroll root exists", () => {
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      overflowY: "visible",
    } as CSSStyleDeclaration)
    vi.spyOn(document, "documentElement", "get").mockReturnValue(null as unknown as HTMLElement)

    const { result } = renderHook(() => useAppShell(), { wrapper })

    act(() => {
      result.current.scrollToTop("auto")
      result.current.markScrollSnapshot()
    })

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()
  })

  it("uses auto behavior for a reduced-motion deferred restore", () => {
    window.sessionStorage.setItem("__scrollTopNext", "1")
    const scrollRoot = document.createElement("div")
    scrollRoot.setAttribute("data-scroll-root", "")
    Object.defineProperty(scrollRoot, "scrollHeight", { configurable: true, value: 2000 })
    Object.defineProperty(scrollRoot, "clientHeight", { configurable: true, value: 500 })
    const scrollTo = vi.fn()
    Object.defineProperty(scrollRoot, "scrollTo", { configurable: true, value: scrollTo })
    document.body.appendChild(scrollRoot)
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      overflowY: "auto",
    } as CSSStyleDeclaration)
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.push(callback)
      return frames.length
    })

    try {
      const { result } = renderHook(() => useAppShell(), { wrapper })

      act(() => {
        result.current.restoreScrollIfNeeded()
      })
      act(() => {
        frames.shift()?.(0)
      })
      act(() => {
        frames.shift()?.(0)
      })

      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })
    } finally {
      scrollRoot.remove()
    }
  })

  it("swallows session-storage failures while marking and consuming snapshots", () => {
    const scrollRoot = document.createElement("div")
    scrollRoot.setAttribute("data-scroll-root", "")
    Object.defineProperty(scrollRoot, "scrollHeight", { configurable: true, value: 2000 })
    Object.defineProperty(scrollRoot, "clientHeight", { configurable: true, value: 500 })
    Object.defineProperty(scrollRoot, "scrollTop", {
      configurable: true,
      writable: true,
      value: 1600,
    })
    document.body.appendChild(scrollRoot)
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      overflowY: "auto",
    } as CSSStyleDeclaration)
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage write unavailable")
    })
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage read unavailable")
    })

    try {
      const { result } = renderHook(() => useAppShell(), { wrapper })
      expect(() => {
        result.current.markScrollSnapshot()
        result.current.restoreScrollIfNeeded()
      }).not.toThrow()
    } finally {
      scrollRoot.remove()
    }
  })

  it("does not restore a snapshot when the marker contains a different value", () => {
    window.sessionStorage.setItem("__scrollTopNext", "0")
    const { result } = renderHook(() => useAppShell(), { wrapper })

    act(() => {
      result.current.restoreScrollIfNeeded()
    })

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBe("0")
  })
})
