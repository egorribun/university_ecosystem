import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook, waitFor } from "@testing-library/react"
import { useEmailChange } from "../useEmailChange"

const mocks = vi.hoisted(() => ({
  user: null as {
    id: string
    email: string
    pending_email: string | null
  } | null,
  setUser: vi.fn(),
  post: vi.fn(),
  cancelQueries: vi.fn(),
  fetchQuery: vi.fn(),
  fetchCurrentUser: vi.fn(),
  t: (key: string, options?: { email?: string }) =>
    options?.email === undefined ? key : `${key}:${options.email}`,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    cancelQueries: mocks.cancelQueries,
    fetchQuery: mocks.fetchQuery,
  }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))
vi.mock("@/api/client", () => ({ default: { post: mocks.post } }))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: mocks.fetchCurrentUser,
}))

const renderEmailChange = (openStepUpFor?: (action: () => Promise<void>) => void) => {
  const setSnackbar = vi.fn()
  const hook = renderHook(() => useEmailChange({ setSnackbar, openStepUpFor }))
  return { ...hook, setSnackbar }
}

const setCredentials = (
  result: ReturnType<typeof renderEmailChange>["result"],
  email = "next@example.test"
) => {
  act(() => {
    result.current.setEmailValue(email)
    result.current.setEmailPassword("current-password")
  })
}

const axiosError = (status: number, detail?: unknown) => {
  const error = new AxiosError("request failed")
  error.response = {
    status,
    data: detail === undefined ? undefined : { detail },
  } as AxiosError["response"]
  return error
}

describe("useEmailChange", () => {
  beforeEach(() => {
    mocks.user = {
      id: "user-1",
      email: "current@example.test",
      pending_email: null,
    }
    mocks.post.mockReset()
    mocks.fetchQuery.mockReset()
    mocks.cancelQueries.mockReset()
    mocks.cancelQueries.mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockReset()
    mocks.setUser.mockReset()
  })

  it("validates both an unchanged email and missing password without a network request", async () => {
    const { result } = renderEmailChange()

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(result.current.emailError).toBe("settings:security.email.noChange")
    expect(result.current.emailPasswordError).toBe(
      "settings:security.email.errors.passwordRequired"
    )
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("requires an email even when the password is present", async () => {
    const { result } = renderEmailChange()
    setCredentials(result, "   ")

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(result.current.emailError).toBe("settings:security.email.errors.required")
    expect(result.current.emailPasswordError).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("handles a missing user context without leaking email state", () => {
    mocks.user = null
    const { result } = renderEmailChange()

    expect(result.current.emailValue).toBe("")
    expect(result.current.pendingEmail).toBeNull()
  })

  it("suppresses a concurrent submit while the first request is busy", async () => {
    let resolvePost: (() => void) | undefined
    mocks.post.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvePost = resolve
        })
    )
    const { result } = renderEmailChange()
    setCredentials(result)

    let firstSubmit: Promise<void> | undefined
    act(() => {
      firstSubmit = result.current.handleEmailSubmit()
    })
    await waitFor(() => expect(result.current.emailBusy).toBe(true))

    await act(async () => {
      await result.current.handleEmailSubmit()
    })
    expect(mocks.post).toHaveBeenCalledOnce()

    await act(async () => {
      resolvePost?.()
      await firstSubmit
    })
    expect(result.current.emailBusy).toBe(false)
  })

  it("submits a new address, refreshes the profile, and stores its pending state", async () => {
    mocks.post.mockResolvedValue({ data: {} })
    const freshUser = {
      id: "user-1",
      email: "current@example.test",
      pending_email: "next@example.test",
    }
    mocks.fetchQuery.mockResolvedValue(freshUser)
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(mocks.post).toHaveBeenCalledWith("/users/me/email", {
      email: "next@example.test",
      password: "current-password", // pragma: allowlist secret
    })
    expect(mocks.fetchQuery).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["users", "me"], staleTime: 0 })
    )
    expect(mocks.setUser).toHaveBeenCalledWith(freshUser)
    expect(result.current.pendingEmail).toBe("next@example.test")
    expect(result.current.emailPassword).toBe("")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.email.confirmationSent:next@example.test",
      severity: "success",
    })
  })

  it("reports a committed email request separately when the profile refresh fails", async () => {
    mocks.post.mockResolvedValue({ data: {} })
    mocks.fetchQuery.mockRejectedValueOnce(new Error("profile refresh failed"))
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(mocks.post).toHaveBeenCalledOnce()
    expect(mocks.fetchQuery).toHaveBeenCalledOnce()
    expect(result.current.pendingEmail).toBe("next@example.test")
    expect(result.current.emailPassword).toBe("")
    expect(result.current.emailError).toBeNull()
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.email.confirmationSentRefreshFailed:next@example.test",
      severity: "warning",
    })
    expect(setSnackbar).not.toHaveBeenCalledWith({
      text: "settings:security.email.failed",
      severity: "error",
    })
  })

  it("warns when an accepted email request has no refreshed profile", async () => {
    mocks.post.mockResolvedValue({ data: {} })
    mocks.fetchQuery.mockResolvedValueOnce(null)
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(mocks.post).toHaveBeenCalledOnce()
    expect(result.current.pendingEmail).toBe("next@example.test")
    expect(result.current.emailPassword).toBe("")
    expect(result.current.emailError).toBeNull()
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.email.confirmationSentRefreshFailed:next@example.test",
      severity: "warning",
    })
  })

  it("suppresses an old account's refresh result after the email request commits", async () => {
    type ProfileSnapshot = {
      id: string
      email: string
      pending_email: string | null
    }
    let resolveRefresh!: (profile: ProfileSnapshot) => void
    const pendingRefresh = new Promise<ProfileSnapshot>((resolve) => {
      resolveRefresh = resolve
    })
    mocks.post.mockResolvedValue({ data: {} })
    mocks.fetchQuery.mockReturnValueOnce(pendingRefresh)
    const { result, rerender, setSnackbar } = renderEmailChange()
    setCredentials(result)
    let operation!: Promise<void>

    act(() => {
      operation = result.current.handleEmailSubmit()
    })
    await waitFor(() => expect(mocks.fetchQuery).toHaveBeenCalledOnce())

    mocks.user = {
      id: "user-2",
      email: "other@example.test",
      pending_email: null,
    }
    rerender()
    await waitFor(() => expect(result.current.pendingEmail).toBeNull())
    expect(result.current.emailValue).toBe("other@example.test")

    await act(async () => {
      resolveRefresh({
        id: "user-1",
        email: "current@example.test",
        pending_email: "next@example.test",
      })
      await operation
    })

    expect(mocks.post).toHaveBeenCalledOnce()
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("suppresses a rejected old-account email refresh after switching accounts", async () => {
    let rejectRefresh!: (reason?: unknown) => void
    mocks.post.mockResolvedValue({ data: {} })
    mocks.fetchQuery.mockReturnValueOnce(
      new Promise<never>((_, reject) => {
        rejectRefresh = reject
      })
    )
    const { result, rerender, setSnackbar } = renderEmailChange()
    setCredentials(result)
    let operation!: Promise<void>

    act(() => {
      operation = result.current.handleEmailSubmit()
    })
    await waitFor(() => expect(mocks.fetchQuery).toHaveBeenCalledOnce())

    mocks.user = {
      id: "user-2",
      email: "other@example.test",
      pending_email: null,
    }
    rerender()
    await act(async () => {
      rejectRefresh(new Error("old account profile refresh failed"))
      await operation
    })

    expect(mocks.post).toHaveBeenCalledOnce()
    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("does not refresh the profile after the email mutation itself fails", async () => {
    mocks.post.mockRejectedValueOnce(new Error("email request failed"))
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(mocks.post).toHaveBeenCalledOnce()
    expect(mocks.fetchQuery).not.toHaveBeenCalled()
    expect(result.current.pendingEmail).toBeNull()
    expect(result.current.emailError).toBe("settings:security.email.failed")
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.email.failed",
      severity: "error",
    })
  })
  it("does not submit an address that already awaits confirmation", async () => {
    mocks.user = {
      id: "user-1",
      email: "current@example.test",
      pending_email: "pending@example.test",
    }
    const { result } = renderEmailChange()
    setCredentials(result, "PENDING@example.test")

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(result.current.emailError).toBe(
      "settings:security.email.pendingSame:pending@example.test"
    )
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("delegates a 428 response to the step-up flow", async () => {
    const openStepUpFor = vi.fn()
    const error = new AxiosError("step up required")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.post.mockRejectedValue(error)
    const { result, setSnackbar } = renderEmailChange(openStepUpFor)
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("retries through step-up and completes the request", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    mocks.post.mockRejectedValueOnce(axiosError(428)).mockResolvedValueOnce({ data: {} })
    mocks.fetchQuery.mockResolvedValue({
      id: "user-1",
      email: "current@example.test",
      pending_email: "next@example.test",
    })
    const { result, setSnackbar } = renderEmailChange(openStepUpFor)
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })
    await act(async () => {
      await retry?.()
    })

    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.email.confirmationSent:next@example.test",
      severity: "success",
    })
  })

  it("classifies invalid-password and other string details without a snackbar", async () => {
    mocks.post.mockRejectedValueOnce(
      axiosError(400, "settings:security.email.errors.invalidPassword")
    )
    const first = renderEmailChange()
    setCredentials(first.result)

    await act(async () => {
      await first.result.current.handleEmailSubmit()
    })
    expect(first.result.current.emailPasswordError).toBe(
      "settings:security.email.errors.invalidPassword"
    )
    expect(first.result.current.emailError).toBeNull()
    expect(first.setSnackbar).not.toHaveBeenCalled()

    mocks.post.mockRejectedValueOnce(axiosError(400, "Address rejected"))
    const second = renderEmailChange()
    setCredentials(second.result)
    await act(async () => {
      await second.result.current.handleEmailSubmit()
    })
    expect(second.result.current.emailError).toBe("Address rejected")
    expect(second.setSnackbar).not.toHaveBeenCalled()
  })

  it("combines validation-array details and falls back for 428 without step-up", async () => {
    mocks.post.mockRejectedValueOnce(
      axiosError(400, [{ msg: "first" }, { msg: "second" }, null, { code: "ignored" }])
    )
    const arrayCase = renderEmailChange()
    setCredentials(arrayCase.result)

    await act(async () => {
      await arrayCase.result.current.handleEmailSubmit()
    })
    expect(arrayCase.result.current.emailError).toBe("first; second")
    expect(arrayCase.setSnackbar).toHaveBeenCalledWith({
      text: "first; second",
      severity: "error",
    })

    mocks.post.mockRejectedValueOnce(axiosError(428))
    const fallbackCase = renderEmailChange()
    setCredentials(fallbackCase.result)
    await act(async () => {
      await fallbackCase.result.current.handleEmailSubmit({ skipStepUp: true })
    })
    expect(fallbackCase.result.current.emailError).toBe("settings:security.email.failed")
    expect(fallbackCase.setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.email.failed",
      severity: "error",
    })
  })

  it("shows a fallback error when the request cannot be classified", async () => {
    mocks.post.mockRejectedValue(new Error("offline"))
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(result.current.emailError).toBe("settings:security.email.failed")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.email.failed",
      severity: "error",
    })
  })

  it("falls back when an Axios validation array contains no messages", async () => {
    mocks.post.mockRejectedValue(axiosError(422, [null, { code: "ignored" }]))
    const { result, setSnackbar } = renderEmailChange()
    setCredentials(result)

    await act(async () => {
      await result.current.handleEmailSubmit()
    })

    expect(result.current.emailError).toBe("settings:security.email.failed")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.email.failed",
      severity: "error",
    })
  })
})
