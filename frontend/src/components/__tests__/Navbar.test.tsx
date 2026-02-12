import { MemoryRouter, useLocation } from "react-router-dom"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import Navbar from "../Navbar"
import { AppShellProvider } from "@/contexts/AppShellContext"

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

vi.mock("@/components/NotificationsBell", () => ({
  default: () => <div data-testid="notifications-bell" />,
}))

vi.mock("@/components/SmartImage", () => ({
  default: ({ alt, onClick }: { alt: string; onClick?: () => void }) => (
    <img src="avatar" alt={alt} role="img" data-testid="smart-image" onClick={onClick} />
  ),
}))

vi.mock("@/components/MessengerButton", () => ({
  default: () => <button data-testid="messenger-button">Messenger</button>,
}))

vi.mock("framer-motion", () => {
  const motionComponent = (Tag: string) => {
    const Component = ({ children, className, onClick, ...props }: any) => {
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
      return (
        <Tag className={className} onClick={onClick} {...filteredProps}>
          {children}
        </Tag>
      )
    }
    Component.displayName = `Motion(${Tag})`
    return Component
  }
  return {
    AnimatePresence: ({ children }: any) => <>{children}</>,
    motion: {
      nav: motionComponent("nav"),
      div: motionComponent("div"),
      button: motionComponent("button"),
      li: motionComponent("li"),
      ul: motionComponent("ul"),
      span: motionComponent("span"),
      line: motionComponent("line"),
    },
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

  const renderNavbar = () =>
    render(
      <AppShellProvider>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <Navbar />
          <LocationDisplay />
        </MemoryRouter>
      </AppShellProvider>
    )

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

  it("traps focus within the mobile drawer and closes on Escape", async () => {
    const user = userEvent.setup()
    renderNavbar()

    const burger = await screen.findByRole("button", { name: "Open menu" })
    await user.click(burger)

    await screen.findByRole("button", { name: "Close menu" })
    // Focus should move to the drawer content
    const drawer = screen.getByRole("dialog")
    await waitFor(() => expect(drawer).toContainElement(document.activeElement as HTMLElement))
    expect(document.body.classList.contains("blurred")).toBe(true)
    expect(document.body.style.overflow).toBe("hidden")

    await user.tab()
    expect(drawer).toContainElement(document.activeElement as HTMLElement)

    await user.tab({ shift: true })
    expect(drawer).toContainElement(document.activeElement as HTMLElement)

    await user.keyboard("{Escape}")

    await waitFor(() => expect(burger).toHaveAttribute("aria-expanded", "false"))
    await waitFor(() => expect(burger).toHaveFocus())
    expect(document.body.classList.contains("blurred")).toBe(false)
    expect(document.body.style.overflow).toBe("")
    expect(drawer).toHaveStyle({ pointerEvents: "none" })
    const drawerNav = drawer.querySelector("nav")
    expect(drawerNav).not.toBeNull()
    expect(drawerNav).toHaveClass("-translate-x-full")
  })

  it("closes the drawer when navigating to another route", async () => {
    const user = userEvent.setup()
    renderNavbar()

    const burger = await screen.findByRole("button", { name: "Open menu" })
    await user.click(burger)
    const newsLink = await screen.findByRole("link", { name: "News" })

    expect(document.body.style.overflow).toBe("hidden")

    await user.click(newsLink)

    await waitFor(() => expect(burger).toHaveAttribute("aria-expanded", "false"))
    const drawer = screen.getByRole("dialog")
    expect(drawer).toHaveStyle({ pointerEvents: "none" })
    expect(drawer.querySelector("nav")).toHaveClass("-translate-x-full")
    expect(document.body.style.overflow).toBe("")
    expect(screen.getByTestId("location-display")).toHaveTextContent("/news")
  })
})
