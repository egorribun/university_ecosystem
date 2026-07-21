import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { useEmailChange } from "../useEmailChange"

const mocks = vi.hoisted(() => ({
  user: { id: "user-1", email: "current@example.test", pending_email: null as string | null },
  setUser: vi.fn(),
  post: vi.fn(),
  fetchQuery: vi.fn(),
  fetchCurrentUser: vi.fn(),
  t: (key: string, options?: { email?: string }) =>
    options?.email === undefined ? key : `${key}:${options.email}`,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ fetchQuery: mocks.fetchQuery }),
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

describe("useEmailChange", () => {
  beforeEach(() => {
    mocks.user = { id: "user-1", email: "current@example.test", pending_email: null }
    mocks.post.mockReset()
    mocks.fetchQuery.mockReset()
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
      password: "current-password",
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

  it("does not submit an address that already awaits confirmation", async () => {
    mocks.user = { ...mocks.user, pending_email: "pending@example.test" }
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
})
