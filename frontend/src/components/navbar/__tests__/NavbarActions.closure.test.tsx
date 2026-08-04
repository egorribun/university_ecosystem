import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("framer-motion", () => ({
  m: {
    div: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
}))

vi.mock("lucide-react", () => ({
  Menu: () => <span data-testid="menu-icon" />,
  X: () => <span data-testid="close-icon" />,
}))

vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <span data-testid="notifications-bell" />,
}))

vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <span data-testid="messenger-button" />,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, onClick }: { alt: string; onClick?: () => void }) => (
    <button type="button" aria-label={alt} onClick={onClick}>
      avatar
    </button>
  ),
}))

vi.mock("../DesktopNav", () => ({
  DesktopNav: ({ isCompact }: { isCompact: boolean }) => (
    <div data-testid="desktop-nav">compact:{String(isCompact)}</div>
  ),
}))

vi.mock("../NavbarOverflowMenu", () => ({
  NavbarOverflowMenu: ({ items }: { items: unknown[] }) => (
    <div data-testid="overflow-menu">items:{items.length}</div>
  ),
}))

vi.mock("../UserMenu", () => ({
  UserMenu: ({ isAuth, loading }: { isAuth: boolean; loading: boolean }) => (
    <div data-testid="user-menu">
      auth:{String(isAuth)} loading:{String(loading)}
    </div>
  ),
}))

import { NavbarActions } from "@/components/navbar/NavbarActions"

const createLogic = (overrides: Record<string, unknown> = {}) =>
  ({
    isMobile: false,
    mobileMenu: false,
    setMobileMenu: vi.fn(),
    isAuth: false,
    user: null,
    loading: false,
    avatarSource: null,
    avatarFallback: "fallback",
    avatarCacheV: "1",
    profileAlt: "Profile",
    profileTitle: "Open profile",
    go: vi.fn(),
    isActive: vi.fn(() => false),
    isSameTarget: vi.fn(() => false),
    scrollToTop: vi.fn(),
    markScrollFromBottom: vi.fn(),
    prefersReducedMotion: false,
    t: (key: string) => key,
    burgerBtnRef: { current: null },
    ...overrides,
  }) as never

const createMorph = (overrides: Record<string, unknown> = {}) =>
  ({
    isCompact: false,
    priorityLinks: [],
    overflowLinks: [],
    ...overrides,
  }) as never

describe("NavbarActions closure paths", () => {
  it("renders the authenticated mobile actions and toggles the menu", async () => {
    const user = userEvent.setup()
    const setMobileMenu = vi.fn()
    const go = vi.fn()
    render(
      <NavbarActions
        logic={createLogic({
          isMobile: true,
          isAuth: true,
          user: { id: "user-1" },
          avatarSource: "/avatar.png",
          setMobileMenu,
          go,
        })}
        morph={createMorph()}
      />
    )

    expect(screen.getByTestId("messenger-button")).toBeInTheDocument()
    expect(screen.getByTestId("notifications-bell")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Profile" }))
    expect(go).toHaveBeenCalledWith("/profile")

    const menuButton = screen.getByRole("button", { name: "navigation:aria.openMenu" })
    expect(menuButton).toHaveAttribute("aria-expanded", "false")
    await user.click(menuButton)
    expect(setMobileMenu).toHaveBeenCalledOnce()
    expect(setMobileMenu.mock.calls[0]![0](false)).toBe(true)
  })

  it("renders the mobile loading state and closed-menu icon branch", () => {
    render(
      <NavbarActions
        logic={createLogic({
          isMobile: true,
          mobileMenu: true,
          loading: true,
          prefersReducedMotion: true,
        })}
        morph={createMorph()}
      />
    )

    expect(screen.queryByRole("button", { name: "Profile" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "navigation:aria.closeMenu" })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
    expect(screen.getByTestId("menu-icon")).toBeInTheDocument()
    expect(screen.getByTestId("close-icon")).toBeInTheDocument()
  })

  it("renders desktop navigation with and without overflow items", () => {
    const { rerender } = render(
      <NavbarActions
        logic={createLogic()}
        morph={createMorph({ isCompact: true, overflowLinks: [{ to: "/more" }] })}
      />
    )

    expect(screen.getByTestId("desktop-nav")).toHaveTextContent("compact:true")
    expect(screen.getByTestId("overflow-menu")).toHaveTextContent("items:1")
    expect(screen.getByTestId("user-menu")).toHaveTextContent("auth:false loading:false")

    rerender(
      <NavbarActions
        logic={createLogic({ isAuth: true })}
        morph={createMorph({ overflowLinks: [] })}
      />
    )
    expect(screen.queryByTestId("overflow-menu")).not.toBeInTheDocument()
    expect(screen.getByTestId("user-menu")).toHaveTextContent("auth:true loading:false")
  })
})
