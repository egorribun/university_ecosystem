import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { AuthContext } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { StepUpDialog } from "./StepUpDialog"

// Wave 199 SW1 — StepUpDialog story (CONTEXT-tier, no infra).
//
// MFA step-up challenge. Renders via createPortal to document.body → default
// theme only (portal escapes `.dark`), layout "fullscreen", LazyMotion for the
// portaled OtpEntry. On open it calls useAuth().requireMfa(); the ambient
// preview AuthContext returns null (→ error state), so the story overrides the
// exported AuthContext (the 9 actions; user/loading still come from Zustand)
// with a requireMfa that resolves a TOTP PendingMfaState → OtpEntry renders.
// submitMfaChallenge is a no-op (won't fire without entering a code).
//
// Variants: Open (TOTP challenge).

const PENDING_MFA: PendingMfaState = {
  status: "mfa_required",
  user_id: "u1",
  default_method: "totp",
  reason: "step-up",
  methods: [
    {
      method: "totp",
      challenge_token: "challenge-token-demo",
      challenge_expires_at: new Date(Date.now() + 300_000).toISOString(),
      attempt_limit: 5,
      remaining_attempts: 5,
    },
  ],
}

const authActions = {
  login: async () => null,
  logout: async () => {},
  setUser: () => {},
  refresh: async () => {},
  submitMfaChallenge: async () => {},
  requireMfa: async () => PENDING_MFA,
  loginWithPasskey: async () => {},
  resetEtagCache: () => {},
  authOperation: false,
}

const withAuth: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <AuthContext.Provider value={authActions}>
      <Story />
    </AuthContext.Provider>
  </LazyMotion>
)

const meta: Meta<typeof StepUpDialog> = {
  title: "MFA/StepUpDialog",
  component: StepUpDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withAuth],
  args: {
    open: true,
    onClose: () => {},
  },
}

export default meta
type Story = StoryObj<typeof StepUpDialog>

export const Open: Story = {}
