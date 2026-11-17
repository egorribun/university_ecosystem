import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { StepUpDialog } from "@/components/mfa/StepUpDialog"
import { ChallengeLockedError } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"

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

const createChallenge = (remaining: number): PendingMfaState => {
  const methods = [
    {
      method: "totp" as const,
      challenge_token: `totp-${remaining}`,
      challenge_expires_at: new Date(Date.now() + 60_000).toISOString(),
      options: null,
      attempt_limit: 5,
      attempt_count: Math.max(0, 5 - remaining),
      remaining_attempts: remaining,
    },
  ]
  return {
    status: "mfa_required",
    reason: "step-up",
    user_id: "0194d2e7-9b84-7f04-b2ff-c087ea96a257",
    session_id: "session-1",
    default_method: "totp",
    methods,
  }
}

beforeEach(() => {
  mockUseAuth.mockReset()
})

describe("StepUpDialog", () => {
  it.each([false, undefined])(
    "keeps an unaccepted auto-submitted code (%s) from completing or retrying itself",
    async (result) => {
      const requireMfa = vi.fn<RequireMfaFn>().mockResolvedValue(createChallenge(2))
      const submitMfaChallenge = vi.fn().mockResolvedValue(result)
      const onCompleted = vi.fn()
      const onClose = vi.fn()
      mockUseAuth.mockReturnValue({ requireMfa, submitMfaChallenge })

      const user = userEvent.setup()
      render(<StepUpDialog open onClose={onClose} onCompleted={onCompleted} />)
      const inputs = await screen.findAllByRole("textbox")
      await user.click(inputs[0]!)
      await user.keyboard("123456")

      expect(
        await screen.findByText("Verification failed. Check the code and try again.")
      ).toBeInTheDocument()
      await act(async () => {
        await Promise.resolve()
      })
      expect(submitMfaChallenge).toHaveBeenCalledOnce()
      expect(onCompleted).not.toHaveBeenCalled()
      expect(onClose).not.toHaveBeenCalled()
      inputs.forEach((input) => expect(input).toHaveValue(""))
    }
  )

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

    const inputs = await screen.findAllByRole("textbox")
    expect(inputs.length).toBe(6)
    expect(await screen.findByText("2 attempts remaining")).toBeInTheDocument()

    // OtpEntry handles its own state, so we need to type into each input or ensure it accepts pasting
    await user.click(inputs[0]!)
    await user.keyboard("123456")
    // OtpEntry auto-submits when 6 digits are entered

    await waitFor(() => {
      expect(requireMfa).toHaveBeenCalledTimes(2)
      expect(onChallengeReset).toHaveBeenCalledTimes(1)
    })

    expect(await screen.findByText("Locked")).toBeInTheDocument()
  })
})
