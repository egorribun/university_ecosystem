import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

const { useTranslationMock, translateMock } = vi.hoisted(() => {
  const translateMock = vi.fn((key: string) => key)
  return {
    translateMock,
    useTranslationMock: vi.fn(() => ({
      t: translateMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
  }
})

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
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
  beforeEach(() => {
    useTranslationMock.mockClear()
    translateMock.mockClear()
    window.sessionStorage.clear()
  })

  it("renders participant count and a register button for an eligible student", () => {
    render(<EventActions {...baseProps} />)
    expect(screen.getByText("events:card.participants")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:card.actions.register" })).toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
    expect(translateMock).toHaveBeenCalledWith("events:card.participants", { count: 42 })
    expect(translateMock).toHaveBeenCalledWith("events:form.participants")
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
    expect(translateMock).toHaveBeenCalledWith("events:card.actions.openQr")
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

  it("restores a persisted QR dialog and clears its marker on close", async () => {
    const user = userEvent.setup()
    window.sessionStorage.setItem("event:qr_open:evt-1", "1")

    render(<EventActions {...baseProps} isRegistered qrToken="qr-token-123" />)

    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "events:card.actions.closeQr" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(window.sessionStorage.getItem("event:qr_open:evt-1")).toBeNull()

    const qrButton = screen.getAllByRole("button")[1]
    expect(qrButton).toBeDefined()
    await user.click(qrButton!)
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "events:card.actions.closeQr" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it.each([
    ["inactive", { isActive: false }],
    ["ended", { isEnded: true }],
  ] as const)("does not expose registration controls for %s events", (_label, overrides) => {
    render(<EventActions {...baseProps} {...overrides} />)
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.unregister" })
    ).not.toBeInTheDocument()
  })

  it.each(["admin", "teacher"] as const)("does not let %s register", (userRole) => {
    render(<EventActions {...baseProps} userRole={userRole} />)
    expect(
      screen.queryByRole("button", { name: "events:card.actions.register" })
    ).not.toBeInTheDocument()
  })

  it("only exposes unregister and QR controls for an active registered event", () => {
    const onUnregister = vi.fn()
    const { rerender } = render(
      <EventActions
        {...baseProps}
        isRegistered
        qrToken="qr-token-123"
        onUnregister={onUnregister}
      />
    )
    expect(
      screen.getByRole("button", { name: "events:card.actions.unregister" })
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:card.actions.openQr" })).toBeInTheDocument()

    rerender(
      <EventActions
        {...baseProps}
        isRegistered
        qrToken="qr-token-123"
        isActive={false}
        onUnregister={onUnregister}
      />
    )
    expect(
      screen.queryByRole("button", { name: "events:card.actions.unregister" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "events:card.actions.openQr" })
    ).not.toBeInTheDocument()
  })

  it("re-evaluates persisted QR state when the token arrives after mount", async () => {
    const { rerender } = render(<EventActions {...baseProps} isRegistered qrToken={undefined} />)
    window.sessionStorage.setItem("event:qr_open:evt-late", "1")
    rerender(<EventActions {...baseProps} eventId="evt-late" isRegistered qrToken="late-token" />)

    expect(await screen.findByRole("dialog")).toBeInTheDocument()
  })

  it("ignores sessionStorage failures in QR persistence effects", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    const removeItem = vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })

    try {
      render(<EventActions {...baseProps} />)
      expect(
        screen.getByRole("button", { name: "events:card.actions.register" })
      ).toBeInTheDocument()
    } finally {
      getItem.mockRestore()
      removeItem.mockRestore()
    }
  })
})
