import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  user: {
    id: "user-1",
    email_verified_at: "2026-08-01T00:00:00Z" as string | null,
    email_mfa_enabled_at: null as string | null,
  },
  setUser: vi.fn(),
  fetchQuery: vi.fn(),
  startEmailVerification: vi.fn(),
  startEmailMfaEnablement: vi.fn(),
  resendEmailMfaChallenge: vi.fn(),
  verifyMfaChallenge: vi.fn(),
  disableEmailMfa: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ fetchQuery: mocks.fetchQuery }),
}))

vi.mock("@/api/mfa", () => ({
  startEmailVerification: mocks.startEmailVerification,
  startEmailMfaEnablement: mocks.startEmailMfaEnablement,
  resendEmailMfaChallenge: mocks.resendEmailMfaChallenge,
  verifyMfaChallenge: mocks.verifyMfaChallenge,
  disableEmailMfa: mocks.disableEmailMfa,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: vi.fn(),
}))

import { useEmailMfa } from "./useEmailMfa"

const challenge = {
  method: "email_otp" as const,
  challenge_token: "challenge-token-1234567890",
  challenge_expires_at: "2026-08-25T16:00:00Z",
  delivery_hint: "u***@example.com",
  resend_available_at: "2026-08-25T15:59:00Z",
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.user.email_verified_at = "2026-08-01T00:00:00Z"
  mocks.user.email_mfa_enabled_at = null
  mocks.startEmailMfaEnablement.mockResolvedValue(challenge)
  mocks.startEmailVerification.mockResolvedValue(challenge)
  mocks.resendEmailMfaChallenge.mockResolvedValue({
    ...challenge,
    challenge_token: "rotated-token-1234567890",
  })
  mocks.verifyMfaChallenge.mockResolvedValue({})
  mocks.disableEmailMfa.mockResolvedValue({ disabled: true })
  mocks.fetchQuery.mockResolvedValue({ ...mocks.user, email_mfa_enabled_at: "2026-08-25" })
})

describe("useEmailMfa", () => {
  it("starts enablement for a verified email and verifies the issued challenge", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor: vi.fn() }))

    await act(() => result.current.handleStartEmailMfa())
    expect(mocks.startEmailMfaEnablement).toHaveBeenCalledOnce()
    expect(result.current.emailChallenge).toEqual(challenge)

    await act(() => result.current.handleConfirmEmailMfa("123456"))
    expect(mocks.verifyMfaChallenge).toHaveBeenCalledWith({
      method: "email_otp",
      code: "123456",
      challenge_token: challenge.challenge_token,
    })
    expect(mocks.setUser).toHaveBeenCalled()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.snackbar.emailMfaEnabled",
      severity: "success",
    })
  })

  it("verifies the account email before allowing email MFA enablement", async () => {
    mocks.user.email_verified_at = null
    const { result } = renderHook(() =>
      useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor: vi.fn() })
    )

    await act(() => result.current.handleStartEmailMfa())
    expect(mocks.startEmailVerification).toHaveBeenCalledOnce()
    expect(mocks.startEmailMfaEnablement).not.toHaveBeenCalled()
  })

  it("rotates the local challenge on resend and disables through step-up", async () => {
    const openStepUpFor = vi.fn((action: () => Promise<void>) => void action())
    const { result } = renderHook(() => useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor }))

    await act(() => result.current.handleStartEmailMfa())
    await act(() => result.current.handleResendEmailMfa())
    expect(mocks.resendEmailMfaChallenge).toHaveBeenCalledWith(challenge.challenge_token)
    expect(result.current.emailChallenge?.challenge_token).toBe("rotated-token-1234567890")

    act(() => result.current.handleDisableEmailMfa())
    expect(openStepUpFor).toHaveBeenCalledOnce()
    await act(async () => Promise.resolve())
    expect(mocks.disableEmailMfa).toHaveBeenCalledOnce()
  })
})
