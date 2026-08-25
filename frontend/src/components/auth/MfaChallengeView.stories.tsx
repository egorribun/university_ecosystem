import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MfaChallengeView } from "./MfaChallengeView"
import type { useMfaFlow } from "@/hooks/auth/useLoginFlow"
import type { MfaMethodChallengeOut } from "@/api/generated"

// Wave 194 SW2 — MfaChallengeView Storybook fixture.
//
// Like LoginCredentialForm, the component consumes the `useMfaFlow()` return as
// a single `mfa` prop (+ activeEmail) — never the
// coupled hook — so the story supplies a tsc-typed mock object. Challenges are
// (method + challenge_token + challenge_expires_at required). The component is a
// `fixed inset-0` full-screen overlay that renders <ParticleAuthBackground />.
//
// §Honesty: ParticleAuthBackground is a live 1000-particle rAF canvas (its
// VITE_E2E_MODE short-circuit is test-only, not active in Storybook), so the orb
// background is non-deterministic for Chromatic. Collect-only mode (W112 SW1)
// auto-accepts the drift; the glass card UI in front is stable. LazyMotion added
// for any `m.*` descendants (Button/OtpEntry).
//
// Variants: OtpOnly, EmailAndOtp, GeneralError,
// GeneralError (page-level locked banner), DarkMode.

const FUTURE = "2026-12-31T23:59:59Z"

const otpChallenge: MfaMethodChallengeOut = {
  method: "totp",
  challenge_token: "mock-totp-token",
  challenge_expires_at: FUTURE,
}

const emailChallenge: MfaMethodChallengeOut = {
  method: "email_otp",
  challenge_token: "mock-email-token",
  challenge_expires_at: FUTURE,
  delivery_hint: "s***@guu.ru",
  resend_available_at: FUTURE,
}

function buildMfa(
  overrides?: Partial<ReturnType<typeof useMfaFlow>>
): ReturnType<typeof useMfaFlow> {
  return {
    loginChallenge: null,
    otpChallenge,
    emailChallenge: undefined,
    resendSeconds: 0,
    mfaBusy: false,
    mfaError: null,
    mfaErrorSource: null,
    generalMfaError: null,
    setMfaError: () => {},
    setMfaErrorSource: () => {},
    handleOtpVerify: async () => {},
    handleEmailOtpVerify: async () => {},
    handleResendEmailOtp: async () => {},
    showRecoveryInput: false,
    setShowRecoveryInput: () => {},
    handleRecoveryVerify: async () => {},
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
    // W201: renders the live ParticleAuthBackground canvas — pauseAnimationAtEnd
    // can't freeze a particle swarm, so skip the snapshot (loses glass-card UI
    // coverage; accepted vs a perpetual false-positive — AUDIT_WAVE201 §Honesty).
    chromatic: { disableSnapshot: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MfaChallengeView>

export const OtpOnly: Story = {
  render: () => <MfaChallengeView activeEmail="student@guu.ru" mfa={buildMfa()} />,
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "TOTP authenticator-code entry." },
    },
  },
}

export const EmailAndOtp: Story = {
  render: () => (
    <MfaChallengeView activeEmail="student@guu.ru" mfa={buildMfa({ emailChallenge })} />
  ),
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: {
        story: "Email OTP delivery and resend controls with a TOTP fallback.",
      },
    },
  },
}

export const GeneralError: Story = {
  render: () => (
    <MfaChallengeView
      activeEmail="student@guu.ru"
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
    <MfaChallengeView activeEmail="student@guu.ru" mfa={buildMfa({ emailChallenge })} />
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
