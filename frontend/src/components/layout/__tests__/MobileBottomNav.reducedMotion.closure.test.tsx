import { act, fireEvent, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import MobileBottomNav from "@/components/layout/MobileBottomNav"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

let mediaQuery: MediaQueryList
let mediaQueryListeners: Array<(event: MediaQueryListEvent) => void>

describe("MobileBottomNav reduced-motion closure", () => {
  beforeEach(() => {
    mediaQueryListeners = []
    mediaQuery = {
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn((_type: string, listener: EventListener) => {
        mediaQueryListeners.push(listener as (event: MediaQueryListEvent) => void)
      }),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as MediaQueryList
    vi.spyOn(window, "matchMedia").mockImplementation(() => mediaQuery)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("uses CSS reduced-motion fallbacks for the indicator and stable label", async () => {
    await renderWithRouter({
      ui: () => <MobileBottomNav />,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    expect(window.matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    const indicator = document.querySelector("[data-nav-indicator]")
    expect(indicator).toHaveClass("motion-reduce:transition-none")
    expect(indicator).toHaveClass("transition-[transform,opacity]")
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page")
    expect(screen.getByText("Home")).toBeInTheDocument()
  })

  it("uses an immediate scroll for active-link and deferred-marker paths", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0)
      return 1
    })
    window.sessionStorage.setItem("__scrollTopNext", "1")

    await renderWithRouter({
      ui: () => <MobileBottomNav />,
      path: "/dashboard",
      initialPath: "/dashboard",
    })
    fireEvent.click(screen.getByRole("link", { name: "Home" }))

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })
    expect(scrollTo).toHaveBeenCalledTimes(2)
  })

  it("reprocesses a deferred scroll marker when reduced-motion preference changes", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })
    const raf = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0)
      return 1
    })

    await renderWithRouter({
      ui: () => <MobileBottomNav />,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    window.sessionStorage.setItem("__scrollTopNext", "1")
    Object.defineProperty(mediaQuery, "matches", { configurable: true, value: false })
    act(() => {
      mediaQueryListeners.forEach((listener) => listener({ matches: false } as MediaQueryListEvent))
    })

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()
    expect(raf).toHaveBeenCalled()
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })
})
