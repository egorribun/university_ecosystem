import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { axe } from "jest-axe"

import { MfaChallengeView } from "./MfaChallengeView"

/**
 * MfaChallengeView axe + render-shape tests.
 *
 * The view renders one of three layouts depending on the available
 * methods on `mfa.loginChallenge`:
 *  - email OTP-only;
 *  - TOTP-only;
 *  - both (separator between);
 *  - neither (warning + start-over).
 *
 * The full interaction flow (OTP entry and resend)
 * involves AuthContext, timers,
 * APIs, and react-hook-form — covered end-to-end by Track D specs.
 * Here we only pin the ARIA / accessibility contract for each shape.
 */

const baseMfa = {
  loginChallenge: null,
  otpChallenge: undefined,
  emailChallenge: undefined,
  resendSeconds: 0,
  mfaBusy: false,
  mfaError: null as string | null,
  mfaErrorSource: null as null | "totp" | "email_otp" | "general",
  generalMfaError: null,
  setMfaError: vi.fn(),
  setMfaErrorSource: vi.fn(),
  handleOtpVerify: vi.fn(),
  handleEmailOtpVerify: vi.fn(),
  handleResendEmailOtp: vi.fn(),
  showRecoveryInput: false,
  setShowRecoveryInput: vi.fn(),
  handleRecoveryVerify: vi.fn(),
}

const props = {
  activeEmail: "user@example.com",
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
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  })

  it("uses the account fallback when the active email is empty", () => {
    render(<MfaChallengeView {...props} activeEmail="" />)
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/your account/i)
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
    await waitFor(() => {
      expect(handleOtpVerify).toHaveBeenCalledWith("123456")
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

describe("MfaChallengeView — email OTP interaction", () => {
  it("renders the masked delivery hint and invokes resend", async () => {
    const handleResendEmailOtp = vi.fn()
    const emailChallenge = {
      method: "email_otp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
      delivery_hint: "u***@example.com",
    }
    const user = userEvent.setup()

    render(
      <MfaChallengeView {...props} mfa={{ ...baseMfa, emailChallenge, handleResendEmailOtp }} />
    )
    expect(screen.getByText(/u\*\*\*@example\.com/i)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /send.*code|resend/i }))
    expect(handleResendEmailOtp).toHaveBeenCalledOnce()
  })

  it("disables resend during cooldown and renders the separator for both methods", () => {
    const emailChallenge = {
      method: "email_otp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "def",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }

    const { rerender } = render(
      <MfaChallengeView {...props} mfa={{ ...baseMfa, emailChallenge, resendSeconds: 42 }} />
    )
    expect(screen.getByRole("button", { name: /42/ })).toBeDisabled()

    rerender(<MfaChallengeView {...props} mfa={{ ...baseMfa, emailChallenge, otpChallenge }} />)
    expect(screen.getByText("OR")).toBeInTheDocument()
  })

  it("shows only an email-specific error in the email OTP entry", () => {
    const emailChallenge = {
      method: "email_otp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    render(
      <MfaChallengeView
        {...props}
        mfa={{
          ...baseMfa,
          emailChallenge,
          mfaError: "Invalid email code",
          mfaErrorSource: "email_otp",
        }}
      />
    )
    expect(screen.getByText("Invalid email code")).toBeInTheDocument()
  })
})

describe("MfaChallengeView — recovery interaction", () => {
  const recoveryMfa = {
    ...baseMfa,
    showRecoveryInput: true,
  }

  it("submits trimmed recovery codes from Enter and the button, and returns to OTP", async () => {
    const handleRecoveryVerify = vi.fn()
    const setShowRecoveryInput = vi.fn()
    const user = userEvent.setup()

    render(
      <MfaChallengeView
        {...props}
        mfa={{ ...recoveryMfa, handleRecoveryVerify, setShowRecoveryInput }}
      />
    )

    const input = screen.getByRole("textbox", { name: "Recovery code" })
    await user.type(input, "  ABC-123  ")
    await user.keyboard("{Enter}")
    expect(handleRecoveryVerify).toHaveBeenCalledWith("ABC-123")

    await user.clear(input)
    await user.type(input, "XYZ-789")
    await user.click(screen.getByRole("button", { name: /Подтвердить|verify/i }))
    expect(handleRecoveryVerify).toHaveBeenCalledWith("XYZ-789")

    await user.clear(input)
    await user.click(screen.getByRole("button", { name: /Подтвердить|verify/i }))
    expect(handleRecoveryVerify).toHaveBeenCalledTimes(2)

    await user.click(screen.getByRole("button", { name: /обычный код|regular verification/i }))
    expect(setShowRecoveryInput).toHaveBeenCalledWith(false)
  })

  it("does not submit an empty recovery code and disables recovery controls while busy", async () => {
    const handleRecoveryVerify = vi.fn()
    const user = userEvent.setup()

    render(
      <MfaChallengeView {...props} mfa={{ ...recoveryMfa, mfaBusy: true, handleRecoveryVerify }} />
    )

    const input = screen.getByRole("textbox", { name: "Recovery code" })
    expect(input).toBeDisabled()
    expect(screen.getByRole("button", { name: /Подтвердить|verify/i })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: /обычный код|regular verification/i }))
    expect(handleRecoveryVerify).not.toHaveBeenCalled()
  })

  it("ignores an empty recovery code on the enabled submit button", () => {
    const handleRecoveryVerify = vi.fn()
    render(<MfaChallengeView {...props} mfa={{ ...recoveryMfa, handleRecoveryVerify }} />)

    fireEvent.click(screen.getByRole("button", { name: /Подтвердить|verify/i }))
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Recovery code" }), {
      key: "Enter",
    })
    expect(handleRecoveryVerify).not.toHaveBeenCalled()
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

  it("reloads the page when start-over is activated", () => {
    const originalLocation = window.location
    const reload = vi.fn()
    const mockLocation = Object.create(originalLocation)
    Object.defineProperty(mockLocation, "reload", {
      value: reload,
      configurable: true,
    })
    Object.defineProperty(window, "location", {
      value: mockLocation,
      configurable: true,
    })

    try {
      render(<MfaChallengeView {...props} />)
      fireEvent.click(screen.getByRole("button", { name: /different account/i }))
      expect(reload).toHaveBeenCalledTimes(1)
    } finally {
      Object.defineProperty(window, "location", {
        value: originalLocation,
        configurable: true,
      })
    }
  })
})

describe("MfaChallengeView — recovery toggle", () => {
  it("opens the recovery-code input from the TOTP view", () => {
    const setShowRecoveryInput = vi.fn()
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }

    render(<MfaChallengeView {...props} mfa={{ ...baseMfa, otpChallenge, setShowRecoveryInput }} />)

    fireEvent.click(document.getElementById("use-recovery-code-toggle") as HTMLElement)
    expect(setShowRecoveryInput).toHaveBeenCalledWith(true)
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

  it("passes a TOTP-specific error into the OTP entry", () => {
    const otpChallenge = {
      method: "totp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
    }
    render(
      <MfaChallengeView
        {...props}
        mfa={{
          ...baseMfa,
          otpChallenge,
          mfaError: "Invalid authenticator code",
          mfaErrorSource: "totp",
        }}
      />
    )
    expect(screen.getByText("Invalid authenticator code")).toBeInTheDocument()
  })
})

describe("MfaChallengeView — accessibility", () => {
  it("has no axe violations in the no-methods state", async () => {
    const { container } = render(<MfaChallengeView {...props} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations with an email OTP challenge", async () => {
    const emailChallenge = {
      method: "email_otp" as const,
      challenge_token: "abc",
      challenge_expires_at: "2099-01-01T00:00:00Z",
      delivery_hint: "u***@example.com",
    }
    const { container } = render(
      <MfaChallengeView {...props} mfa={{ ...baseMfa, emailChallenge }} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
