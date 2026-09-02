import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import MessengerButton from "../MessengerButton"

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), unreadCount: 0, t: (key: string) => key }))

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => mocks.navigate }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock("@/contexts/MessengerContextCore", () => ({
  useMessenger: () => ({ unreadCount: mocks.unreadCount }),
}))

describe("MessengerButton", () => {
  beforeEach(() => {
    mocks.navigate.mockReset()
    mocks.unreadCount = 0
  })

  it("navigates to the messenger without rendering a badge when all chats are read", () => {
    render(<MessengerButton />)

    const button = screen.getByRole("button", { name: "navigation:aria.messenger" })
    expect(button).not.toHaveAttribute("data-unread")
    fireEvent.click(button)
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/messenger" })
  })

  it("exposes the unread state and count to users", () => {
    mocks.unreadCount = 3
    render(<MessengerButton />)

    expect(screen.getByRole("button")).toHaveAttribute("data-unread", "")
    expect(screen.getByText("3")).toBeInTheDocument()
  })
})
