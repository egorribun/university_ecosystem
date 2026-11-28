import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

import { ProfileModal } from "@/components/messenger/ProfileModal"
import { Dialog } from "@/components/ui/Dialog"
import type { User } from "@/types/User"

/**
 * Wave 183 SW10 — ProfileModal unit tests.
 *
 * Covers W183 SW4 a11y batch regression guards + ProfileModal contract:
 *  - Renders nothing when all 3 inputs (user, loading, error) are falsy.
 *  - Renders dialog with role=dialog + aria-modal + aria-labelledby.
 *  - Close button has aria-label + min 44x44 touch (W183 SW4 WCAG 2.5.8).
 *  - Escape key triggers onClose.
 *  - Backdrop click triggers onClose.
 *  - Loading state renders spinner.
 *  - Error state renders error message.
 *  - User state renders name + email + status badge.
 *
 * Mocking strategy:
 *  - Use the real focus trap to exercise Escape ownership and restoration.
 *  - react-i18next passes keys through verbatim.
 *  - SmartImage mocked as <img>.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

const mockUseMediaQuery = vi.hoisted(() => vi.fn(() => false))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mockUseMediaQuery }))

const testUser: User = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  avatar_url: "/avatar.png",
  is_active: true,
  role: "student",
} as User

afterEach(async () => {
  mockUseMediaQuery.mockReturnValue(false)
  cleanup()
  await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
})

describe("ProfileModal", () => {
  it("renders nothing when all inputs are falsy", () => {
    const { container } = render(
      <ProfileModal user={null} loading={false} error={null} onClose={() => {}} />
    )
    // AnimatePresence renders nothing when its child returns false-ish.
    expect(container.firstChild).toBeNull()
  })

  it("renders dialog with proper ARIA when user is provided", () => {
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={() => {}} />)

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeTruthy()
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy()

    // Heading id matches aria-labelledby
    const headingId = dialog.getAttribute("aria-labelledby")!
    const heading = document.getElementById(headingId)
    expect(heading?.textContent).toBe(testUser.full_name)
  })

  it("close button has proper aria-label + 44x44 touch target (W183 SW4)", () => {
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={() => {}} />)

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(closeButton).toBeTruthy()
    expect(closeButton.className).toContain("min-h-[44px]")
    expect(closeButton.className).toContain("min-w-[44px]")
  })

  it("calls onClose once for Escape", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("leaves Escape to the top dialog when a second modal is open", () => {
    const onCloseProfile = vi.fn()
    const onCloseTop = vi.fn()
    const content = (topOpen: boolean) => (
      <>
        <ProfileModal user={testUser} loading={false} error={null} onClose={onCloseProfile} />
        <Dialog open={topOpen} onClose={onCloseTop} title="Another modal">
          Other content
        </Dialog>
      </>
    )
    const view = render(content(false))
    view.rerender(content(true))

    fireEvent.keyDown(screen.getByRole("dialog", { name: "Another modal" }), { key: "Escape" })
    expect(onCloseTop).toHaveBeenCalledOnce()
    expect(onCloseProfile).not.toHaveBeenCalled()
  })

  it("does not handle Escape after the profile is closed", () => {
    const onClose = vi.fn()
    const view = render(
      <ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />
    )
    view.rerender(<ProfileModal user={null} loading={false} error={null} onClose={onClose} />)

    expect(fireEvent.keyDown(document, { key: "Escape" })).toBe(true)
    expect(onClose).not.toHaveBeenCalled()
  })

  it("ignores non-Escape keys and closes from the close button", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />)

    fireEvent.keyDown(document, { key: "Enter" })
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("backdrop click triggers onClose", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />)

    // role="presentation" backdrop
    const backdrop = document.querySelector('[role="presentation"]')
    expect(backdrop).toBeTruthy()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("dialog click does NOT propagate to backdrop (stopPropagation)", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />)

    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()
  })

  it("loading state renders spinner", () => {
    const { container } = render(
      <ProfileModal user={null} loading={true} error={null} onClose={() => {}} />
    )

    const spinner = container.querySelector(".animate-spin")
    expect(spinner).toBeTruthy()
    expect(screen.getByText("messenger:loadingProfile")).toBeTruthy()
  })

  it("error state renders error message", () => {
    render(
      <ProfileModal user={null} loading={false} error="Failed to load profile" onClose={() => {}} />
    )
    expect(screen.getByText(/Failed to load profile/)).toBeTruthy()
  })

  it("user state renders email + status badge with data-status=online", () => {
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={() => {}} />)

    expect(screen.getByText(testUser.email)).toBeTruthy()
    const statusBadge = document.querySelector('[data-status="online"]')
    expect(statusBadge).toBeTruthy()
  })

  it("omits the email line when the public profile carries no email", () => {
    const publicUser = {
      id: testUser.id,
      full_name: testUser.full_name,
      avatar_url: testUser.avatar_url,
      is_active: testUser.is_active,
    }
    const { container } = render(
      <ProfileModal user={publicUser} loading={false} error={null} onClose={() => {}} />
    )

    expect(container.querySelector("h4.sf-pro")?.textContent).toBe(testUser.full_name)
    expect(screen.queryByText(testUser.email)).toBeNull()
    // No empty email paragraph follows the name heading.
    expect(container.querySelector("h4.sf-pro + p")).toBeNull()
  })

  it("omits the email line when the email is empty", () => {
    const { container } = render(
      <ProfileModal
        user={{ ...testUser, email: "" }}
        loading={false}
        error={null}
        onClose={() => {}}
      />
    )

    expect(container.querySelector("h4.sf-pro + p")).toBeNull()
  })

  it("user state renders status badge with data-status=offline when inactive", () => {
    const inactiveUser = { ...testUser, is_active: false }
    render(<ProfileModal user={inactiveUser} loading={false} error={null} onClose={() => {}} />)

    const statusBadge = document.querySelector('[data-status="offline"]')
    expect(statusBadge).toBeTruthy()
  })

  it("uses safe title/avatar fallbacks and reduced-motion animation branches", () => {
    mockUseMediaQuery.mockReturnValue(true)
    const user = { ...testUser, full_name: "", avatar_url: undefined, is_active: false }
    render(<ProfileModal user={user} loading={true} error="problem" onClose={vi.fn()} />)

    expect(screen.getByRole("heading", { name: "messenger:profile" })).toBeInTheDocument()
    expect(screen.getByAltText("")).toHaveAttribute("src", "/fallbacks/default_avatar.png")
    expect(screen.queryByText("messenger:viewAvatar")).not.toBeInTheDocument()
    expect(screen.getByText("messenger:loadingProfile")).toBeInTheDocument()
    expect(screen.getByText("problem")).toBeInTheDocument()
  })

  it("uses an empty image alt for a null profile name", () => {
    render(
      <ProfileModal
        user={{ ...testUser, full_name: null }}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByAltText("")).toBeInTheDocument()
  })

  it("exposes the avatar link only when an avatar exists and preserves status semantics", () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />
    )

    const avatarLink = screen.getByRole("link", { name: /messenger:viewAvatar/ })
    expect(avatarLink).toHaveAttribute("href", "/avatar.png")
    expect(avatarLink).toHaveAttribute("target", "_blank")
    expect(avatarLink).toHaveAttribute("rel", "noreferrer")
    expect(document.querySelector('[data-status="online"]')).toBeInTheDocument()
    expect(document.querySelector(".messenger-online-indicator")).toBeInTheDocument()

    const inactive = { ...testUser, avatar_url: null, is_active: false }
    rerender(<ProfileModal user={inactive} loading={false} error={null} onClose={onClose} />)
    expect(screen.queryByRole("link", { name: /messenger:viewAvatar/ })).toBeNull()
    expect(document.querySelector('[data-status="offline"]')).toBeInTheDocument()
    expect(document.querySelector(".messenger-online-indicator")).toBeNull()
  })

  it("consumes the Escape key it handles", () => {
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={vi.fn()} />)
    expect(fireEvent.keyDown(document, { key: "Escape" })).toBe(false)
  })

  it("renders no empty error region while loading without an error", () => {
    render(<ProfileModal user={null} loading error={null} onClose={vi.fn()} />)
    const paragraphs = screen.getAllByRole("paragraph")

    expect(paragraphs.map((paragraph) => paragraph.textContent?.trim())).toEqual([
      "messenger:loadingProfile",
    ])
  })

  it("labels the status and avatar tiles and colours the presence dot by state", () => {
    const { rerender } = render(
      <ProfileModal user={testUser} loading={false} error={null} onClose={vi.fn()} />
    )
    const online = document.querySelector('[data-status="online"]')!

    expect(screen.getByText("messenger:status")).toBeInTheDocument()
    expect(screen.getByText("messenger:avatar")).toBeInTheDocument()
    expect(online).toHaveTextContent("common:active")
    expect((online.querySelector('[aria-hidden="true"]') as HTMLElement).style.background).toBe(
      "var(--messenger-status-online-text)"
    )

    rerender(
      <ProfileModal
        user={{ ...testUser, is_active: false }}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />
    )
    const offline = document.querySelector('[data-status="offline"]')!
    expect(offline).toHaveTextContent("common:inactive")
    expect((offline.querySelector('[aria-hidden="true"]') as HTMLElement).style.background).toBe(
      "var(--messenger-status-offline-text)"
    )
  })
})
