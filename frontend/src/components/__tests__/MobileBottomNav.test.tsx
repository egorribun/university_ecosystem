import { fireEvent, screen } from "@testing-library/react"
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
    expect(nav.querySelectorAll("a")).toHaveLength(5)
    expect(nav).toMatchSnapshot()
    expect(container).toMatchSnapshot()
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

    expect(container.querySelector('span[aria-hidden="true"]')).not.toBeInTheDocument()
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
})
