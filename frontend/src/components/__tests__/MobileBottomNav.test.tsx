import { act, fireEvent, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import MobileBottomNav from "@/components/layout/MobileBottomNav"
import i18n from "@/i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const mainNavLabel = () => i18n.t("navigation:aria.mainNavigation")

describe("MobileBottomNav", () => {
  it("does not render on auth pages", async () => {
    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/login",
      initialPath: "/login",
    })

    expect(screen.queryByRole("navigation", { name: mainNavLabel() })).toBeNull()
  })

  it("renders links for main sections", async () => {
    const { container } = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    const nav = screen.getByRole("navigation", { name: mainNavLabel() })
    expect(nav).toBeInTheDocument()
    const links = within(nav).getAllByRole("link")
    expect(links).toHaveLength(5)
    expect(
      links.map((link) => ({
        label: link.getAttribute("aria-label"),
        href: link.getAttribute("href"),
      }))
    ).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "News", href: "/news" },
      { label: "Events", href: "/events" },
      { label: "Schedule", href: "/schedule" },
      { label: "Profile", href: "/profile" },
    ])
    expect(links[0]).toHaveAttribute("aria-current", "page")
    for (const link of links.slice(1)) {
      expect(link).not.toHaveAttribute("aria-current")
    }
    for (const link of links) {
      expect(link).toHaveClass("h-full", "w-full", "min-h-11")
      expect(link).toHaveClass("focus-visible:shadow-focus")
      expect(link.querySelector("[data-nav-icon]")).toHaveClass("h-6", "w-6")
      expect(link.querySelector("[data-nav-label]")).toBeInTheDocument()
    }

    const indicator = container.querySelector("[data-nav-indicator]") as HTMLElement
    expect(indicator).toHaveClass("w-1/5", "transition-[transform,opacity]")
    expect(indicator.className).not.toContain("transition-all")
    expect(indicator).toHaveStyle({ transform: "translate3d(0%, 0, 0)" })

    expect(nav).toHaveClass(
      "fixed",
      "inset-x-0",
      "bottom-0",
      "grid",
      "h-[calc(var(--bottom-nav-h)+var(--safe-area-bottom))]",
      "grid-cols-5",
      "items-stretch",
      "transition-[transform,opacity]",
      "md:hidden",
      "translate-y-0",
      "opacity-100"
    )
    expect(links[0]!.querySelector("[data-nav-icon]")).toHaveClass(
      "-translate-y-px",
      "text-(--nav-active-color)"
    )
    expect(links[0]!.querySelector("[data-nav-label]")).toHaveClass("opacity-100")
    expect(links[1]!.querySelector("[data-nav-icon]")).toHaveClass(
      "translate-y-0",
      "text-(--text-secondary)",
      "group-hover:text-(--text-primary)"
    )
    expect(links[1]!.querySelector("[data-nav-label]")).toHaveClass("opacity-0")

    const spacer = container.querySelector("[data-bottom-nav-spacer]")
    expect(spacer).toHaveClass("block", "h-[calc(var(--bottom-nav-h)+var(--safe-area-bottom))]")
  })

  it("marks exactly one section current on a nested route and ignores prefix collisions", async () => {
    const nested = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/news/$slug",
      initialPath: "/news/story",
    })

    expect(
      within(screen.getByRole("navigation", { name: mainNavLabel() }))
        .getAllByRole("link")
        .filter((link) => link.getAttribute("aria-current") === "page")
    ).toHaveLength(1)
    expect(screen.getByRole("link", { name: /news/i })).toHaveAttribute("aria-current", "page")
    nested.unmount()

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/newsroom",
      initialPath: "/newsroom",
    })
    expect(
      screen.getAllByRole("link").filter((link) => link.hasAttribute("aria-current"))
    ).toHaveLength(0)
  })

  it("scrolls to the top when the active section is clicked again", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    fireEvent.click(screen.getByRole("link", { name: /home/i }))
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })

  it("allows navigation without scrolling when another section is clicked", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
      extraRoutes: [{ path: "/news", Component: () => <div>News destination</div> }],
    })

    fireEvent.click(screen.getByRole("link", { name: /news/i }))
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it("treats a trailing slash as the same active section", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard/",
    })

    fireEvent.click(screen.getByRole("link", { name: /home/i }))
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })

  it("does not render the bottom spacer on messenger routes", async () => {
    const { container } = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/messenger",
      initialPath: "/messenger",
    })

    expect(container.querySelector("[data-bottom-nav-spacer]")).not.toBeInTheDocument()
  })

  it("consumes the deferred scroll-to-top marker after mounting", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })
    const raf = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0)
      return 1
    })
    window.sessionStorage.setItem("__scrollTopNext", "1")

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
    expect(raf).toHaveBeenCalledOnce()
  })

  it("does not schedule deferred scrolling when no marker is present", async () => {
    const raf = vi.spyOn(window, "requestAnimationFrame")

    await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    expect(raf).not.toHaveBeenCalled()
  })

  it("cancels deferred scrolling and visual viewport listeners on unmount", async () => {
    const resizeListeners = new Set<EventListener>()
    const scrollListeners = new Set<EventListener>()
    const visualViewport = {
      height: window.innerHeight,
      scale: 1,
      addEventListener: vi.fn((type: string, listener: EventListener) => {
        ;(type === "resize" ? resizeListeners : scrollListeners).add(listener)
      }),
      removeEventListener: vi.fn((type: string, listener: EventListener) => {
        ;(type === "resize" ? resizeListeners : scrollListeners).delete(listener)
      }),
    }
    Object.defineProperty(window, "visualViewport", { configurable: true, value: visualViewport })
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(42)
    const cancelRaf = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined)
    window.sessionStorage.setItem("__scrollTopNext", "1")

    const result = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })
    expect(visualViewport.addEventListener).toHaveBeenCalledWith("resize", expect.any(Function))
    expect(visualViewport.addEventListener).toHaveBeenCalledWith("scroll", expect.any(Function))

    result.unmount()
    expect(cancelRaf).toHaveBeenCalledWith(42)
    expect(visualViewport.removeEventListener).toHaveBeenCalledWith("resize", expect.any(Function))
    expect(visualViewport.removeEventListener).toHaveBeenCalledWith("scroll", expect.any(Function))
  })

  it("hides navigation and its spacer only when the virtual keyboard is open", async () => {
    const listeners = new Set<EventListener>()
    const visualViewport = {
      height: window.innerHeight,
      scale: 1,
      addEventListener: vi.fn((_type: string, listener: EventListener) => listeners.add(listener)),
      removeEventListener: vi.fn((_type: string, listener: EventListener) =>
        listeners.delete(listener)
      ),
    }
    Object.defineProperty(window, "visualViewport", { configurable: true, value: visualViewport })

    const { container } = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })
    expect(screen.getByRole("navigation", { name: mainNavLabel() })).toHaveAttribute(
      "data-virtual-keyboard",
      "closed"
    )

    visualViewport.height = window.innerHeight - 100
    act(() => listeners.forEach((listener) => listener(new Event("resize"))))
    expect(screen.getByRole("navigation", { name: mainNavLabel() })).toHaveAttribute(
      "data-virtual-keyboard",
      "closed"
    )

    visualViewport.height = window.innerHeight - 200
    const input = document.createElement("input")
    document.body.appendChild(input)
    input.focus()
    act(() => listeners.forEach((listener) => listener(new Event("resize"))))

    expect(container.querySelector("nav[data-virtual-keyboard='open']")).toHaveAttribute(
      "aria-hidden",
      "true"
    )
    expect(container.querySelector("nav[data-virtual-keyboard='open']")).toHaveAttribute("inert")
    expect(container.querySelector("nav[data-virtual-keyboard='open']")).toHaveClass(
      "pointer-events-none",
      "translate-y-full",
      "opacity-0"
    )
    expect(container.querySelector("[data-bottom-nav-spacer]")).not.toBeInTheDocument()
  })

  it("does not mistake pinch zoom for the virtual keyboard", async () => {
    const listeners = new Set<EventListener>()
    const visualViewport = {
      height: window.innerHeight - 300,
      scale: 2,
      addEventListener: vi.fn((_type: string, listener: EventListener) => listeners.add(listener)),
      removeEventListener: vi.fn((_type: string, listener: EventListener) =>
        listeners.delete(listener)
      ),
    }
    Object.defineProperty(window, "visualViewport", { configurable: true, value: visualViewport })
    const input = document.createElement("input")
    document.body.appendChild(input)
    input.focus()

    const { container } = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/dashboard",
      initialPath: "/dashboard",
    })
    act(() => listeners.forEach((listener) => listener(new Event("resize"))))

    expect(screen.getByRole("navigation", { name: mainNavLabel() })).toHaveAttribute(
      "data-virtual-keyboard",
      "closed"
    )
    expect(container.querySelector("[data-bottom-nav-spacer]")).toBeInTheDocument()
  })

  it("uses the active indicator position for every navigable section", async () => {
    for (const [index, path] of [
      "/dashboard",
      "/news",
      "/events",
      "/schedule",
      "/profile",
    ].entries()) {
      const { container, unmount } = await renderWithRouter({
        ui: MobileBottomNav,
        path,
        initialPath: path,
      })
      expect(container.querySelector("[data-nav-indicator]")).toHaveStyle({
        transform: `translate3d(${index * 100}%, 0, 0)`,
      })
      unmount()
    }
  })

  it("does not render an indicator for an unrelated route", async () => {
    const { container } = await renderWithRouter({
      ui: MobileBottomNav,
      path: "/newsroom",
      initialPath: "/newsroom",
    })
    expect(container.querySelector("[data-nav-indicator]")).not.toBeInTheDocument()
  })
})
