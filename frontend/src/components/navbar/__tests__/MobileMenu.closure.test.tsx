import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createElement, type HTMLAttributes, type ReactNode } from "react"

const motionState = vi.hoisted(() => ({
  entries: [] as Array<{ tag: string; props: Record<string, unknown> }>,
}))

const translationState = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

const overlayState = vi.hoisted(() => ({
  setOverlayState: vi.fn(),
}))

const swipeState = vi.hoisted(() => ({
  config: undefined as
    | {
        direction: string
        threshold: number
        enabled: boolean
        onSwipeClose: () => void
      }
    | undefined,
  dragOffset: 12,
}))

const serializeMotionValue = (value: unknown): string | undefined => {
  if (value === undefined) return undefined
  return typeof value === "string" ? value : JSON.stringify(value)
}

vi.mock("framer-motion", () => {
  const makeMotionElement = (tag: string) => {
    const MotionElement = ({
      children,
      initial,
      animate,
      exit,
      transition,
      whileTap,
      variants: _variants,
      ...props
    }: HTMLAttributes<HTMLElement> &
      Record<string, unknown> & {
        children?: ReactNode
        initial?: unknown
        animate?: unknown
        exit?: unknown
        transition?: unknown
        whileTap?: unknown
      }) => {
      motionState.entries.push({
        tag,
        props: { initial, animate, exit, transition, whileTap, ...props },
      })
      return createElement(
        tag,
        {
          ...props,
          "data-motion-initial": serializeMotionValue(initial),
          "data-motion-animate": serializeMotionValue(animate),
          "data-motion-exit": serializeMotionValue(exit),
          "data-motion-transition": serializeMotionValue(transition),
          "data-motion-while-tap": serializeMotionValue(whileTap),
        },
        children
      )
    }
    return MotionElement
  }

  return {
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    m: {
      button: makeMotionElement("button"),
      div: makeMotionElement("div"),
      li: makeMotionElement("li"),
    },
  }
})

vi.mock("react-i18next", () => ({ useTranslation: translationState.useTranslation }))

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

vi.mock("@/contexts/AppShellContext", () => ({ useAppShell: () => overlayState }))

vi.mock("@/hooks/useSwipeGesture", () => ({
  useSwipeGesture: (config: typeof swipeState.config) => {
    swipeState.config = config
    return {
      dragOffset: swipeState.dragOffset,
      handlers: { onTouchEnd: () => swipeState.config?.onSwipeClose() },
    }
  },
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

beforeEach(() => {
  motionState.entries.length = 0
  translationState.useTranslation.mockClear()
  overlayState.setOverlayState.mockClear()
  swipeState.config = undefined
  swipeState.dragOffset = 12
})

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
    const notificationsTrigger = document.createElement("button")
    notificationsTrigger.id = "global-notifications-btn"
    const notificationClick = vi.fn()
    notificationsTrigger.addEventListener("click", notificationClick)
    document.body.append(notificationsTrigger)

    const dialog = screen.getByRole("dialog", { name: "navigation:aria.mobileMenu" })
    expect(dialog).toHaveClass("h-dvh", "max-h-dvh")
    expect(dialog).toHaveAttribute("aria-describedby", "mobile-drawer-description")
    expect(dialog).toHaveAttribute("tabindex", "-1")
    expect(
      screen.getByRole("navigation", { name: "navigation:aria.mobileMenu" })
    ).toBeInTheDocument()
    expect(screen.getByTestId("schedule-icon")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("data-active", "true")
    expect(document.getElementById("mobile-nav-link-home")).toBeInTheDocument()
    expect(document.getElementById("mobile-nav-link-schedule")).toBeInTheDocument()
    expect(
      screen.getByText(
        (content) => content === `© ${new Date().getFullYear()} navigation:brandName`
      )
    ).toBeInTheDocument()
    expect(translationState.useTranslation).toHaveBeenCalledWith(["navigation"])
    expect(swipeState.config).toEqual(
      expect.objectContaining({ direction: "right", threshold: 80, enabled: true })
    )
    expect(overlayState.setOverlayState).toHaveBeenCalledWith("mobile-drawer", {
      scrollLocked: true,
      blurred: true,
    })

    const backdrop = screen.getByTestId("mobile-menu-backdrop")
    expect(backdrop).toHaveAttribute("data-motion-initial", '{"opacity":0}')
    expect(backdrop).toHaveAttribute("data-motion-animate", '{"opacity":1}')
    expect(backdrop).toHaveAttribute("data-motion-transition", '{"duration":0.2}')
    expect(dialog).toHaveAttribute("data-motion-initial", '{"x":"100%"}')
    expect(dialog).toHaveAttribute("data-motion-animate", '{"x":12}')
    expect(dialog).toHaveAttribute(
      "data-motion-transition",
      '{"type":"spring","stiffness":300,"damping":28,"mass":0.8}'
    )
    expect(dialog).toHaveClass(
      "fixed",
      "inset-y-0",
      "right-0",
      "z-overlay",
      "drawer-glass",
      "glass-noise",
      "shadow-glass-strong"
    )
    const closeButtons = screen.getAllByRole("button", { name: "navigation:aria.closeMenu" })
    expect(closeButtons.at(-1)).toHaveAttribute("data-motion-while-tap", '{"scale":0.9}')
    expect(closeButtons.at(-1)).toHaveAttribute(
      "data-motion-transition",
      '{"type":"spring","stiffness":260,"damping":25,"mass":1}'
    )
    const separator = document.querySelector('[style*="var(--glass-border)"]') as HTMLElement | null
    expect(separator).toHaveStyle({
      background: "linear-gradient(90deg, transparent, var(--glass-border), transparent)",
    })

    const navEntries = motionState.entries.filter(({ tag }) => tag === "li")
    expect(navEntries[0]?.props.initial).toEqual({ opacity: 0, x: 20 })
    expect(navEntries[0]?.props.animate).toEqual({ opacity: 1, x: 0 })
    expect(navEntries[0]?.props.transition).toEqual(
      expect.objectContaining({ delay: 0.05, type: "spring" })
    )
    expect(navEntries[1]?.props.transition).toEqual(
      expect.objectContaining({ delay: 0.08, type: "spring" })
    )
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("data-active")

    await user.click(screen.getByRole("button", { name: "profile-action" }))
    expect(go).toHaveBeenCalledWith("/profile")
    await user.click(screen.getByRole("button", { name: "settings-action" }))
    expect(go).toHaveBeenCalledWith("/settings")
    await user.click(screen.getByRole("button", { name: "notifications-action" }))
    expect(notificationClick).toHaveBeenCalledOnce()
    await user.click(screen.getByRole("button", { name: "search-action" }))
    await user.click(screen.getByRole("link", { name: "Schedule" }))

    expect(onClose).toHaveBeenCalledTimes(5)
    expect(searchEvents.some((event) => event.key === "k" && event.metaKey)).toBe(true)
    window.removeEventListener("keydown", onKeyDown)
    notificationsTrigger.remove()
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

  it("keeps the profile private when a stale user object is supplied while signed out", () => {
    renderMenu({ isAuth: false, user })

    expect(screen.queryByRole("button", { name: "profile-action" })).not.toBeInTheDocument()
  })

  it("cleans up overlay state and keeps current callbacks across rerenders", () => {
    const firstClose = vi.fn()
    const secondClose = vi.fn()
    const view = renderMenu({ onClose: firstClose })

    expect(overlayState.setOverlayState).toHaveBeenCalledWith("mobile-drawer", {
      scrollLocked: true,
      blurred: true,
    })
    view.rerender(
      <MobileMenu
        isOpen
        onClose={secondClose}
        menuLinks={links}
        isActive={(to) => to === "/dashboard"}
        go={vi.fn()}
        user={user}
        isAuth
        prefersReducedMotion={false}
        drawerTrapRef={{ current: null }}
      />
    )
    swipeState.config?.onSwipeClose()
    expect(secondClose).toHaveBeenCalledOnce()
    expect(firstClose).not.toHaveBeenCalled()

    view.rerender(
      <MobileMenu
        isOpen={false}
        onClose={secondClose}
        menuLinks={links}
        isActive={() => false}
        go={vi.fn()}
        user={null}
        isAuth={false}
        prefersReducedMotion={false}
        drawerTrapRef={{ current: null }}
      />
    )
    expect(overlayState.setOverlayState).toHaveBeenLastCalledWith("mobile-drawer", null)
    view.unmount()
    expect(overlayState.setOverlayState).toHaveBeenLastCalledWith("mobile-drawer", null)
  })

  it("uses reduced-motion-safe transitions and item/link semantics", () => {
    renderMenu({ prefersReducedMotion: true, isAuth: false, user: null })

    const backdrop = screen.getByTestId("mobile-menu-backdrop")
    expect(backdrop).toHaveAttribute("data-motion-transition", '{"duration":0}')
    const dialog = screen.getByRole("dialog", { name: "navigation:aria.mobileMenu" })
    expect(dialog).toHaveAttribute("data-motion-transition", '{"duration":0}')
    const closeButtons = screen.getAllByRole("button", { name: "navigation:aria.closeMenu" })
    expect(closeButtons.at(-1)).not.toHaveAttribute("data-motion-while-tap")
    const navEntries = motionState.entries.filter(({ tag }) => tag === "li")
    expect(navEntries[0]?.props.initial).toBe(false)
    expect(navEntries[0]?.props.transition).toEqual({ duration: 0 })
    expect(overlayState.setOverlayState).toHaveBeenCalledWith("mobile-drawer", {
      scrollLocked: true,
      blurred: false,
    })
  })

  it("does not throw when the global notifications trigger is absent", async () => {
    const user = userEvent.setup()
    const { onClose } = renderMenu({ isAuth: false, user: null })

    await user.click(screen.getByRole("button", { name: "notifications-action" }))
    expect(onClose).toHaveBeenCalledOnce()
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

  it("clears the overlay both when closing and when an open drawer unmounts", () => {
    const view = renderMenu()

    expect(overlayState.setOverlayState).toHaveBeenNthCalledWith(1, "mobile-drawer", {
      scrollLocked: true,
      blurred: true,
    })

    view.rerender(
      <MobileMenu
        isOpen={false}
        onClose={vi.fn()}
        menuLinks={links}
        isActive={() => false}
        go={vi.fn()}
        user={null}
        isAuth={false}
        prefersReducedMotion={false}
        drawerTrapRef={{ current: null }}
      />
    )

    // The previous effect cleanup and the closed-state effect must both clear
    // the shared overlay; relying only on cleanup leaves stale state when the
    // drawer remains mounted in a closed state.
    expect(overlayState.setOverlayState).toHaveBeenNthCalledWith(2, "mobile-drawer", null)
    expect(overlayState.setOverlayState).toHaveBeenNthCalledWith(3, "mobile-drawer", null)

    overlayState.setOverlayState.mockClear()
    const openView = renderMenu()
    openView.unmount()
    expect(overlayState.setOverlayState).toHaveBeenCalledTimes(2)
    expect(overlayState.setOverlayState).toHaveBeenLastCalledWith("mobile-drawer", null)

    view.unmount()
  })

  it("removes the Escape listener on unmount and registers a keydown cleanup", () => {
    const removeEventListener = vi.spyOn(window, "removeEventListener")
    const { onClose, unmount } = renderMenu()

    unmount()

    expect(removeEventListener).toHaveBeenCalledWith("keydown", expect.any(Function))
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    expect(onClose).not.toHaveBeenCalled()
    removeEventListener.mockRestore()
  })

  it("dispatches a bubbling Cmd+K event with the modifier preserved", async () => {
    const user = userEvent.setup()
    const events: KeyboardEvent[] = []
    const listener = (event: KeyboardEvent) => {
      if (event.key === "k") events.push(event)
    }
    window.addEventListener("keydown", listener)

    renderMenu({ isAuth: false, user: null })
    await user.click(screen.getByRole("button", { name: "search-action" }))

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({ key: "k", metaKey: true, bubbles: true })
    window.removeEventListener("keydown", listener)
  })

  it("exposes the drawer description, backdrop semantics, safe width, and accent", () => {
    renderMenu({ isAuth: false, user: null })

    const backdrop = screen.getByTestId("mobile-menu-backdrop")
    expect(backdrop).toHaveAttribute("aria-label", "navigation:aria.closeMenu")
    expect(backdrop).toHaveAttribute("tabindex", "-1")

    const drawer = screen.getByRole("dialog", { name: "navigation:aria.mobileMenu" })
    expect(drawer).toHaveClass("w-(--drawer-w)", "max-w-(--drawer-w-max)")
    expect(screen.getByText("navigation:aria.mobileMenuDescription")).toBeInTheDocument()
    expect(document.querySelector('[style*="var(--drawer-accent-gradient)"]')).toBeInTheDocument()
  })

  it("clamps a negative swipe offset instead of translating the drawer left", () => {
    swipeState.dragOffset = -12
    renderMenu()

    expect(screen.getByRole("dialog")).toHaveAttribute("data-motion-animate", '{"x":0}')
  })

  it("keeps the reduced-motion close transition explicit", () => {
    renderMenu({ prefersReducedMotion: true, isAuth: false, user: null })

    const reducedTransitions = motionState.entries.filter(
      ({ tag, props }) => tag === "button" && props.transition !== undefined
    )
    expect(reducedTransitions.map(({ props }) => props.transition)).toEqual([
      { duration: 0 },
      { duration: 0 },
    ])
  })
})
