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

function axiosError(status: number, detail: string) {
  return Object.assign(new Error(detail), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
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
  it("keeps the challenge when the refreshed profile belongs to a different user", async () => {
    const setSnackbar = vi.fn()
    mocks.fetchQuery.mockResolvedValueOnce({ ...mocks.user, id: "different-user" })
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor: vi.fn() }))

    await act(() => result.current.handleStartEmailMfa())
    expect(result.current.emailChallenge).toEqual(challenge)

    await act(() => result.current.handleConfirmEmailMfa("135790"))

    expect(mocks.verifyMfaChallenge).toHaveBeenCalledOnce()
    expect(result.current.emailChallenge).toEqual(challenge)
    expect(result.current.emailMfaBusy).toBe(false)
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })
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

  it("retries a step-up-protected enablement without recursing into another step-up", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    const setSnackbar = vi.fn()
    mocks.startEmailMfaEnablement
      .mockRejectedValueOnce(axiosError(428, "Step-up required"))
      .mockResolvedValueOnce(challenge)
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor }))

    await act(() => result.current.handleStartEmailMfa())

    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()
    expect(result.current.emailChallenge).toBeNull()

    await act(() => retry?.())

    expect(mocks.startEmailMfaEnablement).toHaveBeenCalledTimes(2)
    expect(result.current.emailChallenge).toEqual(challenge)
  })

  it("ignores a duplicate enablement request while the first request is pending", async () => {
    const pending = deferred<typeof challenge>()
    mocks.startEmailMfaEnablement.mockReturnValueOnce(pending.promise)
    const { result } = renderHook(() =>
      useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor: vi.fn() })
    )

    act(() => {
      void result.current.handleStartEmailMfa()
    })
    expect(result.current.emailMfaBusy).toBe(true)

    await act(() => result.current.handleStartEmailMfa())
    expect(mocks.startEmailMfaEnablement).toHaveBeenCalledOnce()

    await act(async () => pending.resolve(challenge))
    expect(result.current.emailMfaBusy).toBe(false)
  })

  it("surfaces API start errors and falls back to the localized message for transport errors", async () => {
    const setSnackbar = vi.fn()
    mocks.startEmailMfaEnablement.mockRejectedValueOnce(axiosError(400, "Email is unavailable"))
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor: vi.fn() }))

    await act(() => result.current.handleStartEmailMfa())

    expect(result.current.emailMfaError).toBe("Email is unavailable")
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "Email is unavailable",
      severity: "error",
    })

    mocks.startEmailMfaEnablement.mockRejectedValueOnce(new Error("offline"))
    await act(() => result.current.handleStartEmailMfa())

    expect(result.current.emailMfaError).toBe("settings:security.snackbar.emailMfaStartFailed")
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.snackbar.emailMfaStartFailed",
      severity: "error",
    })
  })

  it("does not verify or resend until a challenge has been issued", async () => {
    const { result } = renderHook(() =>
      useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor: vi.fn() })
    )

    await act(() => result.current.handleConfirmEmailMfa("123456"))
    await act(() => result.current.handleResendEmailMfa())

    expect(mocks.verifyMfaChallenge).not.toHaveBeenCalled()
    expect(mocks.resendEmailMfaChallenge).not.toHaveBeenCalled()
  })

  it("announces email verification and ignores confirm or resend while verification is pending", async () => {
    mocks.user.email_verified_at = null
    const verifyPending = deferred<Record<string, never>>()
    mocks.verifyMfaChallenge.mockReturnValueOnce(verifyPending.promise)
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor: vi.fn() }))

    await act(() => result.current.handleStartEmailMfa())
    act(() => {
      void result.current.handleConfirmEmailMfa("654321")
    })
    expect(result.current.emailMfaBusy).toBe(true)

    await act(() => result.current.handleConfirmEmailMfa("111111"))
    await act(() => result.current.handleResendEmailMfa())
    expect(mocks.verifyMfaChallenge).toHaveBeenCalledOnce()
    expect(mocks.resendEmailMfaChallenge).not.toHaveBeenCalled()

    await act(async () => verifyPending.resolve({}))

    expect(result.current.emailChallenge).toBeNull()
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.snackbar.emailVerified",
      severity: "success",
    })
  })

  it("keeps the challenge available when confirmation fails", async () => {
    mocks.verifyMfaChallenge.mockRejectedValueOnce(axiosError(400, "Wrong code"))
    const { result } = renderHook(() =>
      useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor: vi.fn() })
    )

    await act(() => result.current.handleStartEmailMfa())
    await act(() => result.current.handleConfirmEmailMfa("000000"))

    expect(result.current.emailMfaError).toBe("Wrong code")
    expect(result.current.emailChallenge).toEqual(challenge)
    expect(result.current.emailMfaBusy).toBe(false)
  })

  it("reports resend failures and cancellation clears the challenge state", async () => {
    const setSnackbar = vi.fn()
    mocks.resendEmailMfaChallenge.mockRejectedValueOnce(axiosError(429, "Wait before resending"))
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor: vi.fn() }))

    await act(() => result.current.handleStartEmailMfa())
    await act(() => result.current.handleResendEmailMfa())

    expect(result.current.emailMfaError).toBe("Wait before resending")
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "Wait before resending",
      severity: "error",
    })

    act(() => result.current.handleCancelEmailMfa())
    expect(result.current.emailChallenge).toBeNull()
    expect(result.current.emailMfaError).toBeNull()
  })

  it("does not report disable success when the refreshed profile belongs to another user", async () => {
    mocks.user.email_mfa_enabled_at = "2026-01-01T00:00:00Z"
    const setSnackbar = vi.fn()
    let stepUpAction: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      stepUpAction = action
    })
    mocks.fetchQuery.mockResolvedValueOnce({ ...mocks.user, id: "other-user-id" })
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor }))

    act(() => result.current.handleDisableEmailMfa())

    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(stepUpAction).toBeDefined()
    await act(async () => {
      await stepUpAction?.()
    })

    expect(mocks.disableEmailMfa).toHaveBeenCalledOnce()
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })
  it("keeps a new operation busy when an older session request settles", async () => {
    const firstRequest = deferred<typeof challenge>()
    const secondRequest = deferred<typeof challenge>()
    mocks.startEmailMfaEnablement
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise)
    const originalUser = mocks.user
    const { result, rerender } = renderHook(() =>
      useEmailMfa({ setSnackbar: vi.fn(), openStepUpFor: vi.fn() })
    )
    let firstCompletion: Promise<void> | undefined
    let secondCompletion: Promise<void> | undefined

    try {
      act(() => {
        firstCompletion = result.current.handleStartEmailMfa()
      })
      expect(result.current.emailMfaBusy).toBe(true)

      mocks.user = { ...originalUser, id: "different-session-user" }
      rerender()
      expect(result.current.emailMfaBusy).toBe(false)

      act(() => {
        secondCompletion = result.current.handleStartEmailMfa()
      })
      expect(result.current.emailMfaBusy).toBe(true)

      await act(async () => {
        firstRequest.resolve(challenge)
        await firstCompletion
      })
      expect(result.current.emailMfaBusy).toBe(true)
      expect(result.current.emailChallenge).toBeNull()

      await act(async () => {
        secondRequest.resolve(challenge)
        await secondCompletion
      })
      expect(result.current.emailMfaBusy).toBe(false)
    } finally {
      firstRequest.resolve(challenge)
      secondRequest.resolve(challenge)
      const pending = [firstCompletion, secondCompletion].filter(
        (promise): promise is Promise<void> => promise !== undefined
      )
      if (pending.length > 0) {
        await act(async () => {
          await Promise.all(pending)
        })
      }
      mocks.user = originalUser
    }
  })
  it("reports a step-up disable failure without clearing the current user", async () => {
    const setSnackbar = vi.fn()
    const openStepUpFor = vi.fn((action: () => Promise<void>) => void action())
    mocks.disableEmailMfa.mockRejectedValueOnce(new Error("offline"))
    const { result } = renderHook(() => useEmailMfa({ setSnackbar, openStepUpFor }))

    act(() => result.current.handleDisableEmailMfa())
    await act(async () => Promise.resolve())

    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.snackbar.emailMfaDisableFailed",
      severity: "error",
    })
  })
})
