import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { testUser } from "@/tests/mocks/handlers"
import { UserMenu } from "../UserMenu"

vi.mock("@/components/layout/MessengerButton", () => ({ default: () => <button>Messages</button> }))
vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: () => <button>Alerts</button>,
}))
vi.mock("@/components/media/SmartImage", () => ({ default: () => <span /> }))

// jsdom does not lay out container queries. These checks cover the responsive
// wiring and accessible fallback; hosted browser screenshots must verify pixels.
describe("UserMenu available-width fallback", () => {
  it.each([
    "Al",
    "Тест Студентов",
    "Alexandra Catherine Montgomery-Wellington",
    "Александра Екатерина Константинопольская",
    "A".repeat(120),
  ])("keeps the complete identity and profile action for %s", async (full_name) => {
    const go = vi.fn()
    const { container, rerender } = render(
      <UserMenu user={{ ...testUser, full_name }} isAuth loading={false} go={go} t={(key) => key} />
    )
    const avatar = screen.getByRole("button", { name: "navigation:aria.openProfile" })
    expect(container.firstElementChild).toHaveClass("@container/profile-actions")
    expect(avatar).toHaveAccessibleDescription(full_name)
    expect(avatar).toHaveClass("size-11", "shrink-0")
    const name = screen.getByRole("button", { name: `navigation:aria.openProfile: ${full_name}` })
    expect(name.parentElement).toHaveClass("hidden", "@min-[18rem]/profile-actions:block")
    expect(name).toHaveTextContent(full_name)
    await userEvent.click(avatar)
    expect(go).toHaveBeenCalledExactlyOnceWith("/profile")
    expect(screen.getByRole("button", { name: "navigation:menu.settings" })).toBeEnabled()
    rerender(
      <UserMenu
        user={{ ...testUser, full_name }}
        isAuth
        loading={false}
        go={go}
        t={(key) => key}
        isCompact
      />
    )
    expect(container.firstElementChild).not.toHaveClass("@container/profile-actions")
    expect(name).toBeDisabled()
    expect(name).toHaveAttribute("aria-hidden", "true")
    expect(avatar).toBeEnabled()
    expect(avatar).toHaveAccessibleDescription(full_name)
  })
  it("keeps the generic profile action when the name is empty", () => {
    render(
      <UserMenu
        user={{ ...testUser, full_name: "" }}
        isAuth
        loading={false}
        go={vi.fn()}
        t={(key) => key}
      />
    )
    const avatar = screen.getAllByRole("button", { name: "navigation:aria.openProfile" })[0]
    expect(avatar).not.toHaveAttribute("aria-describedby")
    expect(avatar).toBeEnabled()
  })
})
