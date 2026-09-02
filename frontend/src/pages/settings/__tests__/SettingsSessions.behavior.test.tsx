import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  useSessionManagement: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/pages/settings/hooks", () => ({
  useSessionManagement: (options: unknown) => {
    mocks.useSessionManagement(options)
    return mocks.state
  },
}))

vi.mock("@/pages/settings/sections", () => ({
  SessionsSection: ({
    sessionsErrorMessage,
    onRevokeSession,
    onRevokeAllSessions,
  }: {
    sessionsErrorMessage: string | null
    onRevokeSession: (id: string) => void
    onRevokeAllSessions: () => void
  }) => (
    <section data-testid="sessions-section">
      <div data-testid="sessions-error">{sessionsErrorMessage}</div>
      <button type="button" onClick={() => onRevokeSession("session-1")}>
        revoke-session
      </button>
      <button type="button" onClick={onRevokeAllSessions}>
        revoke-all
      </button>
    </section>
  ),
}))

import { SettingsSessions } from "@/pages/settings/SettingsSessions"

const makeState = () => ({
  sessions: [],
  sortedSessions: [],
  sessionsFetching: false,
  sessionsIsError: false,
  sessionsError: null,
  handleRevokeSession: vi.fn(),
  handleRevokeAllSessions: vi.fn(),
  revokeSessionBusy: false,
  revokeAllSessionsBusy: false,
  formatSessionTimestamp: vi.fn(() => "formatted-date"),
})

beforeEach(() => {
  mocks.state = makeState()
  mocks.useSessionManagement.mockReset()
})

describe("SettingsSessions", () => {
  it("forwards active state and session actions", () => {
    const openStepUpFor = vi.fn()
    render(<SettingsSessions setSnackbar={vi.fn()} openStepUpFor={openStepUpFor} isActive />)

    expect(screen.getByTestId("sessions-section")).toBeInTheDocument()
    expect(mocks.useSessionManagement).toHaveBeenCalledWith(
      expect.objectContaining({ tabActive: true, openStepUpFor })
    )
    fireEvent.click(screen.getByRole("button", { name: "revoke-session" }))
    fireEvent.click(screen.getByRole("button", { name: "revoke-all" }))
    expect(mocks.state.handleRevokeSession).toHaveBeenCalledWith("session-1")
    expect(mocks.state.handleRevokeAllSessions).toHaveBeenCalledOnce()
  })

  it.each([
    [{ response: { data: { detail: ["expired", "reauthenticate"] } } }, "expired,reauthenticate"],
    [new Error("Sessions offline"), "Sessions offline"],
    [{}, "settings:sessions.error"],
  ])("normalizes a session error", (sessionsError, expected) => {
    mocks.state = { ...makeState(), sessionsIsError: true, sessionsError }
    render(<SettingsSessions setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent(expected)
  })
})
