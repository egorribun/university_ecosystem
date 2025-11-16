import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import StepUpDialog from "@/components/mfa/StepUpDialog"
import { ChallengeLockedError, type PendingMfaState } from "@/contexts/AuthContext"

type RequireMfaFn = () => Promise<PendingMfaState | null>

const mockUseAuth = vi.fn()

vi.mock("@/contexts/AuthContext", async () => {
  const actual =
    await vi.importActual<typeof import("@/contexts/AuthContext")>("@/contexts/AuthContext")
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  }
})

const createChallenge = (remaining: number): PendingMfaState => ({
  status: "mfa_required",
  reason: "step-up",
  user_id: 1,
  session_id: 42,
  default_method: "totp",
  methods: [
    {
      method: "totp",
      challenge_token: `totp-${remaining}`,
      challenge_expires_at: new Date(Date.now() + 60_000).toISOString(),
      options: null,
      attempt_limit: 5,
      attempt_count: Math.max(0, 5 - remaining),
      remaining_attempts: remaining,
    },
  ],
})

beforeEach(() => {
  mockUseAuth.mockReset()
})

describe("StepUpDialog", () => {
  it("refreshes challenges when a locked error is refreshable", async () => {
    const initialChallenge = createChallenge(2)
    const refreshedChallenge = createChallenge(5)
    const requireMfa = vi
      .fn<RequireMfaFn>()
      .mockResolvedValueOnce(initialChallenge)
      .mockResolvedValueOnce(refreshedChallenge)
    const submitMfaChallenge = vi
      .fn()
      .mockRejectedValueOnce(new ChallengeLockedError("Locked", { refreshable: true }))
    const onChallengeReset = vi.fn()
    mockUseAuth.mockReturnValue({ requireMfa, submitMfaChallenge })

    const user = userEvent.setup()

    render(<StepUpDialog open onClose={() => {}} onChallengeReset={onChallengeReset} />)

    const input = await screen.findByLabelText("Authenticator code")
    expect(await screen.findByText("2 attempts remaining")).toBeInTheDocument()

    await user.type(input, "123456")
    await user.click(screen.getByRole("button", { name: /verify/i }))

    await waitFor(() => {
      expect(requireMfa).toHaveBeenCalledTimes(2)
      expect(onChallengeReset).toHaveBeenCalledTimes(1)
    })

    expect(await screen.findByText("Locked")).toBeInTheDocument()
  })
})
