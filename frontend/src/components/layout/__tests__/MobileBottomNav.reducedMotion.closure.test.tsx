import { fireEvent, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import MobileBottomNav from "@/components/layout/MobileBottomNav"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("MobileBottomNav reduced-motion closure", () => {
  beforeEach(() => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as MediaQueryList
    )
  })

  it("uses CSS reduced-motion fallbacks for the indicator and stable label", async () => {
    await renderWithRouter({
      ui: () => <MobileBottomNav />,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

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
})
