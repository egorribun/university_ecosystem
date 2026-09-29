import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const encode = (value: unknown) => (value === undefined ? undefined : JSON.stringify(value))

vi.mock("framer-motion", () => ({
  m: {
    button: ({
      children,
      transition,
      whileTap,
      ...props
    }: {
      children?: ReactNode
      transition?: unknown
      whileTap?: unknown
      [key: string]: unknown
    }) => (
      <button
        {...(props as React.ButtonHTMLAttributes<HTMLButtonElement>)}
        data-transition={encode(transition)}
        data-while-tap={encode(whileTap)}
      >
        {children}
      </button>
    ),
    div: ({
      animate,
      children,
      className,
      initial,
      transition,
    }: {
      animate?: unknown
      children?: ReactNode
      className?: string
      initial?: unknown
      transition?: unknown
    }) => (
      <div
        className={className}
        data-animate={encode(animate)}
        data-initial={encode(initial)}
        data-transition={encode(transition)}
      >
        {children}
      </div>
    ),
  },
}))

vi.mock("lucide-react", () => ({
  Menu: ({ className, strokeWidth }: { className?: string; strokeWidth?: number }) => (
    <svg className={className} data-stroke-width={strokeWidth} data-testid="menu-icon" />
  ),
  X: ({ className, strokeWidth }: { className?: string; strokeWidth?: number }) => (
    <svg className={className} data-stroke-width={strokeWidth} data-testid="close-icon" />
  ),
}))

vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <span data-testid="notifications-bell" />,
}))

vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <span data-testid="messenger-button" />,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    alt,
    cacheV,
    className,
    fallback,
    srcRaw,
    title,
  }: {
    alt: string
    cacheV?: unknown
    className?: string
    fallback?: string
    srcRaw?: string
    title?: string
  }) => (
    <img
      alt={alt}
      className={className}
      data-cache-v={cacheV === undefined ? "undefined" : String(cacheV)}
      data-fallback={fallback}
      data-testid="smart-image"
      src={srcRaw}
      title={title}
    />
  ),
}))

vi.mock("../DesktopNav", () => ({
  DesktopNav: (props: { isCompact: boolean; menuLinks: unknown[] }) => (
    <div
      data-compact={String(props.isCompact)}
      data-links={JSON.stringify(props.menuLinks)}
      data-testid="desktop-nav"
    />
  ),
}))

vi.mock("../NavbarOverflowMenu", () => ({
  NavbarOverflowMenu: (props: { isCompact: boolean; items: unknown[] }) => (
    <div
      data-compact={String(props.isCompact)}
      data-items={JSON.stringify(props.items)}
      data-testid="overflow-menu"
    />
  ),
}))

vi.mock("../UserMenu", () => ({
  UserMenu: (props: { isAuth: boolean; loading: boolean }) => (
    <div
      data-auth={String(props.isAuth)}
      data-loading={String(props.loading)}
      data-testid="user-menu"
    />
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
    avatarSource: "",
    avatarFallback: "/fallback.png",
    avatarCacheV: 42,
    profileAlt: "Profile avatar",
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

describe("NavbarActions mutation contracts", () => {
  it("renders the mobile profile only for an authenticated, loaded user", () => {
    const { rerender } = render(
      <NavbarActions
        logic={createLogic({ isMobile: true, isAuth: true, user: { id: "user-1" } })}
        morph={createMorph()}
      />
    )
    expect(screen.getByRole("button", { name: "Open profile" })).toBeInTheDocument()

    rerender(
      <NavbarActions
        logic={createLogic({ isMobile: true, isAuth: true, user: { id: "user-1" }, loading: true })}
        morph={createMorph()}
      />
    )
    expect(screen.queryByRole("button", { name: "Open profile" })).not.toBeInTheDocument()
    expect(screen.queryByTestId("smart-image")).not.toBeInTheDocument()

    rerender(
      <NavbarActions
        logic={createLogic({ isMobile: true, isAuth: false, user: { id: "user-1" } })}
        morph={createMorph()}
      />
    )
    expect(screen.queryByRole("button", { name: "Open profile" })).not.toBeInTheDocument()

    rerender(
      <NavbarActions
        logic={createLogic({ isMobile: true, isAuth: true, user: null })}
        morph={createMorph()}
      />
    )
    expect(screen.queryByRole("button", { name: "Open profile" })).not.toBeInTheDocument()
  })

  it("publishes the mobile profile image contract and routes profile clicks", async () => {
    const go = vi.fn()
    const actions = userEvent.setup()
    render(
      <NavbarActions
        logic={createLogic({
          isMobile: true,
          isAuth: true,
          user: { id: "user-1" },
          avatarSource: "/avatar.webp",
          avatarCacheV: 7,
          profileAlt: "Named profile avatar",
          profileTitle: "Open profile",
          go,
        })}
        morph={createMorph()}
      />
    )

    const image = screen.getByTestId("smart-image")
    expect(image).toHaveAttribute("src", "/avatar.webp")
    expect(image).toHaveAttribute("data-cache-v", "7")
    expect(image).toHaveAttribute("data-fallback", "/fallback.png")
    expect(image).toHaveAttribute("title", "Open profile")
    expect(image).toHaveClass("size-8", "rounded-full", "object-cover")
    expect(screen.getByRole("button", { name: "Open profile" })).toHaveClass("size-11")

    await actions.click(screen.getByRole("button", { name: "Open profile" }))
    expect(go).toHaveBeenCalledWith("/profile")
  })

  it("uses spring profile tap and deterministic menu-icon animations when motion is enabled", () => {
    const { rerender } = render(
      <NavbarActions
        logic={createLogic({ isMobile: true, isAuth: true, user: { id: "user-1" } })}
        morph={createMorph()}
      />
    )

    const profile = screen.getByRole("button", { name: "Open profile" })
    expect(profile).toHaveAttribute("data-while-tap", JSON.stringify({ scale: 0.95 }))
    expect(profile).toHaveAttribute(
      "data-transition",
      JSON.stringify({ type: "spring", stiffness: 260, damping: 25, mass: 1 })
    )
    const animated = [...document.querySelectorAll<HTMLElement>("[data-animate]")]
    expect(animated).toHaveLength(2)
    expect(animated[0]).toHaveAttribute(
      "data-animate",
      JSON.stringify({ opacity: 1, rotate: 0, scale: 1 })
    )
    expect(animated[1]).toHaveAttribute(
      "data-animate",
      JSON.stringify({ opacity: 0, rotate: -90, scale: 0.5 })
    )
    expect(animated[0]).toHaveAttribute("data-initial", "false")
    expect(animated[1]).toHaveAttribute("data-initial", "false")
    expect(animated[0]).toHaveAttribute("data-transition", JSON.stringify({ duration: 0.2 }))
    expect(animated[1]).toHaveAttribute("data-transition", JSON.stringify({ duration: 0.2 }))

    rerender(
      <NavbarActions
        logic={createLogic({
          isMobile: true,
          mobileMenu: true,
          isAuth: true,
          user: { id: "user-1" },
        })}
        morph={createMorph()}
      />
    )
    const openAnimated = [...document.querySelectorAll<HTMLElement>("[data-animate]")]
    expect(openAnimated[0]).toHaveAttribute(
      "data-animate",
      JSON.stringify({ opacity: 0, rotate: 90, scale: 0.5 })
    )
    expect(openAnimated[1]).toHaveAttribute(
      "data-animate",
      JSON.stringify({ opacity: 1, rotate: 0, scale: 1 })
    )
  })

  it("removes tap animation and collapses icon transitions under reduced motion", () => {
    render(
      <NavbarActions
        logic={createLogic({
          isMobile: true,
          isAuth: true,
          user: { id: "user-1" },
          prefersReducedMotion: true,
        })}
        morph={createMorph()}
      />
    )

    expect(screen.getByRole("button", { name: "Open profile" })).not.toHaveAttribute(
      "data-while-tap"
    )
    expect(screen.getByRole("button", { name: "Open profile" })).toHaveAttribute(
      "data-transition",
      JSON.stringify({ duration: 0 })
    )
    for (const animated of document.querySelectorAll<HTMLElement>("[data-animate]")) {
      expect(animated).toHaveAttribute("data-transition", JSON.stringify({ duration: 0 }))
    }
  })

  it("keeps mobile menu controls accessible and exposes both icon states", async () => {
    const setMobileMenu = vi.fn()
    const actions = userEvent.setup()
    render(
      <NavbarActions logic={createLogic({ isMobile: true, setMobileMenu })} morph={createMorph()} />
    )

    const menuButton = screen.getByRole("button", { name: "navigation:aria.openMenu" })
    expect(menuButton).toHaveAttribute("aria-expanded", "false")
    expect(menuButton).toHaveAttribute("aria-controls", "mobile-drawer")
    expect(menuButton).toHaveClass("nav-action-btn", "text-text-primary")
    expect(screen.getByTestId("menu-icon")).toHaveClass(
      "nav-action-icon",
      "stroke-(--text-primary)"
    )
    expect(screen.getByTestId("menu-icon")).toHaveAttribute("data-stroke-width", "2.5")
    expect(screen.getByTestId("close-icon")).toHaveClass(
      "nav-action-icon",
      "stroke-(--text-primary)"
    )
    await actions.click(menuButton)
    expect(setMobileMenu).toHaveBeenCalledWith(expect.any(Function))
    expect(setMobileMenu.mock.calls[0]![0](false)).toBe(true)
  })

  it("renders desktop priority, overflow, and normalized user-menu contracts", () => {
    const logic = createLogic({ isAuth: true, user: { id: "user-1" }, loading: false })
    const morph = createMorph({
      isCompact: true,
      priorityLinks: [{ to: "/dashboard" }],
      overflowLinks: [{ to: "/settings" }],
    })
    const { rerender } = render(<NavbarActions logic={logic} morph={morph} />)

    expect(screen.getByTestId("desktop-nav")).toHaveAttribute("data-compact", "true")
    expect(screen.getByTestId("desktop-nav")).toHaveAttribute(
      "data-links",
      JSON.stringify([{ to: "/dashboard" }])
    )
    expect(screen.getByTestId("overflow-menu")).toHaveAttribute(
      "data-items",
      JSON.stringify([{ to: "/settings" }])
    )
    expect(screen.getByTestId("user-menu")).toHaveAttribute("data-auth", "true")
    expect(screen.getByTestId("user-menu")).toHaveAttribute("data-loading", "false")

    rerender(
      <NavbarActions
        logic={createLogic({ isAuth: false, user: null, loading: true })}
        morph={createMorph({ isCompact: false, priorityLinks: [], overflowLinks: [] })}
      />
    )
    expect(screen.queryByTestId("overflow-menu")).not.toBeInTheDocument()
    expect(screen.getByTestId("desktop-nav")).toHaveAttribute("data-compact", "false")
    expect(screen.getByTestId("user-menu")).toHaveAttribute("data-auth", "false")
    expect(screen.getByTestId("user-menu")).toHaveAttribute("data-loading", "true")
  })
})
