import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import type React from "react"
import { handleMainSkipLink, MainLayout } from "../MainLayout"

const mocks = vi.hoisted(() => ({
  routeType: { isCompactPage: false, hideFooter: false, isMessenger: false },
  t: (key: string) => key,
  useTranslation: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: (...args: unknown[]) => {
    mocks.useTranslation(...args)
    return { t: mocks.t }
  },
}))
vi.mock("@/hooks/useRouteType", () => ({ useRouteType: () => mocks.routeType }))
vi.mock("@/components/navbar", () => ({ default: () => <nav data-testid="navbar" /> }))
vi.mock("@/components/layout/Footer", () => ({ default: () => <footer data-testid="footer" /> }))
vi.mock("@/components/motion/BackToTop", () => ({
  default: () => <button data-testid="back-to-top" />,
}))
vi.mock("@/components/layout/MobileBottomNav", () => ({
  default: () => <nav data-testid="mobile-bottom-nav" />,
}))

describe("MainLayout", () => {
  beforeEach(() => {
    mocks.routeType = { isCompactPage: false, hideFooter: false, isMessenger: false }
    mocks.useTranslation.mockClear()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("renders standard chrome and moves keyboard focus to main via the skip link", () => {
    render(
      <MainLayout>
        <p>page content</p>
      </MainLayout>
    )

    expect(screen.getByTestId("navbar")).toBeInTheDocument()
    expect(screen.getByTestId("footer")).toBeInTheDocument()
    expect(screen.getByTestId("back-to-top")).toBeInTheDocument()
    expect(screen.getByTestId("mobile-bottom-nav")).toBeInTheDocument()

    const main = screen.getByRole("main")
    expect(main).toHaveAttribute("tabindex", "-1")
    expect(main).toHaveClass("vt-page-content", "w-full", "outline-none", "min-h-dvh")
    fireEvent.click(screen.getByRole("link", { name: "common:skipToMain" }))
    expect(main).toHaveFocus()
    expect(main.scrollIntoView).toHaveBeenCalledWith({ block: "start" })
    expect(mocks.useTranslation).toHaveBeenCalledWith(["navigation", "common"])
  })

  it("keeps the skip link safe when the main landmark is unavailable", () => {
    const getElementById = vi.spyOn(document, "getElementById").mockReturnValue(null)
    const event = { preventDefault: vi.fn() } as unknown as React.MouseEvent<HTMLAnchorElement>

    expect(() => handleMainSkipLink(event)).not.toThrow()
    expect(event.preventDefault).toHaveBeenCalledOnce()
    getElementById.mockRestore()
  })

  it("removes nonessential chrome on compact routes", () => {
    mocks.routeType = { isCompactPage: true, hideFooter: true, isMessenger: false }
    render(<MainLayout>compact content</MainLayout>)

    expect(screen.getByText("compact content")).toBeInTheDocument()
    expect(screen.queryByTestId("navbar")).not.toBeInTheDocument()
    expect(screen.queryByTestId("footer")).not.toBeInTheDocument()
    expect(screen.queryByTestId("back-to-top")).not.toBeInTheDocument()
    expect(screen.queryByTestId("mobile-bottom-nav")).not.toBeInTheDocument()
  })

  it("uses an explicit viewport height for the messenger route", () => {
    mocks.routeType = { isCompactPage: false, hideFooter: true, isMessenger: true }
    render(<MainLayout>messenger content</MainLayout>)

    expect(screen.getByRole("main")).toHaveClass(
      "h-[calc(100dvh-var(--navbar-h-base,4rem))]",
      "overflow-hidden"
    )
    expect(screen.queryByTestId("footer")).not.toBeInTheDocument()
  })

  it("renders lightweight landmark stubs in E2E mode", async () => {
    vi.stubEnv("VITE_E2E_MODE", "1")
    vi.resetModules()
    const { MainLayout: E2EMainLayout } = await import("../MainLayout")

    const { container } = render(<E2EMainLayout>e2e content</E2EMainLayout>)

    expect(container.querySelector('[data-e2e-stub="main-nav"]')).toBeInTheDocument()
    expect(container.querySelector('[data-e2e-stub="footer"]')).toBeInTheDocument()
    expect(container.querySelector('[data-e2e-stub="mobile-bottom-nav"]')).toBeInTheDocument()
    expect(container.querySelector('[data-e2e-stub="mobile-bottom-nav"]')).toHaveAttribute(
      "aria-label",
      "navigation:aria.mainNavigation"
    )
    expect(screen.queryByTestId("navbar")).not.toBeInTheDocument()
  })

  it("honors compact and footer-hidden flags in E2E mode", async () => {
    vi.stubEnv("VITE_E2E_MODE", "1")
    vi.resetModules()
    const { MainLayout: E2EMainLayout } = await import("../MainLayout")

    mocks.routeType = { isCompactPage: true, hideFooter: false, isMessenger: false }
    const compact = render(<E2EMainLayout>compact e2e content</E2EMainLayout>)
    expect(compact.container.querySelector('[data-e2e-stub="main-nav"]')).not.toBeInTheDocument()
    expect(compact.container.querySelector('[data-e2e-stub="footer"]')).not.toBeInTheDocument()
    expect(
      compact.container.querySelector('[data-e2e-stub="mobile-bottom-nav"]')
    ).not.toBeInTheDocument()
    compact.unmount()

    mocks.routeType = { isCompactPage: false, hideFooter: true, isMessenger: false }
    const withoutFooter = render(<E2EMainLayout>footer-hidden e2e content</E2EMainLayout>)
    expect(withoutFooter.container.querySelector('[data-e2e-stub="main-nav"]')).toBeInTheDocument()
    expect(
      withoutFooter.container.querySelector('[data-e2e-stub="footer"]')
    ).not.toBeInTheDocument()
    expect(
      withoutFooter.container.querySelector('[data-e2e-stub="mobile-bottom-nav"]')
    ).toBeInTheDocument()
  })
})
