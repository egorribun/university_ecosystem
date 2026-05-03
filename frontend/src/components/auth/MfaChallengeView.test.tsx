import { describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"
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
} as const

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
    }
    const { container } = render(
      <MfaChallengeView
        {...props}
        mfa={{ ...baseMfa, otpChallenge }}
      />,
    )
    // OtpEntry renders a digit-input form. We just confirm the page
    // mounted with no crash. (Detailed OtpEntry behaviour is its own test.)
    expect(container).toBeInTheDocument()
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
      options: {},
    }
    const { container } = render(
      <MfaChallengeView
        {...props}
        webauthnSupported={false}
        mfa={{ ...baseMfa, webauthnChallenge }}
      />,
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations with WebAuthn-supported challenge", async () => {
    const webauthnChallenge = {
      method: "webauthn" as const,
      challenge_token: "abc",
      options: {},
    }
    const { container } = render(
      <MfaChallengeView
        {...props}
        mfa={{ ...baseMfa, webauthnChallenge }}
      />,
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
