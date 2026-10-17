import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { StrictMode, type PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { MfaTotpEnrollment, TotpEnrollmentStart } from "@/types/Mfa"
import { useTotpEnrollment } from "../useTotpEnrollment"

const mocks = vi.hoisted(() => ({
  user: {
    id: "user-1",
    mfa_required: false,
    mfa_default_method: null as string | null,
    mfa_last_verified_at: null as string | null,
    totp_enrollments: [] as MfaTotpEnrollment[],
  },
  setUser: vi.fn(),
  fetchQuery: vi.fn(async () => ({ id: "user-1" })),
  startTotpEnrollment: vi.fn(),
  confirmTotpEnrollment: vi.fn(),
  deleteTotpEnrollment: vi.fn(),
  deletePendingTotpEnrollment: vi.fn(),
  extractApiError: vi.fn((error: unknown) => ({
    status: error && typeof error === "object" && "status" in error ? error.status : undefined,
    message:
      error instanceof Error
        ? error.message
        : error && typeof error === "object" && "message" in error
          ? String(error.message)
          : "api error",
  })),
  formatDate: vi.fn((value: string) => `formatted:${value}`),
  t: vi.fn((key: string, options?: { value?: string }) =>
    options?.value === undefined ? key : `${key}:${options.value}`
  ),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: mocks.fetchQuery,
}))

vi.mock("@/api/mfa", () => ({
  startTotpEnrollment: mocks.startTotpEnrollment,
  confirmTotpEnrollment: mocks.confirmTotpEnrollment,
  deleteTotpEnrollment: mocks.deleteTotpEnrollment,
  deletePendingTotpEnrollment: mocks.deletePendingTotpEnrollment,
}))

vi.mock("@/utils/error", () => ({ extractApiError: mocks.extractApiError }))
vi.mock("@/utils/date", () => ({ formatDate: mocks.formatDate }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))

const enrollment = (overrides: Partial<MfaTotpEnrollment> = {}): MfaTotpEnrollment => ({
  id: "totp-1",
  user_id: "user-1",
  created_at: "2026-07-01T00:00:00Z",
  is_active: true,
  ...overrides,
})

const draft = (id = "totp-1", userId = "user-1"): TotpEnrollmentStart => ({
  enrollment: enrollment({ id, user_id: userId }),
  secret: "secret", // pragma: allowlist secret
  otpauth_url: "otpauth://totp/test",
})

type Deferred<T> = {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason?: unknown) => void
}

const deferred = <T,>(): Deferred<T> => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const settleEnrollmentRequests = async (...requests: Deferred<TotpEnrollmentStart>[]) => {
  requests.forEach((request) => request.resolve(draft("cleanup")))
  await Promise.allSettled(requests.map((request) => request.promise))
}

const renderTotpHook = (openStepUpFor = vi.fn()) => {
  const setSnackbar = vi.fn()
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useTotpEnrollment({ setSnackbar, openStepUpFor }), { wrapper })
  return { ...hook, setSnackbar, openStepUpFor }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.user = {
    id: "user-1",
    mfa_required: false,
    mfa_default_method: null,
    mfa_last_verified_at: null,
    totp_enrollments: [],
  }
  mocks.startTotpEnrollment.mockReset()
  mocks.startTotpEnrollment.mockResolvedValue(draft())
  mocks.confirmTotpEnrollment.mockResolvedValue(undefined)
  mocks.deleteTotpEnrollment.mockResolvedValue({ mfa_default_method: null, mfa_required: false })
  mocks.deletePendingTotpEnrollment.mockResolvedValue(undefined)
  mocks.fetchQuery.mockResolvedValue({ id: "user-1" })
})

describe("useTotpEnrollment — derived state", () => {
  it("separates active and pending enrollments and formats security status", () => {
    mocks.user = {
      ...mocks.user,
      mfa_required: true,
      mfa_default_method: "totp",
      mfa_last_verified_at: "2026-07-30T10:00:00Z",
      totp_enrollments: [
        enrollment({ id: "active", confirmed_at: "2026-07-01T01:00:00Z" }),
        enrollment({ id: "pending", confirmed_at: null }),
        enrollment({ id: "revoked", confirmed_at: "2026-07-01T01:00:00Z", revoked_at: "now" }),
      ],
    }
    const { result } = renderTotpHook()

    expect(result.current.activeTotp.map((item) => item.id)).toEqual(["active"])
    expect(result.current.pendingTotpEnrollment?.id).toBe("pending")
    expect(result.current.hasInteractiveMfa).toBe(true)
    expect(result.current.totpLimitReached).toBe(true)
    expect(result.current.mfaDisabledMessage).toBeNull()
    expect(result.current.defaultMethodText).toBe("settings:security.status.defaultTotp")
    expect(result.current.lastVerifiedText).toBe(
      "settings:security.status.lastVerified:formatted:2026-07-30T10:00:00Z"
    )
    expect(result.current.formatDateTime(null)).toBeNull()
  })

  it("shows disabled/default/not-verified messages when no MFA is active", () => {
    mocks.user.mfa_required = true
    const { result } = renderTotpHook()

    expect(result.current.mfaDisabledMessage).toBe(
      "settings:security.status.mfaDisabledWasRequired"
    )
    expect(result.current.defaultMethodText).toBe("settings:security.status.noDefault")
    expect(result.current.lastVerifiedText).toBe("settings:security.status.notVerified")
  })

  it("handles a missing authenticated user with the safe derived defaults", () => {
    mocks.user = null as never
    const { result } = renderTotpHook()

    expect(result.current.activeTotp).toEqual([])
    expect(result.current.pendingTotpEnrollment).toBeNull()
    expect(result.current.mfaDisabledMessage).toBe("settings:security.status.mfaDisabled")
    expect(result.current.defaultMethodText).toBe("settings:security.status.noDefault")
    expect(result.current.lastVerifiedText).toBe("settings:security.status.notVerified")
  })

  it("falls back when the last-verified date cannot be formatted", () => {
    mocks.user.mfa_last_verified_at = "2026-07-30T10:00:00Z"
    mocks.formatDate.mockReturnValueOnce("")
    const { result } = renderTotpHook()

    expect(result.current.lastVerifiedText).toBe("settings:security.status.notVerified")
  })
})

describe("useTotpEnrollment — start and confirm", () => {
  it("starts enrollment with a payload and stores the draft", async () => {
    const { result } = renderTotpHook()
    const payload = { label: "Authenticator", reuse_existing: false }

    await act(async () => {
      await result.current.handleStartTotp({ payload })
    })

    expect(mocks.startTotpEnrollment).toHaveBeenCalledWith(payload)
    expect(result.current.totpDraft).toEqual(draft())
    expect(result.current.totpBusy).toBe(false)
  })

  it("auto-resumes a pending enrollment with reuse_existing", async () => {
    mocks.user.totp_enrollments = [enrollment({ confirmed_at: null })]
    const { result } = renderTotpHook()

    await waitFor(() =>
      expect(mocks.startTotpEnrollment).toHaveBeenCalledWith({ reuse_existing: true })
    )
    await waitFor(() => expect(result.current.totpDraft).toEqual(draft()))
  })

  it("does not auto-retry a failed pending enrollment, but allows manual retry", async () => {
    mocks.user.totp_enrollments = [enrollment({ id: "pending", confirmed_at: null })]
    const first = deferred<TotpEnrollmentStart>()
    const manualRetry = deferred<TotpEnrollmentStart>()
    mocks.startTotpEnrollment
      .mockImplementationOnce(() => first.promise)
      .mockImplementation(() => manualRetry.promise)
    const { result, unmount } = renderTotpHook()

    try {
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1))
      await act(async () => {
        first.reject({ status: 400, message: "Start failed" })
        await first.promise.catch(() => undefined)
      })

      // Check before waiting for the error: an automatic retry can clear it.
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1)
      await waitFor(() => expect(result.current.totpError).toBe("Start failed"))
      expect(result.current.totpBusy).toBe(false)

      await act(async () => {
        const retry = result.current.handleStartTotp()
        manualRetry.resolve(draft("pending"))
        await retry
      })
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2)
      expect(result.current.totpDraft).toEqual(draft("pending"))
    } finally {
      unmount()
      await settleEnrollmentRequests(first, manualRetry)
    }
  })

  it("keeps the auto-resume 428 continuation available without auto-retrying", async () => {
    mocks.user.totp_enrollments = [enrollment({ id: "pending", confirmed_at: null })]
    const first = deferred<TotpEnrollmentStart>()
    const stepUpRetry = deferred<TotpEnrollmentStart>()
    let continuation: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      continuation = action
    })
    mocks.startTotpEnrollment
      .mockImplementationOnce(() => first.promise)
      .mockImplementation(() => stepUpRetry.promise)
    const { result, unmount } = renderTotpHook(openStepUpFor)

    try {
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1))
      await act(async () => {
        first.reject({ status: 428, message: "step up" })
        await first.promise.catch(() => undefined)
      })

      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1)
      expect(openStepUpFor).toHaveBeenCalledOnce()
      expect(continuation).toBeDefined()

      await act(async () => {
        const retry = continuation?.()
        stepUpRetry.resolve(draft("pending"))
        await retry
      })
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2)
      expect(result.current.totpDraft).toEqual(draft("pending"))
    } finally {
      unmount()
      await settleEnrollmentRequests(first, stepUpRetry)
    }
  })

  it("does not consume the pending ID while the active-enrollment limit is reached", async () => {
    const pending = enrollment({ id: "pending", confirmed_at: null })
    mocks.user = {
      ...mocks.user,
      totp_enrollments: [
        enrollment({ id: "active", confirmed_at: "2026-07-01T01:00:00Z" }),
        pending,
      ],
    }
    mocks.startTotpEnrollment.mockResolvedValue(draft("pending"))
    const { result, rerender } = renderTotpHook()

    expect(result.current.totpLimitReached).toBe(true)
    expect(mocks.startTotpEnrollment).not.toHaveBeenCalled()
    mocks.user = { ...mocks.user, totp_enrollments: [pending] }
    rerender()

    await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.totpDraft).toEqual(draft("pending")))
  })

  it("waits for the current request before resuming a changed pending ID", async () => {
    mocks.user.totp_enrollments = [enrollment({ id: "pending-1", confirmed_at: null })]
    const first = deferred<TotpEnrollmentStart>()
    const next = deferred<TotpEnrollmentStart>()
    mocks.startTotpEnrollment
      .mockImplementationOnce(() => first.promise)
      .mockImplementation(() => next.promise)
    const { result, rerender, unmount } = renderTotpHook()

    try {
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1))
      mocks.user = {
        ...mocks.user,
        totp_enrollments: [enrollment({ id: "pending-2", confirmed_at: null })],
      }
      rerender()
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1)

      await act(async () => {
        first.reject({ status: 400, message: "Start failed" })
        await first.promise.catch(() => undefined)
      })
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2))
      expect(mocks.startTotpEnrollment).toHaveBeenLastCalledWith({ reuse_existing: true })

      await act(async () => {
        next.resolve(draft("pending-2"))
        await next.promise
      })
      await waitFor(() => expect(result.current.totpDraft).toEqual(draft("pending-2")))
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2)
    } finally {
      unmount()
      await settleEnrollmentRequests(first, next)
    }
  })

  it("auto-resumes a pending enrollment under StrictMode with a usable draft", async () => {
    mocks.user.totp_enrollments = [enrollment({ id: "pending", confirmed_at: null })]
    mocks.startTotpEnrollment.mockResolvedValue(draft("pending"))
    const setSnackbar = vi.fn()
    const openStepUpFor = vi.fn()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <StrictMode>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </StrictMode>
    )
    const { result, unmount } = renderHook(
      () => useTotpEnrollment({ setSnackbar, openStepUpFor }),
      { wrapper }
    )

    try {
      await waitFor(() => expect(result.current.totpDraft).toEqual(draft("pending")))
      expect(mocks.startTotpEnrollment).toHaveBeenCalled()
      expect(mocks.startTotpEnrollment.mock.calls.length).toBeLessThanOrEqual(2)
    } finally {
      unmount()
      queryClient.clear()
    }
  })

  it("starts the new account's pending enrollment after an account switch", async () => {
    mocks.user.totp_enrollments = [
      enrollment({ id: "pending-1", user_id: "user-1", confirmed_at: null }),
    ]
    const first = deferred<TotpEnrollmentStart>()
    const next = deferred<TotpEnrollmentStart>()
    mocks.startTotpEnrollment
      .mockImplementationOnce(() => first.promise)
      .mockImplementation(() => next.promise)
    const { result, rerender, unmount } = renderTotpHook()

    try {
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1))
      mocks.user = {
        ...mocks.user,
        id: "user-2",
        totp_enrollments: [enrollment({ id: "pending-2", user_id: "user-2", confirmed_at: null })],
      }
      rerender()
      await waitFor(() => expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2))

      await act(async () => {
        first.resolve(draft("pending-1"))
        await first.promise
      })
      expect(result.current.totpDraft).toBeNull()

      await act(async () => {
        next.resolve(draft("pending-2", "user-2"))
        await next.promise
      })
      await waitFor(() => expect(result.current.totpDraft).toEqual(draft("pending-2", "user-2")))
      expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2)
    } finally {
      unmount()
      await settleEnrollmentRequests(first, next)
    }
  })

  it("opens step-up and retries a 428 start failure", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    mocks.startTotpEnrollment.mockRejectedValueOnce({ status: 428, message: "step up" })
    const { result, setSnackbar } = renderTotpHook(openStepUpFor)

    await act(async () => {
      await result.current.handleStartTotp({ payload: { label: "Key" } })
    })
    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()

    await act(async () => {
      await retry?.()
    })
    expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(2)
    expect(result.current.totpDraft).toEqual(draft())
  })

  it("reports start errors and ignores start when the limit is reached", async () => {
    mocks.startTotpEnrollment.mockRejectedValue({ status: 400, message: "Start failed" })
    const { result, setSnackbar } = renderTotpHook()

    await act(async () => {
      await result.current.handleStartTotp()
    })
    expect(result.current.totpError).toBe("Start failed")
    expect(setSnackbar).toHaveBeenCalledWith({ text: "Start failed", severity: "error" })

    mocks.user.totp_enrollments = [enrollment({ confirmed_at: "confirmed" })]
    const limited = renderTotpHook()
    await act(async () => {
      await limited.result.current.handleStartTotp()
    })
    expect(mocks.startTotpEnrollment).toHaveBeenCalledTimes(1)
  })

  it("uses the translated fallback for an error without an API status", async () => {
    mocks.startTotpEnrollment.mockRejectedValueOnce({ reason: "offline" })
    const { result, setSnackbar } = renderTotpHook()

    await act(async () => {
      await result.current.handleStartTotp()
    })

    expect(result.current.totpError).toBe("settings:security.snackbar.totpStartFailed")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.snackbar.totpStartFailed",
      severity: "error",
    })
  })

  it("confirms a draft, refreshes the user, and handles missing enrollment safely", async () => {
    const { result, setSnackbar } = renderTotpHook()
    await act(async () => {
      await result.current.handleConfirmTotp("123456")
    })
    expect(mocks.confirmTotpEnrollment).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.handleStartTotp()
    })
    await waitFor(() => expect(result.current.totpDraft).not.toBeNull())
    await act(async () => {
      await result.current.handleConfirmTotp("123456")
    })
    expect(mocks.confirmTotpEnrollment).toHaveBeenCalledWith({
      enrollment_id: "totp-1",
      code: "123456",
    })
    expect(mocks.fetchQuery).toHaveBeenCalled()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.snackbar.totpEnabled",
      severity: "success",
    })
    expect(result.current.totpDraft).toBeNull()
  })

  it("surfaces confirmation errors without a snackbar", async () => {
    mocks.confirmTotpEnrollment.mockRejectedValue({ status: 422, message: "Invalid code" })
    const { result, setSnackbar } = renderTotpHook()

    await act(async () => {
      await result.current.handleStartTotp()
    })
    await waitFor(() => expect(result.current.totpDraft).not.toBeNull())
    await act(async () => {
      await result.current.handleConfirmTotp("000000")
    })

    expect(result.current.totpError).toBe("Invalid code")
    expect(setSnackbar).not.toHaveBeenCalled()
  })
})

describe("useTotpEnrollment — cancel and disable", () => {
  it("cancels a draft, refreshes the user, and ignores duplicate cancellation", async () => {
    const { result } = renderTotpHook()
    await act(async () => {
      await result.current.handleCancelTotp()
    })
    expect(mocks.deletePendingTotpEnrollment).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.handleStartTotp()
    })
    await waitFor(() => expect(result.current.totpDraft).not.toBeNull())
    await act(async () => {
      await result.current.handleCancelTotp()
    })
    expect(mocks.deletePendingTotpEnrollment).toHaveBeenCalledWith("totp-1")
    expect(mocks.fetchQuery).toHaveBeenCalled()
    expect(result.current.totpDraft).toBeNull()
  })

  it("reports cancel errors", async () => {
    mocks.deletePendingTotpEnrollment.mockRejectedValue({ status: 400, message: "Cancel failed" })
    const { result, setSnackbar } = renderTotpHook(vi.fn())

    await act(async () => {
      await result.current.handleStartTotp()
    })
    await waitFor(() => expect(result.current.totpDraft).not.toBeNull())
    await act(async () => {
      await result.current.handleCancelTotp()
    })
    expect(result.current.totpError).toBe("Cancel failed")
    expect(setSnackbar).toHaveBeenCalledWith({ text: "Cancel failed", severity: "error" })
  })

  it("opens step-up for disable, applies returned MFA state, and reports failures", async () => {
    let action: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((next: () => Promise<void>) => {
      action = next
    })
    const { result, setSnackbar } = renderTotpHook(openStepUpFor)

    result.current.handleDisableTotp("totp-1")
    expect(openStepUpFor).toHaveBeenCalledOnce()
    await act(async () => {
      await action?.()
    })
    expect(mocks.deleteTotpEnrollment).toHaveBeenCalledWith("totp-1")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.snackbar.totpDisabled",
      severity: "success",
    })

    mocks.deleteTotpEnrollment.mockRejectedValueOnce({ status: 400, message: "Disable failed" })
    result.current.handleDisableTotp("totp-1")
    await act(async () => {
      await action?.()
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "Disable failed", severity: "error" })

    mocks.deleteTotpEnrollment.mockResolvedValueOnce(undefined)
    result.current.handleDisableTotp("totp-1")
    await act(async () => {
      await action?.()
    })
    const updateUser = mocks.setUser.mock.calls.find(
      ([value]) => typeof value === "function"
    )?.[0] as ((previous: typeof mocks.user | null) => unknown) | undefined
    expect(updateUser?.(mocks.user)).toMatchObject({
      mfa_default_method: null,
      mfa_required: false,
    })
    expect(updateUser?.(null)).toBeNull()
  })
})
