import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user-1" } as { id: string } | null },
  email: {} as Record<string, unknown>,
  password: {} as Record<string, unknown>,
  sessions: {} as Record<string, unknown>,
  totp: {} as Record<string, unknown>,
  webauthn: {} as Record<string, unknown>,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mocks.auth,
}))

vi.mock("@/pages/settings/hooks", () => ({
  useEmailChange: () => mocks.email,
  usePasswordChange: () => mocks.password,
  useSessionManagement: () => mocks.sessions,
  useTotpEnrollment: () => mocks.totp,
  useWebAuthn: () => mocks.webauthn,
}))

vi.mock("@/pages/settings/sections", () => ({
  EmailSection: ({ onSubmit }: { onSubmit: () => void }) => (
    <section data-testid="email-section">
      <button type="button" onClick={onSubmit}>
        email-submit
      </button>
    </section>
  ),
  PasswordSection: ({ onSubmit }: { onSubmit: () => void }) => (
    <section data-testid="password-section">
      <button type="button" onClick={onSubmit}>
        password-submit
      </button>
    </section>
  ),
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

vi.mock("@/components/settings", () => ({
  Alert: ({ children, severity }: { children: React.ReactNode; severity: string }) => (
    <div role={severity === "error" ? "alert" : "status"}>{children}</div>
  ),
  AccordionSection: ({
    title,
    subtitle,
    children,
  }: {
    title: React.ReactNode
    subtitle: React.ReactNode
    children: React.ReactNode
  }) => (
    <section>
      <h3>{title}</h3>
      <p>{subtitle}</p>
      {children}
    </section>
  ),
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode
    onClick?: () => void
    disabled?: boolean
  }) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  SectionCard: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  SectionTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  SectionSubtitle: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

vi.mock("@/components/mfa/TotpQrDisplay", () => ({
  TotpQrDisplay: ({ secret }: { secret: string }) => <div data-testid="totp-qr">{secret}</div>,
}))

vi.mock("@/components/mfa/OtpEntry", () => ({
  OtpEntry: ({
    onSubmit,
    error,
    loading,
  }: {
    onSubmit: (value: string) => void
    error?: string | null
    loading?: boolean
  }) => (
    <div>
      <button type="button" disabled={loading} onClick={() => onSubmit("123456")}>
        otp-submit
      </button>
      {error ? <span>{error}</span> : null}
    </div>
  ),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt ?? ""} />,
}))

import { SettingsSecurity } from "@/pages/settings/SettingsSecurity"

const makeEmailState = () => ({
  emailValue: "",
  emailPassword: "",
  emailBusy: false,
  emailError: null,
  emailPasswordError: null,
  pendingEmail: null,
  setEmailValue: vi.fn(),
  setEmailPassword: vi.fn(),
  handleEmailSubmit: vi.fn(),
})

const makePasswordState = () => ({
  currentPasswordValue: "",
  newPasswordValue: "",
  confirmPasswordValue: "",
  passwordBusy: false,
  passwordError: null,
  currentPasswordError: null,
  isNewPasswordError: false,
  confirmPasswordMessage: null,
  setCurrentPasswordValue: vi.fn(),
  setNewPasswordValue: vi.fn(),
  setConfirmPasswordValue: vi.fn(),
  handlePasswordSubmit: vi.fn(),
})

const makeSessionsState = () => ({
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

const makeTotpState = () => ({
  totpDraft: null,
  totpBusy: false,
  totpError: null,
  activeTotp: [],
  handleStartTotp: vi.fn(),
  handleConfirmTotp: vi.fn(),
  handleCancelTotp: vi.fn(),
  handleDisableTotp: vi.fn(),
  formatDateTime: vi.fn(() => "formatted-date"),
})

const makeWebAuthnState = () => ({
  credentials: [],
  busy: false,
  supported: false,
  handleRegister: vi.fn(),
  handleDelete: vi.fn(),
})

const renderSecurity = (isActive = true) =>
  render(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={isActive} />)

beforeEach(() => {
  mocks.auth = { user: { id: "user-1" } }
  mocks.email = makeEmailState()
  mocks.password = makePasswordState()
  mocks.sessions = makeSessionsState()
  mocks.totp = makeTotpState()
  mocks.webauthn = makeWebAuthnState()
})

describe("SettingsSecurity", () => {
  it("renders delegated sections and forwards email/password/session actions", () => {
    renderSecurity()

    expect(screen.getByTestId("email-section")).toBeInTheDocument()
    expect(screen.getByTestId("password-section")).toBeInTheDocument()
    expect(screen.getByTestId("sessions-section")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("settings:security.webauthn.notSupported")

    fireEvent.click(screen.getByRole("button", { name: "email-submit" }))
    fireEvent.click(screen.getByRole("button", { name: "password-submit" }))
    fireEvent.click(screen.getByRole("button", { name: "revoke-session" }))
    fireEvent.click(screen.getByRole("button", { name: "revoke-all" }))

    expect(mocks.email.handleEmailSubmit).toHaveBeenCalledTimes(1)
    expect(mocks.password.handlePasswordSubmit).toHaveBeenCalledTimes(1)
    expect(mocks.sessions.handleRevokeSession).toHaveBeenCalledWith("session-1")
    expect(mocks.sessions.handleRevokeAllSessions).toHaveBeenCalledTimes(1)
  })

  it("covers TOTP add, draft confirmation/cancel, active removal, and limit states", () => {
    const { rerender } = renderSecurity()
    fireEvent.click(screen.getByRole("button", { name: "settings:security.totp.add" }))
    expect(mocks.totp.handleStartTotp).toHaveBeenCalledTimes(1)

    mocks.totp = {
      ...makeTotpState(),
      totpDraft: { secret: "SECRET", otpauth_url: "otpauth://totp/test" }, // pragma: allowlist secret
      totpError: "Invalid code",
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByTestId("totp-qr")).toHaveTextContent("SECRET")
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid code")
    fireEvent.click(screen.getByRole("button", { name: "otp-submit" }))
    fireEvent.click(screen.getByRole("button", { name: "settings:security.totp.cancel" }))
    expect(mocks.totp.handleConfirmTotp).toHaveBeenCalledWith("123456")
    expect(mocks.totp.handleCancelTotp).toHaveBeenCalledTimes(1)

    const activeTotp = { id: "totp-1", label: "", created_at: "2026-01-01T00:00:00Z" }
    mocks.totp = { ...makeTotpState(), activeTotp: [activeTotp] }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByText("settings:security.totp.unnamed")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "settings:security.totp.remove" }))
    expect(mocks.totp.handleDisableTotp).toHaveBeenCalledWith("totp-1")

    mocks.totp = {
      ...makeTotpState(),
      activeTotp: [activeTotp],
      totpError: "Too many attempts",
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByText("settings:security.totp.limitReached")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Too many attempts")
  })

  it("covers supported WebAuthn credentials, registration, deletion, and busy controls", () => {
    const { rerender } = renderSecurity()
    mocks.webauthn = {
      ...makeWebAuthnState(),
      supported: true,
      credentials: [{ id: "credential-1", label: "", created_at: "2026-01-01T00:00:00Z" }],
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByText("settings:security.webauthn.defaultLabel")).toBeInTheDocument()
    const iconButton = screen.getAllByRole("button").find((button) => button.querySelector("svg"))
    expect(iconButton).toBeDefined()
    fireEvent.click(iconButton!)
    fireEvent.click(screen.getByRole("button", { name: "settings:security.webauthn.add" }))
    expect(mocks.webauthn.handleDelete).toHaveBeenCalledWith("credential-1")
    expect(mocks.webauthn.handleRegister).toHaveBeenCalledTimes(1)

    mocks.webauthn = {
      ...mocks.webauthn,
      busy: true,
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByRole("button", { name: "settings:security.webauthn.add" })).toBeDisabled()
  })

  it("normalizes session error details, Error messages, and translation fallback", () => {
    const { rerender } = renderSecurity(false)
    mocks.sessions = {
      ...makeSessionsState(),
      sessionsIsError: true,
      sessionsError: { response: { data: { detail: ["expired", "reauthenticate"] } } },
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent("expired,reauthenticate")

    mocks.sessions = {
      ...makeSessionsState(),
      sessionsIsError: true,
      sessionsError: new Error("Sessions offline"),
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent("Sessions offline")

    mocks.sessions = {
      ...makeSessionsState(),
      sessionsIsError: true,
      sessionsError: {},
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent("settings:sessions.error")

    mocks.auth = { user: null }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={false} />)
    expect(screen.getByTestId("sessions-error")).toHaveTextContent("settings:sessions.error")
  })
})
