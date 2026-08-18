import { useLocation } from "@tanstack/react-router"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import Navbar from "../navbar"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      full_name: "Jane Doe",
      role: "student",
      avatar_url: "",
      avatar_updated_at: 1,
    },
    isAuth: true,
    loading: false,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const translations: Record<string, string> = {
  "navigation:aria.homeLink": "Home",
  "navigation:brandAlt": "Brand",
  "navigation:brandName": "Great University",
  "navigation:aria.openMenu": "Open menu",
  "navigation:aria.closeMenu": "Close menu",
  "navigation:aria.mobileMenu": "Mobile navigation",
  "navigation:aria.close": "Close",
  "navigation:aria.profileAvatar": "Profile avatar",
  "navigation:aria.openProfile": "Open profile",
  "navigation:menu.dashboard": "Dashboard",
  "navigation:menu.news": "News",
  "navigation:menu.schedule": "Schedule",
  "navigation:menu.events": "Events",
  "navigation:menu.activity": "Activity",
  "navigation:menu.map": "Map",
  "navigation:menu.settings": "Settings",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) => {
      if (key === "navigation:aria.profileAvatarNamed") {
        return `Profile avatar for ${options?.name ?? "user"}`
      }
      return translations[key] ?? key
    },
  }),
}))

vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <div data-testid="notifications-bell" />,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, onClick }: { alt: string; onClick?: () => void }) => (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-redundant-roles
    <img src="avatar" alt={alt} role="img" data-testid="smart-image" onClick={onClick} />
  ),
}))

vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <button data-testid="messenger-button">Messenger</button>,
}))

vi.mock("framer-motion", () => {
  const motionComponent = (Tag: string) => {
    const Component = ({
      children,
      className,
      onClick,
      ...props
    }: React.ComponentProps<"div"> & { [key: string]: unknown }) => {
      const filteredProps = { ...props }
      const motionProps = [
        "initial",
        "animate",
        "exit",
        "variants",
        "transition",
        "whileHover",
        "whileTap",
        "whileFocus",
        "whileDrag",
        "whileInView",
        "viewport",
        "layout",
        "layoutId",
      ]
      motionProps.forEach((prop) => delete filteredProps[prop])
      const Element = Tag as React.ElementType
      return (
        <Element className={className} onClick={onClick} {...filteredProps}>
          {children}
        </Element>
      )
    }
    Component.displayName = `Motion(${Tag})`
    return Component as unknown as React.ComponentType<unknown>
  }
  // Wave 124 SW1 — also expose `m` (LazyMotion minimal component) since
  // production code now uses `<m.X>` JSX. Plus LazyMotion/MotionConfig/
  // domAnimation stubs so AppProviders' wrapper renders cleanly. useScroll +
  // useMotionValueEvent stubs preserved for any pre-Wave-124 callers still
  // depending on them (Navbar's own usage moved to native scroll listener
  // via useScrollBehavior refactor — Phase A).
  const motionProxy = {
    nav: motionComponent("nav"),
    div: motionComponent("div"),
    button: motionComponent("button"),
    li: motionComponent("li"),
    ul: motionComponent("ul"),
    span: motionComponent("span"),
    line: motionComponent("line"),
  }
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    LazyMotion: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    MotionConfig: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    domAnimation: {},
    domMax: {},
    motion: motionProxy,
    m: motionProxy,
    useReducedMotion: () => false,
    useScroll: () => ({ scrollY: { onChange: () => {} } }),
    useMotionValueEvent: () => {},
  }
})

const LocationDisplay = () => {
  const location = useLocation()
  return <div data-testid="location-display">{location.pathname}</div>
}

describe("Navbar", () => {
  const setupMatchMedia = ({
    mobile,
    reducedMotion,
  }: {
    mobile: boolean
    reducedMotion: boolean
  }) => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          media: query,
          matches: query.includes("max-width")
            ? mobile
            : query.includes("prefers-reduced-motion")
              ? reducedMotion
              : false,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )
  }

  const renderNavbar = (initialPath = "/dashboard") => {
    const Wrapped = () => (
      <AppShellProvider>
        <Navbar />
        <LocationDisplay />
      </AppShellProvider>
    )
    return renderWithRouter({
      ui: Wrapped,
      path: initialPath,
      initialPath,
      extraRoutes:
        initialPath === "/dashboard"
          ? [{ path: "/news", Component: () => <div>News route</div> }]
          : [{ path: "/dashboard", Component: () => <div>Dashboard route</div> }],
    })
  }

  beforeEach(() => {
    setupMatchMedia({ mobile: true, reducedMotion: false })
    document.body.className = ""
    document.body.style.overflow = ""
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.className = ""
    document.body.style.overflow = ""
  })

  // Wave 115 SW2 closed SW1-remainder: the original assertions expected
  // `-translate-x-full` / `pointer-events-none` classes on the drawer /
  // backdrop AFTER closing. That matched a pre-Wave-?? drawer that
  // permanently rendered both and toggled transform via class. The current
  // `MobileMenu` uses declarative framer-motion `exit={{ x: "100%" }}` and
  // wraps the backdrop+drawer pair inside `<AnimatePresence>{isOpen && (...)}`
  // — the elements unmount on close. The rewritten assertions read the
  // post-close DOM (drawer/backdrop unmounted, burger refocused, body
  // overflow cleared) which matches the real close behaviour the user
  // experiences. Focus-trap semantics are verified while the drawer is still
  // open, before the close transition.
  it("traps focus within the mobile drawer and closes on Escape", async () => {
    const user = userEvent.setup()
    await renderNavbar()

    const burger = await screen.findByRole("button", { name: "Open menu" })
    await user.click(burger)

    await screen.findByTestId("mobile-menu-backdrop")
    const drawer = screen.getByRole("dialog")
    await waitFor(() => expect(drawer).toContainElement(document.activeElement as HTMLElement))
    expect(burger).toHaveAttribute("aria-expanded", "true")
    expect(document.body.style.overflow).toBe("hidden")

    // Focus trap — tabbing forward stays inside the drawer.
    await user.tab()
    expect(drawer).toContainElement(document.activeElement as HTMLElement)

    await user.tab({ shift: true })
    expect(drawer).toContainElement(document.activeElement as HTMLElement)

    await user.keyboard("{Escape}")

    // Drawer + backdrop unmount (AnimatePresence pass-through mock snaps to
    // removed state when `isOpen` flips false).
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.queryByTestId("mobile-menu-backdrop")).not.toBeInTheDocument()
    await waitFor(() => expect(burger).toHaveAttribute("aria-expanded", "false"))
    await waitFor(() => expect(burger).toHaveFocus())
    expect(document.body.classList.contains("blurred")).toBe(false)
    expect(document.body.style.overflow).toBe("")
  })

  it("closes the drawer when navigating to another route", async () => {
    const user = userEvent.setup()
    await renderNavbar()

    const burger = await screen.findByRole("button", { name: "Open menu" })
    await user.click(burger)

    expect(document.body.style.overflow).toBe("hidden")

    const newsLink = await screen.findByRole("link", { name: "News" })
    await user.click(newsLink)

    await waitFor(() => expect(burger).toHaveAttribute("aria-expanded", "false"))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.queryByTestId("mobile-menu-backdrop")).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe("")
    // LocationDisplay only renders under the /dashboard route component —
    // after navigation the router swaps to the /news extraRoute which only
    // emits "News route". Asserting on that string confirms the click
    // actually performed a route transition (not just a no-op close).
    await waitFor(() => expect(screen.getByText("News route")).toBeInTheDocument())
  })

  it("uses the scrolled mobile style and scrolls home to the top", async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, "scrollY", { configurable: true, value: 200 })
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderNavbar()
    await waitFor(() => expect(screen.getByRole("navigation")).toHaveClass("bg-(--pill-bg)"))

    await user.click(screen.getByRole("link", { name: "Home" }))
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })

  it("uses the transparent compact desktop style after scrolling", async () => {
    setupMatchMedia({ mobile: false, reducedMotion: true })
    Object.defineProperty(window, "scrollY", { configurable: true, value: 200 })
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderNavbar()
    const nav = await screen.findByRole("navigation")
    await waitFor(() => expect(nav).toHaveClass("bg-transparent"))
    expect(nav).toHaveStyle({ boxShadow: "none" })
    await userEvent.click(screen.getByRole("link", { name: "Home" }))
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" })
  })

  it("lets the logo navigate from another route without forcing a scroll", async () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    })

    await renderNavbar("/news")
    await userEvent.click(screen.getByRole("link", { name: "Home" }))

    expect(scrollTo).not.toHaveBeenCalled()
    expect(await screen.findByText("Dashboard route")).toBeInTheDocument()
  })
})
