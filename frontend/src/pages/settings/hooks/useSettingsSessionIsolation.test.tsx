import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider, onlineManager } from "@tanstack/react-query"
import type { ChangeEvent, FocusEvent, PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { User } from "@/types/User"
import { rotateBrowserSession } from "@/stores/sessionEpoch"
import { useDndSettings } from "./useDndSettings"
import { useAvatarUpload } from "./useAvatarUpload"
import { useCoverUpload } from "./useCoverUpload"
import { useEmailChange } from "./useEmailChange"
import { useEmailMfa } from "./useEmailMfa"
import { useTotpEnrollment } from "./useTotpEnrollment"

const mocks = vi.hoisted(() => ({
  user: null as User | null,
  loading: false,
  setUser: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  fetchCurrentUser: vi.fn(),
  startEmailMfaEnablement: vi.fn(),
  startEmailVerification: vi.fn(),
  verifyMfaChallenge: vi.fn(),
  resendEmailMfaChallenge: vi.fn(),
  disableEmailMfa: vi.fn(),
  startTotpEnrollment: vi.fn(),
  confirmTotpEnrollment: vi.fn(),
  deleteTotpEnrollment: vi.fn(),
  deletePendingTotpEnrollment: vi.fn(),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, loading: mocks.loading, setUser: mocks.setUser }),
}))
vi.mock("@/api/client", () => ({
  default: { put: mocks.put, post: mocks.post, delete: mocks.delete },
}))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: mocks.fetchCurrentUser,
}))
vi.mock("@/api/mfa", () => ({
  startEmailMfaEnablement: mocks.startEmailMfaEnablement,
  startEmailVerification: mocks.startEmailVerification,
  verifyMfaChallenge: mocks.verifyMfaChallenge,
  resendEmailMfaChallenge: mocks.resendEmailMfaChallenge,
  disableEmailMfa: mocks.disableEmailMfa,
  startTotpEnrollment: mocks.startTotpEnrollment,
  confirmTotpEnrollment: mocks.confirmTotpEnrollment,
  deleteTotpEnrollment: mocks.deleteTotpEnrollment,
  deletePendingTotpEnrollment: mocks.deletePendingTotpEnrollment,
}))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
const account = (id: string) =>
  ({
    id,
    full_name: id,
    email: `${id}@example.test`,
    role: "student",
    preferences: { dnd_enabled: false },
    totp_enrollments: [],
  }) as unknown as User
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const setSnackbar = vi.fn()
  const openStepUpFor = vi.fn()
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const hook = renderHook(
    () => ({
      dnd: useDndSettings(setSnackbar),
      avatar: useAvatarUpload(setSnackbar),
      cover: useCoverUpload(setSnackbar),
      email: useEmailChange({ setSnackbar, openStepUpFor }),
      emailMfa: useEmailMfa({ setSnackbar, openStepUpFor }),
      totp: useTotpEnrollment({ setSnackbar, openStepUpFor }),
    }),
    { wrapper }
  )
  return { ...hook, queryClient, setSnackbar, openStepUpFor }
}
beforeEach(() => {
  vi.resetAllMocks()
  rotateBrowserSession()
  mocks.user = account("account-a")
  mocks.loading = false
  mocks.setUser.mockImplementation((next: User | ((previous: User | null) => User | null)) => {
    mocks.user = typeof next === "function" ? next(mocks.user) : next
  })
  mocks.fetchCurrentUser.mockResolvedValue(account("account-a"))
  mocks.post.mockResolvedValue({ data: {} })
  mocks.delete.mockResolvedValue({ data: {} })
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:profile-preview")
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
})

type SettingsHook = ReturnType<typeof renderSettings>
type AsyncAction =
  | "avatar"
  | "cover"
  | "email"
  | "emailStart"
  | "emailConfirm"
  | "emailResend"
  | "emailDisable"
  | "totpStart"
  | "totpConfirm"
  | "totpCancel"
  | "totpDisable"
const challenge = {
  method: "email_otp",
  challenge_token: "account-a-challenge",
  challenge_expires_at: "2026-11-01T00:00:00Z",
}
async function prepareAction(kind: AsyncAction, hook: SettingsHook) {
  const { result, openStepUpFor, setSnackbar } = hook
  if (kind === "avatar" || kind === "cover") {
    return {
      request: mocks.post,
      run: () =>
        result.current[kind].upload(new File(["image"], "profile.png", { type: "image/png" })),
    }
  }
  if (kind === "email") {
    act(() => {
      result.current.email.setEmailValue("next@example.test")
      result.current.email.setEmailPassword("current-password")
    })
    return { request: mocks.post, run: () => result.current.email.handleEmailSubmit() }
  }
  if (kind === "emailStart")
    return {
      request: mocks.startEmailVerification,
      run: () => result.current.emailMfa.handleStartEmailMfa(),
    }
  if (kind === "emailConfirm" || kind === "emailResend") {
    mocks.startEmailVerification.mockResolvedValue(challenge)
    await act(() => result.current.emailMfa.handleStartEmailMfa())
    return kind === "emailConfirm"
      ? {
          request: mocks.verifyMfaChallenge,
          run: () => result.current.emailMfa.handleConfirmEmailMfa("123456"),
        }
      : {
          request: mocks.resendEmailMfaChallenge,
          run: () => result.current.emailMfa.handleResendEmailMfa(),
        }
  }
  if (kind === "emailDisable") {
    act(() => result.current.emailMfa.handleDisableEmailMfa())
    return {
      request: mocks.disableEmailMfa,
      run: openStepUpFor.mock.calls[0]![0] as () => Promise<void>,
    }
  }
  if (kind === "totpStart")
    return { request: mocks.startTotpEnrollment, run: () => result.current.totp.handleStartTotp() }
  if (kind === "totpDisable") {
    act(() => result.current.totp.handleDisableTotp("enrollment-a"))
    return {
      request: mocks.deleteTotpEnrollment,
      run: openStepUpFor.mock.calls[0]![0] as () => Promise<void>,
    }
  }
  mocks.startTotpEnrollment.mockResolvedValue({
    enrollment: { id: "enrollment-a", user_id: "account-a" },
    secret: crypto.randomUUID(),
    otpauth_url: "otpauth://totp/test",
  })
  await act(() => result.current.totp.handleStartTotp())
  setSnackbar.mockClear()
  return kind === "totpConfirm"
    ? {
        request: mocks.confirmTotpEnrollment,
        run: () => result.current.totp.handleConfirmTotp("123456"),
      }
    : {
        request: mocks.deletePendingTotpEnrollment,
        run: () => result.current.totp.handleCancelTotp(),
      }
}

describe("settings session isolation", () => {
  it.each(["logout", "switch"] as const)(
    "drops a delayed DND profile response after %s",
    async (transition) => {
      const pending = deferred<{ data: User }>()
      mocks.put.mockReturnValue(pending.promise)
      const { result, rerender, setSnackbar } = renderSettings()
      act(() => result.current.dnd.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true))
      rotateBrowserSession()
      const nextUser = transition === "switch" ? account("account-b") : null
      mocks.user = nextUser
      rerender()
      await act(async () => {
        pending.resolve({ data: account("account-a") })
        await pending.promise
      })
      expect(mocks.user).toBe(nextUser)
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
      expect(result.current.dnd.dndSaving).toBe(false)
      expect(result.current.dnd.dndEnabled).toBe(false)
    }
  )

  it("does not roll back account B's DND draft or show account A's delayed failure", async () => {
    const pending = deferred<never>()
    mocks.put.mockReturnValue(pending.promise)
    const { result, rerender, setSnackbar } = renderSettings()
    act(() => result.current.dnd.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true))
    rotateBrowserSession()
    mocks.user = {
      ...account("account-b"),
      preferences: { dnd_enabled: true, dnd_start: "19:00:00", dnd_end: "05:00:00" },
    } as User
    rerender()
    await act(async () => {
      pending.reject(new Error("A failed"))
      await pending.promise.catch(() => {})
    })
    expect(result.current.dnd.dndStart).toBe("19:00")
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it.each(["avatar", "cover", "email", "emailMfa", "totp"] as const)(
    "does not adopt or cache %s's delayed profile refresh after account switch",
    async (kind) => {
      const pending = deferred<User>()
      mocks.fetchCurrentUser.mockReturnValue(pending.promise)
      const { result, rerender, setSnackbar, openStepUpFor, queryClient } = renderSettings()
      let operation!: Promise<void>
      if (kind === "email") {
        act(() => {
          result.current.email.setEmailValue("next@example.test")
          result.current.email.setEmailPassword("password")
        })
        act(() => {
          operation = result.current.email.handleEmailSubmit()
        })
      } else if (kind === "emailMfa") {
        act(() => result.current.emailMfa.handleDisableEmailMfa())
        act(() => {
          operation = openStepUpFor.mock.calls[0]![0]()
        })
      } else if (kind === "totp") {
        act(() => result.current.totp.handleDisableTotp("enrollment-a"))
        act(() => {
          operation = openStepUpFor.mock.calls[0]![0]()
        })
      } else {
        act(() => {
          operation = result.current[kind].remove()
        })
      }
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalled())
      mocks.setUser.mockClear()
      rotateBrowserSession()
      const nextUser = account("account-b")
      mocks.user = nextUser
      rerender()
      await act(async () => {
        pending.resolve(account("account-a"))
        await operation
      })
      expect(mocks.user).toBe(nextUser)
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(["users", "me"])).toBeUndefined()
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )

  it.each(["emailMfa", "totp"] as const)(
    "does not replay %s step-up action for a different account",
    async (kind) => {
      const { result, rerender, openStepUpFor } = renderSettings()
      act(() => {
        if (kind === "emailMfa") result.current.emailMfa.handleDisableEmailMfa()
        else result.current.totp.handleDisableTotp("enrollment-a")
      })
      rotateBrowserSession()
      mocks.user = account("account-b")
      rerender()
      await act(async () => {
        await openStepUpFor.mock.calls[0]![0]()
      })
      expect(mocks.disableEmailMfa).not.toHaveBeenCalled()
      expect(mocks.deleteTotpEnrollment).not.toHaveBeenCalled()
    }
  )
  it.each(["same account login", "unmount", "other tab"] as const)(
    "drops an obsolete response after %s",
    async (transition) => {
      const pending = deferred<{ data: User }>()
      mocks.put.mockReturnValue(pending.promise)
      const { result, unmount, setSnackbar } = renderSettings()
      act(() => result.current.dnd.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true))
      if (transition === "unmount") unmount()
      else if (transition === "same account login") rotateBrowserSession()
      else
        localStorage.setItem(
          "ecosystem.session.generation.v1",
          JSON.stringify({ nonce: "remote-session", hash: null })
        )
      await act(async () => {
        pending.resolve({ data: account("account-a") })
        await pending.promise
      })
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )

  it("issues no writes from a tab whose origin session has already changed", async () => {
    const { result } = renderSettings()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "remote-session", hash: null })
    )
    await act(async () => {
      result.current.dnd.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await result.current.avatar.remove()
      await result.current.cover.remove()
      await result.current.totp.handleStartTotp()
      await result.current.emailMfa.handleStartEmailMfa()
    })
    expect(mocks.put).not.toHaveBeenCalled()
    expect(mocks.delete).not.toHaveBeenCalled()
    expect(mocks.startTotpEnrollment).not.toHaveBeenCalled()
    expect(mocks.startEmailVerification).not.toHaveBeenCalled()
  })

  it.each(["avatar", "cover"] as const)(
    "does not start %s profile refresh after a stale write completes",
    async (kind) => {
      const pending = deferred<unknown>()
      mocks.delete.mockReturnValue(pending.promise)
      const { result, rerender, setSnackbar } = renderSettings()
      let operation!: Promise<void>
      act(() => {
        operation = result.current[kind].remove()
      })
      rotateBrowserSession()
      mocks.user = account("account-b")
      rerender()
      await act(async () => {
        pending.resolve({})
        await operation
      })
      expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
      expect(result.current[kind].busy).toBe(false)
    }
  )

  it("rejects a profile refresh for a different identity before caching it", async () => {
    mocks.fetchCurrentUser.mockResolvedValue(account("account-b"))
    const { result, queryClient, setSnackbar } = renderSettings()
    await act(() => result.current.avatar.remove())
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(queryClient.getQueryData(["users", "me"])).toBeUndefined()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:media.avatar.deleteFailed",
      severity: "error",
    })
  })

  it("discards the previous account's secret-bearing enrollment response", async () => {
    const pending = deferred<unknown>()
    mocks.startTotpEnrollment.mockReturnValue(pending.promise)
    const { result, rerender } = renderSettings()
    let operation!: Promise<void>
    act(() => {
      operation = result.current.totp.handleStartTotp()
    })
    rotateBrowserSession()
    mocks.user = account("account-b")
    rerender()
    await act(async () => {
      pending.resolve({ secret: crypto.randomUUID(), enrollment: { id: "enrollment-a" } })
      await operation
    })
    expect(result.current.totp.totpDraft).toBeNull()
    expect(result.current.totp.totpBusy).toBe(false)
  })
  it("preserves an authenticated step-up action across its temporary auth loading state", async () => {
    const { result, rerender, openStepUpFor, setSnackbar } = renderSettings()
    act(() => result.current.emailMfa.handleDisableEmailMfa())
    mocks.loading = true
    rerender()
    mocks.loading = false
    rerender()
    await act(() => openStepUpFor.mock.calls[0]![0]())
    expect(mocks.disableEmailMfa).toHaveBeenCalledOnce()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.snackbar.emailMfaDisabled",
      severity: "success",
    })
  })
  it.each(
    (
      [
        "avatar",
        "cover",
        "email",
        "emailStart",
        "emailConfirm",
        "emailResend",
        "emailDisable",
        "totpStart",
        "totpConfirm",
        "totpCancel",
        "totpDisable",
      ] as const
    ).flatMap((kind) => (["success", "failure"] as const).map((outcome) => ({ kind, outcome })))
  )("suppresses stale $kind $outcome after account replacement", async ({ kind, outcome }) => {
    const hook = renderSettings()
    const action = await prepareAction(kind, hook)
    const pending = deferred<unknown>()
    action.request.mockReturnValueOnce(pending.promise)
    let operation!: Promise<void>
    act(() => {
      operation = action.run()
    })
    expect(action.request).toHaveBeenCalled()
    rotateBrowserSession()
    const nextUser = account("account-b")
    mocks.user = nextUser
    hook.rerender()
    await act(async () => {
      if (outcome === "success") pending.resolve({ data: account("account-a") })
      else pending.reject(new Error("Account A failed"))
      await operation
    })
    expect(mocks.user).toBe(nextUser)
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
    expect(hook.setSnackbar).not.toHaveBeenCalled()
    expect(hook.result.current.email.pendingEmail).toBeNull()
    expect(hook.result.current.email.emailError).toBeNull()
    expect(hook.result.current.emailMfa.emailChallenge).toBeNull()
    expect(hook.result.current.emailMfa.emailMfaError).toBeNull()
    expect(hook.result.current.emailMfa.emailMfaBusy).toBe(false)
    expect(hook.result.current.totp.totpDraft).toBeNull()
    expect(hook.result.current.totp.totpError).toBeNull()
    expect(hook.result.current.totp.totpBusy).toBe(false)
  })

  it.each(["avatar", "cover"] as const)(
    "does not dispatch a %s upload from an obsolete tab",
    async (kind) => {
      const hook = renderSettings()
      const action = await prepareAction(kind, hook)
      localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({ nonce: "other-tab", hash: null })
      )
      await act(action.run)
      expect(mocks.post).not.toHaveBeenCalled()
      expect(URL.createObjectURL).not.toHaveBeenCalled()
      expect(hook.result.current[kind].busy).toBe(false)
    }
  )

  it("does not open account security step-up for an obsolete tab", () => {
    const { result, openStepUpFor } = renderSettings()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "other-tab", hash: null })
    )
    act(() => {
      result.current.emailMfa.handleDisableEmailMfa()
      result.current.totp.handleDisableTotp("enrollment-a")
    })
    expect(openStepUpFor).not.toHaveBeenCalled()
  })

  it.each(["email", "emailStart", "totpStart"] as const)(
    "does not replay %s after a delayed step-up loses ownership",
    async (kind) => {
      const hook = renderSettings()
      const action = await prepareAction(kind, hook)
      action.request.mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 428, data: { detail: "Step-up required" } },
      })
      await act(action.run)
      expect(hook.openStepUpFor).toHaveBeenCalledOnce()
      rotateBrowserSession()
      mocks.user = account("account-b")
      hook.rerender()
      await act(() => hook.openStepUpFor.mock.calls[0]![0]())
      expect(action.request).toHaveBeenCalledOnce()
    }
  )

  it.each(["totpConfirm", "totpCancel", "totpDisable"] as const)(
    "stops %s completion when a profile observer replaces its session",
    async (kind) => {
      const hook = renderSettings()
      const action = await prepareAction(kind, hook)
      action.request.mockResolvedValueOnce(undefined)
      const nextUser = account("account-b")
      mocks.setUser.mockImplementation(() => {
        rotateBrowserSession()
        mocks.user = nextUser
      })
      await act(action.run)
      expect(mocks.setUser).toHaveBeenCalledOnce()
      expect(mocks.user).toBe(nextUser)
      expect(hook.setSnackbar).not.toHaveBeenCalled()
    }
  )

  it("rejects a paused profile refresh before dispatch after account replacement", async () => {
    const hook = renderSettings()
    onlineManager.setOnline(false)
    let operation!: Promise<void>
    try {
      act(() => {
        operation = hook.result.current.avatar.remove()
      })
      await waitFor(() =>
        expect(hook.queryClient.getQueryState(["users", "me"])?.fetchStatus).toBe("paused")
      )
      rotateBrowserSession()
      mocks.user = account("account-b")
      hook.rerender()
      await act(async () => {
        onlineManager.setOnline(true)
        await operation
      })
      expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(hook.setSnackbar).not.toHaveBeenCalled()
    } finally {
      onlineManager.setOnline(true)
    }
  })

  it("rechecks DND ownership if another tab changes the session while input is read", () => {
    mocks.user = {
      ...account("account-a"),
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    } as User
    const { result } = renderSettings()
    const input = {
      get value() {
        localStorage.setItem(
          "ecosystem.session.generation.v1",
          JSON.stringify({ nonce: "other-tab", hash: null })
        )
        return "20:00"
      },
    }
    act(() =>
      result.current.dnd.handleDndStartBlur({
        currentTarget: input,
      } as FocusEvent<HTMLInputElement>)
    )
    expect(mocks.put).not.toHaveBeenCalled()
    expect(result.current.dnd.dndSaving).toBe(false)
  })
})
