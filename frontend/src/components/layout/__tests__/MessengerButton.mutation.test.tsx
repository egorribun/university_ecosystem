import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  t: vi.fn((key: string) => key),
  useTranslation: vi.fn(),
  unreadCount: 0,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
}))

vi.mock("react-i18next", () => ({
  useTranslation: mocks.useTranslation,
}))

vi.mock("@/contexts/MessengerContextCore", () => ({
  useMessenger: () => ({ unreadCount: mocks.unreadCount }),
}))

vi.mock("framer-motion", () => ({
  m: {
    span: ({
      children,
      initial,
      animate,
      ...props
    }: {
      children?: ReactNode
      initial?: Record<string, unknown>
      animate?: Record<string, unknown>
      className?: string
    }) => (
      <span
        {...props}
        data-testid="messenger-unread-motion"
        data-motion-animate={JSON.stringify(animate)}
        data-motion-initial={JSON.stringify(initial)}
      >
        {children}
      </span>
    ),
  },
}))

import MessengerButton from "@/components/layout/MessengerButton"

describe("MessengerButton mutation contracts", () => {
  beforeEach(() => {
    mocks.navigate.mockReset()
    mocks.t.mockReset().mockImplementation((key: string) => key)
    mocks.useTranslation.mockReset().mockReturnValue({ t: mocks.t })
    mocks.unreadCount = 0
  })

  it("requests the navigation namespace and preserves the translated accessible name", () => {
    render(<MessengerButton />)

    expect(mocks.useTranslation).toHaveBeenCalledWith(["navigation"])
    expect(mocks.t).toHaveBeenCalledWith("navigation:aria.messenger")
    expect(screen.getByRole("button", { name: "navigation:aria.messenger" })).toHaveClass(
      "relative",
      "nav-action-btn",
      "group",
      "focus-ring-premium",
      "text-text-primary",
      "hover:text-brand"
    )
  })

  it("navigates to the messenger route and omits the unread badge at zero", () => {
    render(<MessengerButton />)

    const button = screen.getByRole("button", { name: "navigation:aria.messenger" })
    button.click()

    expect(mocks.navigate).toHaveBeenCalledOnce()
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/messenger" })
    expect(button).not.toHaveAttribute("data-unread")
    expect(screen.queryByText("0")).not.toBeInTheDocument()
  })

  it("renders the unread count with stable motion enter props", () => {
    mocks.unreadCount = 3
    render(<MessengerButton />)

    expect(screen.getByRole("button")).toHaveAttribute("data-unread", "")
    expect(screen.getByText("3")).toBeInTheDocument()
    const motionWrapper = screen.getByTestId("messenger-unread-motion")
    expect(motionWrapper).toHaveAttribute("data-motion-initial", '{"scale":0}')
    expect(motionWrapper).toHaveAttribute("data-motion-animate", '{"scale":1}')
  })
})
