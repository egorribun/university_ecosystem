import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  useSessionManagement: vi.fn(),
  auth: { user: { id: "user-1" } as { id: string | number } | null, loading: false },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }))

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
    identityPending,
  }: {
    sessionsErrorMessage: string | null
    onRevokeSession: (id: string) => void
    onRevokeAllSessions: () => void
    identityPending: boolean
  }) => (
    <section data-testid="sessions-section">
      <div data-testid="sessions-error">{sessionsErrorMessage}</div>
      <button type="button" onClick={() => onRevokeSession("session-1")} disabled={identityPending}>
        revoke-session
      </button>
      <button type="button" onClick={onRevokeAllSessions} disabled={identityPending}>
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
  mocks.auth = { user: { id: "user-1" }, loading: false }
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
  ])("normalizes a session error [case %#]", (sessionsError, expected) => {
    mocks.state = { ...makeState(), sessionsIsError: true, sessionsError }
    render(<SettingsSessions setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent(expected)
  })

  it.each([
    ["SSR stub", "ssr-stub", false],
    ["numeric cache placeholder", -1, false],
    ["still-loading account", "user-1", true],
  ])("disables session revocation for %s until identity is confirmed", (_, id, loading) => {
    mocks.auth = { user: { id }, loading }
    const renderView = () => (
      <SettingsSessions setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />
    )
    const { rerender } = render(renderView())
    const revoke = screen.getByRole("button", { name: "revoke-session" })
    const revokeAll = screen.getByRole("button", { name: "revoke-all" })
    expect(revoke).toBeDisabled()
    expect(revokeAll).toBeDisabled()
    fireEvent.click(revoke)
    fireEvent.click(revokeAll)
    expect(mocks.state.handleRevokeSession).not.toHaveBeenCalled()
    expect(mocks.state.handleRevokeAllSessions).not.toHaveBeenCalled()

    mocks.auth = { user: { id: "user-1" }, loading: false }
    rerender(renderView())
    expect(revoke).toBeEnabled()
    expect(revokeAll).toBeEnabled()
    fireEvent.click(revoke)
    fireEvent.click(revokeAll)
    expect(mocks.state.handleRevokeSession).toHaveBeenCalledWith("session-1")
    expect(mocks.state.handleRevokeAllSessions).toHaveBeenCalledOnce()
  })
})
