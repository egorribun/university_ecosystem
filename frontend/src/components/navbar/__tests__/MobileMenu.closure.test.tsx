import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    onClick,
    children,
    ...props
  }: {
    to: string
    onClick?: () => void
    children?: ReactNode
  }) => (
    <a href={to} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: vi.fn() }),
}))

vi.mock("@/hooks/useSwipeGesture", () => ({
  useSwipeGesture: ({ onSwipeClose }: { onSwipeClose: () => void }) => ({
    dragOffset: 12,
    handlers: { onTouchEnd: onSwipeClose },
  }),
}))

vi.mock("@/components/navbar/MobileDrawerProfile", () => ({
  MobileDrawerProfile: ({ onProfileClick }: { onProfileClick: () => void }) => (
    <button type="button" onClick={onProfileClick}>
      profile-action
    </button>
  ),
}))

vi.mock("@/components/navbar/MobileDrawerQuickActions", () => ({
  MobileDrawerQuickActions: ({
    onSearch,
    onNotifications,
    onSettings,
  }: {
    onSearch: () => void
    onNotifications: () => void
    onSettings: () => void
  }) => (
    <div>
      <button type="button" onClick={onSearch}>
        search-action
      </button>
      <button type="button" onClick={onNotifications}>
        notifications-action
      </button>
      <button type="button" onClick={onSettings}>
        settings-action
      </button>
    </div>
  ),
}))

import { MobileMenu } from "../MobileMenu"

const links = [
  { to: "/", label: "Home" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/schedule", label: "Schedule", icon: () => <span data-testid="schedule-icon" /> },
]

const user = { id: "user-1", email: "user@example.com" } as never

function renderMenu(overrides: Partial<React.ComponentProps<typeof MobileMenu>> = {}) {
  const onClose = vi.fn()
  const go = vi.fn()
  const drawerTrapRef = { current: null }
  const props = {
    isOpen: true,
    onClose,
    menuLinks: links,
    isActive: (to: string) => to === "/dashboard",
    go,
    user,
    isAuth: true,
    prefersReducedMotion: false,
    drawerTrapRef,
    ...overrides,
  }
  return { onClose, go, ...render(<MobileMenu {...props} />) }
}

describe("MobileMenu closure paths", () => {
  it("renders authenticated navigation and wires every drawer action", async () => {
    const user = userEvent.setup()
    const searchEvents: KeyboardEvent[] = []
    const onKeyDown = (event: KeyboardEvent) => searchEvents.push(event)
    window.addEventListener("keydown", onKeyDown)
    const { onClose, go } = renderMenu()

    expect(screen.getByRole("dialog", { name: "navigation:aria.mobileMenu" })).toBeInTheDocument()
    expect(screen.getByTestId("schedule-icon")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("data-active", "true")
    expect(document.getElementById("mobile-nav-link-home")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "profile-action" }))
    expect(go).toHaveBeenCalledWith("/profile")
    await user.click(screen.getByRole("button", { name: "settings-action" }))
    expect(go).toHaveBeenCalledWith("/settings")
    await user.click(screen.getByRole("button", { name: "notifications-action" }))
    await user.click(screen.getByRole("button", { name: "search-action" }))
    await user.click(screen.getByRole("link", { name: "Schedule" }))

    expect(onClose).toHaveBeenCalledTimes(5)
    expect(searchEvents.some((event) => event.key === "k" && event.metaKey)).toBe(true)
    window.removeEventListener("keydown", onKeyDown)
  })

  it("closes from backdrop, close button, swipe, and Escape", async () => {
    const user = userEvent.setup()
    const { onClose } = renderMenu()

    await user.click(screen.getByTestId("mobile-menu-backdrop"))
    const closeButtons = screen.getAllByRole("button", { name: "navigation:aria.closeMenu" })
    await user.click(closeButtons[0]!)
    fireEvent.touchEnd(screen.getByRole("dialog"))
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))

    expect(onClose).toHaveBeenCalledTimes(4)
  })

  it("renders nothing while closed and supports unauthenticated reduced-motion mode", () => {
    const { container } = renderMenu({
      isOpen: false,
      isAuth: false,
      user: null,
      prefersReducedMotion: true,
    })

    expect(container).toBeEmptyDOMElement()
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
  })

  it("renders the open unauthenticated drawer and respects a prevented Escape", () => {
    const { onClose } = renderMenu({ isAuth: false, user: null, prefersReducedMotion: true })

    expect(screen.getByRole("dialog", { name: "navigation:aria.mobileMenu" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "profile-action" })).not.toBeInTheDocument()

    const event = new KeyboardEvent("keydown", { key: "Escape", cancelable: true })
    event.preventDefault()
    window.dispatchEvent(event)
    expect(onClose).not.toHaveBeenCalled()
  })
})
