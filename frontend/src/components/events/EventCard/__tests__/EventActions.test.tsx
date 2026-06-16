import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventActions } from "@/components/events/EventCard/EventActions"

const baseProps = {
  eventId: "evt-1",
  isActive: true,
  isEnded: false,
  isRegistered: false,
  participantCount: 42,
  loading: false,
  onRegister: vi.fn(),
  onUnregister: vi.fn(),
}

describe("EventActions", () => {
  it("renders participant count and a register button for an eligible student", () => {
    render(<EventActions {...baseProps} />)
    expect(screen.getByText("events:card.participants")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:card.actions.register" })).toBeInTheDocument()
  })

  it("shows the ended badge and no register button for an ended event", () => {
    render(<EventActions {...baseProps} isEnded />)
    expect(screen.getByText("events:card.statuses.ended")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
  })

  it("renders unregister + QR controls when registered with a token", async () => {
    const user = userEvent.setup()
    const onUnregister = vi.fn()
    render(
      <EventActions
        {...baseProps}
        isRegistered
        qrToken="qr-token-123"
        onUnregister={onUnregister}
      />
    )
    expect(screen.getAllByRole("button")).toHaveLength(2)
    await user.click(screen.getByRole("button", { name: "events:card.actions.unregister" }))
    expect(onUnregister).toHaveBeenCalledOnce()
  })

  it("fires onRegister when the register button is clicked", async () => {
    const user = userEvent.setup()
    const onRegister = vi.fn()
    render(<EventActions {...baseProps} onRegister={onRegister} />)
    await user.click(screen.getByRole("button", { name: "events:card.actions.register" }))
    expect(onRegister).toHaveBeenCalledOnce()
  })
})
