import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user-1" } as { id: string } | null },
  email: {} as Record<string, unknown>,
  password: {} as Record<string, unknown>,
  totp: {} as Record<string, unknown>,
  emailMfa: {} as Record<string, unknown>,
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
  useTotpEnrollment: () => mocks.totp,
  useEmailMfa: () => mocks.emailMfa,
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

const makeEmailMfaState = () => ({
  emailChallenge: null,
  emailMfaBusy: false,
  emailMfaError: null,
  emailMfaEnabled: false,
  emailVerified: true,
  handleStartEmailMfa: vi.fn(),
  handleConfirmEmailMfa: vi.fn(),
  handleResendEmailMfa: vi.fn(),
  handleCancelEmailMfa: vi.fn(),
  handleDisableEmailMfa: vi.fn(),
})

const renderSecurity = (isActive = true) =>
  render(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive={isActive} />)

beforeEach(() => {
  mocks.auth = { user: { id: "user-1" } }
  mocks.email = makeEmailState()
  mocks.password = makePasswordState()
  mocks.totp = makeTotpState()
  mocks.emailMfa = makeEmailMfaState()
})

describe("SettingsSecurity", () => {
  it("renders delegated sections and forwards email/password actions", () => {
    renderSecurity()

    expect(screen.getByTestId("email-section")).toBeInTheDocument()
    expect(screen.getByTestId("password-section")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "settings:security.emailMfa.enable" })
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "email-submit" }))
    fireEvent.click(screen.getByRole("button", { name: "password-submit" }))

    expect(mocks.email.handleEmailSubmit).toHaveBeenCalledTimes(1)
    expect(mocks.password.handlePasswordSubmit).toHaveBeenCalledTimes(1)
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

  it("covers email MFA enable, challenge, resend, confirm, cancel, and disable states", () => {
    const { rerender } = renderSecurity()
    fireEvent.click(screen.getByRole("button", { name: "settings:security.emailMfa.enable" }))
    expect(mocks.emailMfa.handleStartEmailMfa).toHaveBeenCalledTimes(1)

    mocks.emailMfa = {
      ...makeEmailMfaState(),
      emailChallenge: {
        method: "email_otp",
        challenge_token: "challenge-token",
        challenge_expires_at: "2026-08-25T16:00:00Z",
        delivery_hint: "u***@example.com",
      },
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByText("settings:security.emailMfa.sentTo")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "otp-submit" }))
    fireEvent.click(screen.getByRole("button", { name: "settings:security.emailMfa.resend" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(mocks.emailMfa.handleConfirmEmailMfa).toHaveBeenCalledWith("123456")
    expect(mocks.emailMfa.handleResendEmailMfa).toHaveBeenCalledTimes(1)
    expect(mocks.emailMfa.handleCancelEmailMfa).toHaveBeenCalledTimes(1)

    mocks.emailMfa = {
      ...makeEmailMfaState(),
      emailMfaEnabled: true,
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    fireEvent.click(screen.getByRole("button", { name: "settings:security.emailMfa.disable" }))
    expect(mocks.emailMfa.handleDisableEmailMfa).toHaveBeenCalledTimes(1)
  })
})
