import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

import { ProfileModal } from "@/components/messenger/ProfileModal"
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
 *  - useFocusTrap mocked to no-op (focus-trap behaviour is integration-
 *    tested via the real DOM in actual usage; here we just want to verify
 *    the modal renders and the onClose/onDeactivate wiring is correct).
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

vi.mock("@/hooks/useFocusTrap", () => ({
  default: () => ({ current: null }),
}))

const testUser: User = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  avatar_url: "/avatar.png",
  is_active: true,
  role: "student",
} as User

afterEach(() => {
  mockUseMediaQuery.mockReturnValue(false)
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

  it("Escape key triggers onClose", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={testUser} loading={false} error={null} onClose={onClose} />)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
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
})
