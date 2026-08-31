/**
 * Render coverage tests (testing session 10) for the small, prop-driven navbar
 * pieces that prior sessions left untested: DesktopNav, NavbarLogo,
 * MobileDrawerProfile, MobileDrawerQuickActions, and UserMenu (loading /
 * unauthenticated / authenticated states). Mirrors the renderWithRouter +
 * stub-props pattern from NavbarOverflowMenu.test.tsx (session 9 template).
 */
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { Home, Calendar } from "lucide-react"
import type { TFunction } from "i18next"

// UserMenu's authed branch renders MessengerButton + NotificationsBell, which
// require MessengerProvider / notification context renderWithRouter doesn't
// supply. Stub them — the focus here is UserMenu's own auth-state markup.
vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <div data-testid="messenger-button" />,
}))
vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <div data-testid="notifications-bell" />,
}))

import { DesktopNav } from "@/components/navbar/DesktopNav"
import { NavbarLogo } from "@/components/navbar/NavbarLogo"
import { MobileDrawerProfile } from "@/components/navbar/MobileDrawerProfile"
import { MobileDrawerQuickActions } from "@/components/navbar/MobileDrawerQuickActions"
import { UserMenu } from "@/components/navbar/UserMenu"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { testUser } from "@/tests/mocks/handlers"
import type { NavigationItem } from "@/config/navigation"

const t = ((key: string) => key) as unknown as TFunction

const navItems: NavigationItem[] = [
  { to: "/", label: "Home", icon: Home },
  { to: "/news", label: "News", icon: Home },
  { to: "/events", label: "Events", icon: Calendar },
]

describe("DesktopNav", () => {
  it("renders a list item + premium link per nav entry", async () => {
    const scrollToTop = vi.fn()
    await renderWithRouter({
      ui: () => (
        <DesktopNav
          menuLinks={navItems}
          isActive={(to) => to === "/news"}
          isSameTarget={() => false}
          scrollToTop={scrollToTop}
          markScrollFromBottom={vi.fn()}
          prefersReducedMotion
          isCompact={false}
        />
      ),
      authProvider: false,
    })
    expect(screen.getByText("News")).toBeInTheDocument()
    expect(screen.getByText("Events")).toBeInTheDocument()
    expect(document.querySelector(".navbar-desktop-nav")).toBeInTheDocument()
    // active entry carries data-active.
    const newsLink = document.getElementById("navbar-link-news")
    expect(newsLink).toHaveAttribute("data-active")
    expect(document.getElementById("navbar-link-home")).toBeInTheDocument()
    await userEvent.click(screen.getByText("Home"))
    expect(scrollToTop).not.toHaveBeenCalled()
  })

  it("scrolls to top instead of navigating when the link targets the current page", async () => {
    const scrollToTop = vi.fn()
    await renderWithRouter({
      ui: () => (
        <DesktopNav
          menuLinks={navItems}
          isActive={() => false}
          isSameTarget={(to) => to === "/news"}
          scrollToTop={scrollToTop}
          markScrollFromBottom={vi.fn()}
          prefersReducedMotion
          isCompact
        />
      ),
      authProvider: false,
    })
    await userEvent.click(screen.getByText("News"))
    expect(scrollToTop).toHaveBeenCalledWith("auto")
  })

  it("uses smooth scrolling for a same-target link when motion is allowed", async () => {
    const scrollToTop = vi.fn()
    await renderWithRouter({
      ui: () => (
        <DesktopNav
          menuLinks={navItems}
          isActive={() => false}
          isSameTarget={(to) => to === "/events"}
          scrollToTop={scrollToTop}
          markScrollFromBottom={vi.fn()}
          prefersReducedMotion={false}
          isCompact={false}
        />
      ),
      authProvider: false,
    })

    await userEvent.click(screen.getByText("Events"))
    expect(scrollToTop).toHaveBeenCalledWith("smooth")
  })
})

describe("NavbarLogo", () => {
  it("renders the brand link to /dashboard with alt + brand name", async () => {
    const onLogoClick = vi.fn()
    await renderWithRouter({
      ui: () => (
        <NavbarLogo
          t={t}
          isMobile={false}
          isCompact={false}
          isPhone={false}
          prefersReducedMotion
          onLogoClick={onLogoClick}
          markScrollFromBottom={vi.fn()}
        />
      ),
      authProvider: false,
    })
    const link = document.getElementById("navbar-logo-link")
    expect(link).toHaveAttribute("href", "/dashboard")
    expect(screen.getByText("navigation:brandName")).toBeInTheDocument()
    expect(document.querySelector(".navbar-brand-name")).toBeInTheDocument()
    const logoSurface = screen.getByRole("img").parentElement
    expect(logoSurface).not.toHaveClass("hover:scale-105", "active:scale-95")
  })

  it("renders the tablet-mobile spacing variant", async () => {
    await renderWithRouter({
      ui: () => (
        <NavbarLogo
          t={t}
          isMobile
          isCompact={false}
          isPhone={false}
          prefersReducedMotion={false}
          onLogoClick={vi.fn()}
          markScrollFromBottom={vi.fn()}
        />
      ),
      authProvider: false,
    })

    expect(document.getElementById("navbar-logo-link")).toHaveClass("gap-fluid-gap")
  })
})

describe("MobileDrawerProfile", () => {
  it("renders name + role chip and fires onProfileClick", async () => {
    const onProfileClick = vi.fn()
    await renderWithRouter({
      ui: () => <MobileDrawerProfile user={testUser} onProfileClick={onProfileClick} t={t} />,
      authProvider: false,
    })
    expect(screen.getByText(testUser.full_name as string)).toBeInTheDocument()
    expect(screen.getByText("navigation:role.student")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button"))
    expect(onProfileClick).toHaveBeenCalledOnce()
  })

  it("shows the admin role label for admin users", async () => {
    await renderWithRouter({
      ui: () => (
        <MobileDrawerProfile user={{ ...testUser, role: "admin" }} onProfileClick={vi.fn()} t={t} />
      ),
      authProvider: false,
    })
    expect(screen.getByText("navigation:role.admin")).toBeInTheDocument()
  })

  it("shows the teacher role label for teaching staff", async () => {
    await renderWithRouter({
      ui: () => (
        <MobileDrawerProfile
          user={{ ...testUser, role: "teacher" }}
          onProfileClick={vi.fn()}
          t={t}
        />
      ),
      authProvider: false,
    })
    expect(screen.getByText("navigation:role.teacher")).toBeInTheDocument()
  })

  it("uses an avatar URL and the translated alt fallback when the name is empty", async () => {
    await renderWithRouter({
      ui: () => (
        <MobileDrawerProfile
          user={{
            ...testUser,
            full_name: "",
            role: undefined,
            avatar_url: "https://example.test/avatar.png",
            avatar_updated_at: "2026-08-04T12:00:00Z",
          }}
          onProfileClick={vi.fn()}
          t={t}
        />
      ),
      authProvider: false,
    })
    expect(screen.getByAltText("navigation:aria.profileAvatar")).toBeInTheDocument()
  })
})

describe("MobileDrawerQuickActions", () => {
  it("renders the 3 quick-action buttons and wires their handlers", async () => {
    const onSearch = vi.fn()
    const onNotifications = vi.fn()
    const onSettings = vi.fn()
    await renderWithRouter({
      ui: () => (
        <MobileDrawerQuickActions
          onSearch={onSearch}
          onNotifications={onNotifications}
          onSettings={onSettings}
          prefersReducedMotion
          t={(key) => key}
        />
      ),
      authProvider: false,
    })
    await userEvent.click(screen.getByRole("button", { name: "navigation:menu.search" }))
    await userEvent.click(screen.getByRole("button", { name: "navigation:menu.notifications" }))
    await userEvent.click(screen.getByRole("button", { name: "navigation:menu.settings" }))
    expect(onSearch).toHaveBeenCalledOnce()
    expect(onNotifications).toHaveBeenCalledOnce()
    expect(onSettings).toHaveBeenCalledOnce()
  })
})

describe("UserMenu", () => {
  it("renders the loading skeleton when loading", async () => {
    await renderWithRouter({
      ui: () => <UserMenu user={null} isAuth={false} loading go={vi.fn()} t={(key) => key} />,
    })
    expect(screen.getByLabelText("common:aria.loadingUserMenu")).toBeInTheDocument()
  })

  it("renders the authenticated profile affordance + routes to /profile", async () => {
    const go = vi.fn()
    await renderWithRouter({
      ui: () => <UserMenu user={testUser} isAuth loading={false} go={go} t={(key) => key} />,
    })
    const avatarButton = screen.getByRole("button", { name: "navigation:aria.openProfile" })
    const profileNameButton = screen.getByRole("button", {
      name: `navigation:aria.openProfile: ${testUser.full_name}`,
    })
    expect(document.querySelector(".navbar-user-name")).toBeInTheDocument()
    expect(avatarButton).toHaveClass("size-11")
    await userEvent.click(avatarButton)
    expect(go).toHaveBeenCalledWith("/profile")
    await userEvent.click(profileNameButton)
    expect(go).toHaveBeenLastCalledWith("/profile")
    await userEvent.click(screen.getByAltText("navigation:aria.profileAvatarNamed"))
    expect(go).toHaveBeenLastCalledWith("/profile")
    await userEvent.click(screen.getByRole("button", { name: "navigation:menu.settings" }))
    expect(go).toHaveBeenLastCalledWith("/settings")
  })

  it("renders nothing for a settled unauthenticated state", async () => {
    const { container } = await renderWithRouter({
      ui: () => (
        <UserMenu user={null} isAuth={false} loading={false} go={vi.fn()} t={(key) => key} />
      ),
    })
    expect(container).toBeEmptyDOMElement()
  })

  it("passes avatar URL cache metadata through the authenticated profile", async () => {
    await renderWithRouter({
      ui: () => (
        <UserMenu
          user={{
            ...testUser,
            avatar_url: "https://example.test/avatar.png",
            avatar_updated_at: "2026-08-04T12:00:00Z",
          }}
          isAuth
          loading={false}
          go={vi.fn()}
          t={(key) => key}
        />
      ),
    })
    expect(screen.getByAltText("navigation:aria.profileAvatarNamed")).toBeInTheDocument()
  })

  it("renders the compact reduced-motion variant", async () => {
    await renderWithRouter({
      ui: () => (
        <UserMenu
          user={testUser}
          isAuth
          loading={false}
          go={vi.fn()}
          t={(key) => key}
          isCompact
          prefersReducedMotion
        />
      ),
    })

    expect(screen.getByAltText("navigation:aria.profileAvatarNamed")).toHaveClass("h-7", "w-7")
    expect(screen.getByRole("button", { name: "navigation:menu.settings" })).toHaveClass(
      "size-11",
      "duration-0"
    )
  })
})
