import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  auth: {
    user: { id: "user-1" } as { id: string | number; email?: string } | null,
    loading: false,
  },
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
  EmailSection: ({
    onSubmit,
    identityPending,
  }: {
    onSubmit: () => void
    identityPending: boolean
  }) => (
    <section data-testid="email-section">
      <button type="button" onClick={onSubmit} disabled={identityPending}>
        email-submit
      </button>
    </section>
  ),
  PasswordSection: ({
    onSubmit,
    identityPending,
  }: {
    onSubmit: () => void
    identityPending: boolean
  }) => (
    <section data-testid="password-section">
      <button type="button" onClick={onSubmit} disabled={identityPending}>
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
      <button
        type="button"
        disabled={loading}
        data-loading={Boolean(loading)}
        onClick={() => onSubmit("123456")}
      >
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
  mocks.auth = { user: { id: "user-1" }, loading: false }
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
      emailMfaError: "Email delivery failed",
      emailChallenge: {
        method: "email_otp",
        challenge_token: "challenge-token",
        challenge_expires_at: "2026-08-25T16:00:00Z",
        delivery_hint: "u***@example.com",
      },
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByRole("alert")).toHaveTextContent("Email delivery failed")
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

  it("covers email delivery fallbacks and the unverified-account action", () => {
    mocks.auth = { user: { id: "user-1", email: "user@example.com" }, loading: false }
    mocks.emailMfa = {
      ...makeEmailMfaState(),
      emailChallenge: {
        method: "email_otp",
        challenge_token: "challenge-token",
        challenge_expires_at: "2026-08-25T16:00:00Z",
      },
    }
    const { rerender } = renderSecurity()
    expect(screen.getByText("settings:security.emailMfa.sentTo")).toBeInTheDocument()

    mocks.auth = { user: null, loading: false }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByText("settings:security.emailMfa.sentTo")).toBeInTheDocument()

    mocks.auth = { user: { id: "user-1" }, loading: false }
    mocks.emailMfa = { ...makeEmailMfaState(), emailVerified: false }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    fireEvent.click(screen.getByRole("button", { name: "settings:security.emailMfa.verifyEmail" }))
    expect(mocks.emailMfa.handleStartEmailMfa).toHaveBeenCalledOnce()
  })

  it.each([
    ["SSR stub", "ssr-stub", false],
    ["numeric cache placeholder", -1, false],
    ["still-loading account", "user-1", true],
  ])("blocks security actions for %s until identity is confirmed", (_, id, loading) => {
    mocks.auth = { user: { id }, loading }
    const { rerender } = renderSecurity()
    const buttons = () => [
      screen.getByRole("button", { name: "email-submit" }),
      screen.getByRole("button", { name: "password-submit" }),
      screen.getByRole("button", { name: "settings:security.totp.add" }),
      screen.getByRole("button", { name: "settings:security.emailMfa.enable" }),
    ]
    buttons().forEach((button) => {
      expect(button).toBeDisabled()
      fireEvent.click(button)
    })
    expect(mocks.email.handleEmailSubmit).not.toHaveBeenCalled()
    expect(mocks.password.handlePasswordSubmit).not.toHaveBeenCalled()
    expect(mocks.totp.handleStartTotp).not.toHaveBeenCalled()
    expect(mocks.emailMfa.handleStartEmailMfa).not.toHaveBeenCalled()

    mocks.auth = { user: { id: "user-1" }, loading: false }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    buttons().forEach((button) => {
      expect(button).toBeEnabled()
      fireEvent.click(button)
    })
    expect(mocks.email.handleEmailSubmit).toHaveBeenCalledOnce()
    expect(mocks.password.handlePasswordSubmit).toHaveBeenCalledOnce()
    expect(mocks.totp.handleStartTotp).toHaveBeenCalledOnce()
    expect(mocks.emailMfa.handleStartEmailMfa).toHaveBeenCalledOnce()

    mocks.auth.loading = true
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    buttons().forEach((button) => expect(button).toBeDisabled())
  })

  it("gates enrollment removal and disabling email MFA when identity is pending", () => {
    mocks.auth.loading = true
    mocks.totp = {
      ...makeTotpState(),
      activeTotp: [{ id: "totp-1", label: "Phone", created_at: "2026-01-01T00:00:00Z" }],
    }
    mocks.emailMfa = { ...makeEmailMfaState(), emailMfaEnabled: true }
    const { rerender } = renderSecurity()
    const remove = screen.getByRole("button", { name: "settings:security.totp.remove" })
    const disable = screen.getByRole("button", { name: "settings:security.emailMfa.disable" })
    expect(remove).toBeDisabled()
    expect(disable).toBeDisabled()
    fireEvent.click(remove)
    fireEvent.click(disable)
    expect(mocks.totp.handleDisableTotp).not.toHaveBeenCalled()
    expect(mocks.emailMfa.handleDisableEmailMfa).not.toHaveBeenCalled()

    mocks.auth.loading = false
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(remove).toBeEnabled()
    expect(disable).toBeEnabled()
    fireEvent.click(remove)
    fireEvent.click(disable)
    expect(mocks.totp.handleDisableTotp).toHaveBeenCalledWith("totp-1")
    expect(mocks.emailMfa.handleDisableEmailMfa).toHaveBeenCalledOnce()
  })

  it("gates confirmation, cancellation, and resend during a pending identity", () => {
    mocks.auth.loading = true
    mocks.totp = {
      ...makeTotpState(),
      totpDraft: { secret: crypto.randomUUID(), otpauth_url: "otpauth://totp/test" },
    }
    mocks.emailMfa = {
      ...makeEmailMfaState(),
      emailChallenge: { method: "email_otp", challenge_token: "challenge-token" },
    }
    const { rerender } = renderSecurity()
    const buttons = () => [
      ...screen.getAllByRole("button", { name: "otp-submit" }),
      screen.getByRole("button", { name: "settings:security.totp.cancel" }),
      screen.getByRole("button", { name: "settings:security.emailMfa.resend" }),
      screen.getByRole("button", { name: "common:buttons.cancel" }),
    ]
    buttons().forEach((button) => {
      expect(button).toBeDisabled()
      fireEvent.click(button)
    })
    screen.getAllByRole("button", { name: "otp-submit" }).forEach((button) => {
      expect(button).toHaveAttribute("data-loading", "false")
    })
    expect(mocks.totp.handleConfirmTotp).not.toHaveBeenCalled()
    expect(mocks.totp.handleCancelTotp).not.toHaveBeenCalled()
    expect(mocks.emailMfa.handleConfirmEmailMfa).not.toHaveBeenCalled()
    expect(mocks.emailMfa.handleResendEmailMfa).not.toHaveBeenCalled()
    expect(mocks.emailMfa.handleCancelEmailMfa).not.toHaveBeenCalled()

    mocks.auth.loading = false
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    buttons().forEach((button) => {
      expect(button).toBeEnabled()
      fireEvent.click(button)
    })
    expect(mocks.totp.handleConfirmTotp).toHaveBeenCalledWith("123456")
    expect(mocks.totp.handleCancelTotp).toHaveBeenCalledOnce()
    expect(mocks.emailMfa.handleConfirmEmailMfa).toHaveBeenCalledWith("123456")
    expect(mocks.emailMfa.handleResendEmailMfa).toHaveBeenCalledOnce()
    expect(mocks.emailMfa.handleCancelEmailMfa).toHaveBeenCalledOnce()
  })

  it("keeps MFA controls disabled while their own requests are busy", () => {
    mocks.totp = { ...makeTotpState(), totpBusy: true }
    mocks.emailMfa = { ...makeEmailMfaState(), emailMfaBusy: true }
    const { rerender } = renderSecurity()
    expect(screen.getByRole("button", { name: "settings:security.totp.add" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "settings:security.emailMfa.enable" })).toBeDisabled()

    mocks.totp = {
      ...makeTotpState(),
      totpBusy: true,
      activeTotp: [{ id: "totp-1", label: "Phone", created_at: "2026-01-01T00:00:00Z" }],
    }
    mocks.emailMfa = { ...makeEmailMfaState(), emailMfaBusy: true, emailMfaEnabled: true }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    expect(screen.getByRole("button", { name: "settings:security.totp.remove" })).toBeDisabled()
    expect(
      screen.getByRole("button", { name: "settings:security.emailMfa.disable" })
    ).toBeDisabled()

    mocks.totp = {
      ...makeTotpState(),
      totpBusy: true,
      totpDraft: { secret: crypto.randomUUID(), otpauth_url: "otpauth://totp/test" },
    }
    mocks.emailMfa = {
      ...makeEmailMfaState(),
      emailMfaBusy: true,
      emailChallenge: { method: "email_otp", challenge_token: "challenge-token" },
    }
    rerender(<SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} isActive />)
    screen.getAllByRole("button", { name: "otp-submit" }).forEach((button) => {
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute("data-loading", "true")
    })
    expect(screen.getByRole("button", { name: "settings:security.totp.cancel" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "settings:security.emailMfa.resend" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "common:buttons.cancel" })).toBeDisabled()
  })
})
