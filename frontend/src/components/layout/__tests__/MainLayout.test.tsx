import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { MainLayout } from "../MainLayout"

const mocks = vi.hoisted(() => ({
  routeType: { isCompactPage: false, hideFooter: false, isMessenger: false },
  t: (key: string) => key,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
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
    Element.prototype.scrollIntoView = vi.fn()
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
    fireEvent.click(screen.getByRole("link", { name: "navigation:aria.skipLink" }))
    expect(main).toHaveFocus()
    expect(main.scrollIntoView).toHaveBeenCalledWith({ block: "start" })
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
})
