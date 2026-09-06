import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import type { User } from "@/types/User"
import { testUser } from "@/tests/mocks/handlers"

vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <span data-testid="messenger-button" />,
}))

vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <span data-testid="notifications-bell" />,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    alt,
    cacheV,
    className,
    srcRaw,
  }: {
    alt: string
    cacheV?: number
    className?: string
    srcRaw: string
  }) => (
    <img
      alt={alt}
      className={className}
      data-cache-v={cacheV === undefined ? "undefined" : String(cacheV)}
      data-testid="smart-image"
      src={srcRaw}
    />
  ),
}))

vi.mock("@/components/ui", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div className={className} data-testid="skeleton" />
  ),
}))

vi.mock("lucide-react", () => ({
  Settings: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="settings-icon" />
  ),
}))

import { UserMenu } from "@/components/navbar/UserMenu"

const t = (key: string) => key
const user = { ...testUser, full_name: "Ada Lovelace", avatar_url: null } as User

type RenderOverrides = Partial<{
  go: (to: string) => void
  isAuth: boolean
  isCompact: boolean
  loading: boolean
  prefersReducedMotion: boolean
  t: (key: string) => string
  user: User | null
}>

const renderMenu = (overrides: RenderOverrides = {}) => {
  const go = overrides.go ?? vi.fn()
  const view = render(
    <UserMenu
      go={go}
      isAuth={overrides.isAuth ?? true}
      loading={overrides.loading ?? false}
      prefersReducedMotion={overrides.prefersReducedMotion}
      t={overrides.t ?? t}
      user={overrides.user === undefined ? user : overrides.user}
      isCompact={overrides.isCompact}
    />
  )
  return { ...view, go }
}

describe("UserMenu mutation contracts", () => {
  it("renders one or two loading skeletons according to compact mode", () => {
    const { rerender } = render(<UserMenu user={null} isAuth={false} loading go={vi.fn()} t={t} />)

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true")
    expect(screen.getByLabelText("common:aria.loadingUserMenu")).toBeInTheDocument()
    expect(screen.getAllByTestId("skeleton")).toHaveLength(2)

    rerender(<UserMenu user={null} isAuth={false} loading isCompact go={vi.fn()} t={t} />)
    expect(screen.getAllByTestId("skeleton")).toHaveLength(1)
  })

  it.each([
    ["signed out", false, user],
    ["missing user", true, null],
  ])("does not render private actions when %s", (_label, isAuth, currentUser) => {
    const { container } = renderMenu({ isAuth, user: currentUser })

    expect(container).toBeEmptyDOMElement()
  })

  it("uses the first available avatar timestamp and falls through deterministically", () => {
    const { rerender } = renderMenu({
      user: {
        ...user,
        avatar_url: "https://example.test/avatar.png",
        avatar_updated_at: "123",
        avatar_version: 456,
        updated_at: "789",
      },
    })

    expect(screen.getByTestId("smart-image")).toHaveAttribute("data-cache-v", "123")

    rerender(
      <UserMenu
        go={vi.fn()}
        isAuth
        loading={false}
        t={t}
        user={{ ...user, avatar_url: "https://example.test/avatar.png", avatar_version: 456 }}
      />
    )
    expect(screen.getByTestId("smart-image")).toHaveAttribute("data-cache-v", "456")

    rerender(
      <UserMenu
        go={vi.fn()}
        isAuth
        loading={false}
        t={t}
        user={{ ...user, avatar_url: "https://example.test/avatar.png", updated_at: "789" }}
      />
    )
    expect(screen.getByTestId("smart-image")).toHaveAttribute("data-cache-v", "789")
  })

  it("selects the supplied avatar source or the canonical placeholder", () => {
    const { rerender } = renderMenu({
      user: { ...user, avatar_url: "https://example.test/avatar.png" },
    })

    expect(screen.getByTestId("smart-image")).toHaveAttribute(
      "src",
      "https://example.test/avatar.png"
    )

    rerender(
      <UserMenu go={vi.fn()} isAuth loading={false} t={t} user={{ ...user, avatar_url: "" }} />
    )
    expect(screen.getByTestId("smart-image")).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
    expect(screen.getByTestId("smart-image")).toHaveAttribute("data-cache-v", "undefined")
  })

  it("keeps profile labels localized for named and unnamed accounts", () => {
    const { rerender } = renderMenu()

    expect(screen.getByRole("button", { name: "navigation:aria.openProfile" })).toHaveAttribute(
      "title",
      "navigation:aria.openProfile"
    )
    expect(
      screen.getByRole("button", { name: "navigation:aria.openProfile: Ada Lovelace" })
    ).toBeInTheDocument()
    expect(screen.getByAltText("navigation:aria.profileAvatarNamed")).toBeInTheDocument()

    rerender(
      <UserMenu go={vi.fn()} isAuth loading={false} t={t} user={{ ...user, full_name: "" }} />
    )
    expect(screen.getByAltText("navigation:aria.profileAvatar")).toBeInTheDocument()
    for (const profileControl of screen.getAllByRole("button", {
      name: "navigation:aria.openProfile",
    })) {
      expect(profileControl).toHaveAttribute("title", "navigation:aria.openProfile")
    }
  })

  it("routes both profile controls and settings through the supplied navigator", async () => {
    const go = vi.fn()
    const userActions = userEvent.setup()
    renderMenu({ go })

    await userActions.click(screen.getByRole("button", { name: "navigation:aria.openProfile" }))
    await userActions.click(
      screen.getByRole("button", { name: "navigation:aria.openProfile: Ada Lovelace" })
    )
    await userActions.click(screen.getByRole("button", { name: "navigation:menu.settings" }))

    expect(go).toHaveBeenNthCalledWith(1, "/profile")
    expect(go).toHaveBeenNthCalledWith(2, "/profile")
    expect(go).toHaveBeenNthCalledWith(3, "/settings")
  })

  it("uses the full-size motion-friendly visual contract by default", () => {
    const { container } = renderMenu()
    const root = container.firstElementChild
    const inner = container.querySelector(".navbar-user-name")?.parentElement
    const avatarButton = screen.getByRole("button", { name: "navigation:aria.openProfile" })
    const avatar = screen.getByTestId("smart-image")
    const settingsButton = screen.getByRole("button", { name: "navigation:menu.settings" })

    expect(root).toHaveClass("gap-3", "duration-500", "ease-[var(--ease-premium)]")
    expect(inner).toHaveClass("gap-3", "ml-3", "h-10")
    expect(avatarButton).toHaveClass(
      "size-11",
      "duration-500",
      "hover:scale-105",
      "active:scale-95"
    )
    expect(avatar).toHaveClass("h-9", "w-9", "object-cover", "pointer-events-none")
    expect(container.querySelector(".navbar-user-name")).toHaveClass("max-w-48", "opacity-100")
    expect(
      screen.getByRole("button", { name: "navigation:aria.openProfile: Ada Lovelace" })
    ).toHaveClass("min-h-11", "font-bold", "text-base", "hover:text-brand")
    expect(settingsButton).toHaveClass(
      "size-11",
      "duration-500",
      "transition-[transform,opacity,background-color]",
      "hover:bg-(--bg-surface-hover)/(--opacity-soft)",
      "hover:scale-105",
      "active:scale-95"
    )
    expect(screen.getByTestId("settings-icon")).toHaveClass("h-5", "w-5")
  })

  it("uses compact reduced-motion geometry and removes hover transforms", () => {
    const { container } = renderMenu({ isCompact: true, prefersReducedMotion: true })
    const root = container.firstElementChild
    const inner = container.querySelector(".navbar-user-name")?.parentElement
    const avatarButton = screen.getByRole("button", { name: "navigation:aria.openProfile" })
    const settingsButton = screen.getByRole("button", { name: "navigation:menu.settings" })

    expect(root).toHaveClass("gap-2", "duration-0")
    expect(inner).toHaveClass("gap-2", "ml-1", "h-8", "duration-0")
    expect(container.querySelector(".navbar-user-name")).toHaveClass("max-w-0", "opacity-0")
    expect(screen.getByTestId("smart-image")).toHaveClass("h-7", "w-7")
    expect(avatarButton).toHaveClass("size-11", "duration-0")
    expect(avatarButton).not.toHaveClass("hover:scale-105", "active:scale-95")
    expect(settingsButton).toHaveClass("size-11", "duration-0")
    expect(settingsButton).not.toHaveClass("hover:scale-105", "active:scale-95")
    expect(screen.getByTestId("settings-icon")).toHaveClass("h-4", "w-4")
  })
})
