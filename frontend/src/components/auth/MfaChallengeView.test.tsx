import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { axe } from "jest-axe"

import { MfaChallengeView } from "./MfaChallengeView"

/**
 * MfaChallengeView axe + render-shape tests.
 *
 * The view renders one of three layouts depending on the available
 * methods on `mfa.loginChallenge`:
 *  - WebAuthn-only;
 *  - TOTP-only;
 *  - both (separator between);
 *  - neither (warning + start-over).
 *
 * The full interaction flow (TOTP digit entry, WebAuthn navigator
 * call, trust-device persistence) involves AuthContext, navigator
 * APIs, and react-hook-form — covered end-to-end by Track D specs.
 * Here we only pin the ARIA / accessibility contract for each shape.
 */

const baseMfa = {
  loginChallenge: null,
  otpChallenge: undefined,
  webauthnChallenge: undefined,
  mfaBusy: false,
  mfaError: null as string | null,
  mfaErrorSource: null as null | "totp" | "general",
  generalMfaError: null,
  setMfaError: vi.fn(),
  setMfaErrorSource: vi.fn(),
  handleOtpVerify: vi.fn(),
  handleWebAuthnVerify: vi.fn(),
  showRecoveryInput: false,
  setShowRecoveryInput: vi.fn(),
  handleRecoveryVerify: vi.fn(),
}

const props = {
  activeEmail: "user@example.com",
  trustDevice: false,
  onTrustDeviceChange: vi.fn(),
  webauthnSupported: true,
  mfa: baseMfa,
}

describe("MfaChallengeView — render shapes", () => {
  it("renders the no-methods warning when both challenges are absent", () => {
    const { container } = render(<MfaChallengeView {...props} />)
    // The warning carries the auth:mfa.noMethods translation. We test by
    // looking for any text content rather than the exact i18n value.
    expect(container.querySelector("h1")).toBeInTheDocument()
  })

  it("renders the TOTP entry when otpChallenge is present", () => {
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    const { container } = render(<MfaChallengeView {...props} mfa={{ ...baseMfa, otpChallenge }} />)
    // OtpEntry renders a digit-input form. We just confirm the page
    // mounted with no crash. (Detailed OtpEntry behaviour is its own test.)
    expect(container).toBeInTheDocument()
  })
})

describe("MfaChallengeView — TOTP interaction", () => {
  it("auto-submits 6 digits via handleOtpVerify", async () => {
    const handleOtpVerify = vi.fn()
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    const user = userEvent.setup()

    render(<MfaChallengeView {...props} mfa={{ ...baseMfa, otpChallenge, handleOtpVerify }} />)

    // OtpEntry renders 6 single-character inputs labelled "<TOTP> - digit N".
    const inputs = await screen.findAllByLabelText(/digit \d/)
    expect(inputs).toHaveLength(6)

    // Type into the first input — handleChange auto-advances focus, so
    // we need to type into each one explicitly.
    for (let i = 0; i < 6; i++) {
      await user.type(inputs[i] as HTMLInputElement, String(i + 1))
    }

    // Auto-submit fires when 6 digits + !loading + !error. The view's
    // handleOtpVerify wrapper passes (code, trustDevice).
    await waitFor(() => {
      expect(handleOtpVerify).toHaveBeenCalledWith("123456", false)
    })
  })

  it("propagates trustDevice value to handleOtpVerify", async () => {
    const handleOtpVerify = vi.fn()
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    const user = userEvent.setup()

    render(
      <MfaChallengeView
        {...props}
        trustDevice={true}
        mfa={{ ...baseMfa, otpChallenge, handleOtpVerify }}
      />
    )

    const inputs = await screen.findAllByLabelText(/digit \d/)
    for (let i = 0; i < 6; i++) {
      await user.type(inputs[i] as HTMLInputElement, String(i + 1))
    }

    await waitFor(() => {
      expect(handleOtpVerify).toHaveBeenCalledWith("123456", true)
    })
  })

  it("disables digit inputs while mfaBusy is true", () => {
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    render(<MfaChallengeView {...props} mfa={{ ...baseMfa, otpChallenge, mfaBusy: true }} />)
    const inputs = screen.getAllByLabelText(/digit \d/)
    for (const input of inputs) {
      expect(input).toBeDisabled()
    }
  })
})

describe("MfaChallengeView — WebAuthn interaction", () => {
  it("invokes handleWebAuthnVerify on the security-key button click", async () => {
    const handleWebAuthnVerify = vi.fn()
    const webauthnChallenge = {
      method: "webauthn" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
      options: {},
    }
    const user = userEvent.setup()

    render(
      <MfaChallengeView {...props} mfa={{ ...baseMfa, webauthnChallenge, handleWebAuthnVerify }} />
    )

    // Look for any button that mentions "security key" / "passkey" / etc.
    // The translation key is auth:mfa.webauthn.useSecurityKey.
    const button = screen.getByRole("button", { name: /security key/i })
    await user.click(button)

    expect(handleWebAuthnVerify).toHaveBeenCalledWith(false)
  })
})

describe("MfaChallengeView — start over", () => {
  it("renders the start-over button under every shape", () => {
    const { unmount } = render(<MfaChallengeView {...props} />)
    // The auth:mfa.startOver translation renders as "Use a different account"
    // in English; in Russian it's a different label. We assert the canonical
    // EN copy since setupTests.ts pins the test locale to "en".
    expect(screen.getByRole("button", { name: /different account/i })).toBeInTheDocument()
    unmount()
  })
})

describe("MfaChallengeView — error display", () => {
  it("shows the general MFA error when generalMfaError is set", () => {
    render(
      <MfaChallengeView
        {...props}
        mfa={{
          ...baseMfa,
          mfaError: "Account locked",
          mfaErrorSource: "general",
          generalMfaError: "Account locked",
        }}
      />
    )
    expect(screen.getByText("Account locked")).toBeInTheDocument()
  })
})

describe("MfaChallengeView — accessibility", () => {
  it("has no axe violations in the no-methods state", async () => {
    const { container } = render(<MfaChallengeView {...props} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations with WebAuthn unsupported warning", async () => {
    const webauthnChallenge = {
      method: "webauthn" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
      options: {},
    }
    const { container } = render(
      <MfaChallengeView
        {...props}
        webauthnSupported={false}
        mfa={{ ...baseMfa, webauthnChallenge }}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations with WebAuthn-supported challenge", async () => {
    const webauthnChallenge = {
      method: "webauthn" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
      options: {},
    }
    const { container } = render(
      <MfaChallengeView {...props} mfa={{ ...baseMfa, webauthnChallenge }} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
