import { screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
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
})
