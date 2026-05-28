import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MfaChallengeView } from "./MfaChallengeView"
import type { useMfaFlow } from "@/hooks/auth/useLoginFlow"
import type { MfaMethodChallengeOut } from "@/api/generated"

// Wave 194 SW2 — MfaChallengeView Storybook fixture.
//
// Like LoginCredentialForm, the component consumes the `useMfaFlow()` return as
// a single `mfa` prop (+ activeEmail/trustDevice/onTrustDeviceChange/
// webauthnSupported) — never the coupled hook — so the story supplies a tsc-typed
// mock object. otpChallenge/webauthnChallenge are MfaMethodChallengeOut objects
// (method + challenge_token + challenge_expires_at required). The component is a
// `fixed inset-0` full-screen overlay that renders <ParticleAuthBackground />.
//
// §Honesty: ParticleAuthBackground is a live 1000-particle rAF canvas (its
// VITE_E2E_MODE short-circuit is test-only, not active in Storybook), so the orb
// background is non-deterministic for Chromatic. Collect-only mode (W112 SW1)
// auto-accepts the drift; the glass card UI in front is stable. LazyMotion added
// for any `m.*` descendants (Button/OtpEntry).
//
// Variants: OtpOnly (TOTP entry), WebAuthnAndOtp (security-key + OR + TOTP),
// GeneralError (page-level locked banner), DarkMode.

const FUTURE = "2026-12-31T23:59:59Z"

const otpChallenge: MfaMethodChallengeOut = {
  method: "totp",
  challenge_token: "mock-totp-token",
  challenge_expires_at: FUTURE,
}

const webauthnChallenge: MfaMethodChallengeOut = {
  method: "webauthn",
  challenge_token: "mock-webauthn-token",
  challenge_expires_at: FUTURE,
  options: { challenge: "mock-challenge" },
}

function buildMfa(
  overrides?: Partial<ReturnType<typeof useMfaFlow>>
): ReturnType<typeof useMfaFlow> {
  return {
    loginChallenge: null,
    otpChallenge,
    webauthnChallenge: undefined,
    mfaBusy: false,
    mfaError: null,
    mfaErrorSource: null,
    generalMfaError: null,
    setMfaError: () => {},
    setMfaErrorSource: () => {},
    handleOtpVerify: async () => {},
    handleWebAuthnVerify: async () => {},
    ...overrides,
  }
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <Story />
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MfaChallengeView> = {
  title: "Auth/MfaChallengeView",
  component: MfaChallengeView,
  parameters: {
    layout: "fullscreen",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MfaChallengeView>

export const OtpOnly: Story = {
  render: () => (
    <MfaChallengeView
      activeEmail="student@guu.ru"
      trustDevice={false}
      onTrustDeviceChange={() => {}}
      webauthnSupported
      mfa={buildMfa()}
    />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "TOTP authenticator-code entry only (no WebAuthn method available)." },
    },
  },
}

export const WebAuthnAndOtp: Story = {
  render: () => (
    <MfaChallengeView
      activeEmail="student@guu.ru"
      trustDevice={false}
      onTrustDeviceChange={() => {}}
      webauthnSupported
      mfa={buildMfa({ webauthnChallenge })}
    />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story: "Security-key button + OR divider + TOTP fallback (both methods offered).",
      },
    },
  },
}

export const GeneralError: Story = {
  render: () => (
    <MfaChallengeView
      activeEmail="student@guu.ru"
      trustDevice={false}
      onTrustDeviceChange={() => {}}
      webauthnSupported
      mfa={buildMfa({
        mfaError: "Your account is temporarily locked. Try again later.",
        mfaErrorSource: "general",
        generalMfaError: "Your account is temporarily locked. Try again later.",
      })}
    />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Page-level error banner (e.g. challenge expired / account locked)." },
    },
  },
}

export const DarkMode: Story = {
  render: () => (
    <MfaChallengeView
      activeEmail="student@guu.ru"
      trustDevice={false}
      onTrustDeviceChange={() => {}}
      webauthnSupported
      mfa={buildMfa({ webauthnChallenge })}
    />
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
