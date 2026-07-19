import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { usePasswordChange } from "../usePasswordChange"

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  invalidateQueries: vi.fn(),
  t: (key: string, options?: { count?: number }) =>
    options?.count === undefined ? key : `${key}:${options.count}`,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))
vi.mock("@/api/client", () => ({ default: { post: mocks.post } }))

const sessionsQueryKey = ["sessions"] as const

const renderPasswordChange = (openStepUpFor?: (action: () => Promise<void>) => void) => {
  const setSnackbar = vi.fn()
  const hook = renderHook(() => usePasswordChange({ setSnackbar, sessionsQueryKey, openStepUpFor }))
  return { ...hook, setSnackbar }
}

const setValidPasswords = (result: ReturnType<typeof renderPasswordChange>["result"]) => {
  act(() => {
    result.current.setCurrentPasswordValue("old-password")
    result.current.setNewPasswordValue("new-password")
    result.current.setConfirmPasswordValue("new-password")
  })
}

describe("usePasswordChange", () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.invalidateQueries.mockReset().mockResolvedValue(undefined)
  })

  it("reports missing current and new passwords before it calls the API", async () => {
    const { result } = renderPasswordChange()

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.currentPasswordError).toBe(
      "settings:security.password.errors.currentRequired"
    )
    expect(result.current.passwordError).toBe("settings:security.password.errors.newRequired")
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("rejects mismatched confirmation locally", async () => {
    const { result } = renderPasswordChange()
    act(() => {
      result.current.setCurrentPasswordValue("old-password")
      result.current.setNewPasswordValue("new-password")
      result.current.setConfirmPasswordValue("different-password")
    })

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.passwordError).toBe("settings:security.password.errors.mismatch")
    expect(result.current.confirmPasswordMessage).toBe("settings:security.password.errors.mismatch")
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("updates the password, clears fields, and refreshes session data", async () => {
    mocks.post.mockResolvedValue({ data: { ok: true, revoked_sessions: 2 } })
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(mocks.post).toHaveBeenCalledWith("/users/me/password", {
      current_password: "old-password",
      new_password: "new-password",
    })
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: sessionsQueryKey })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.password.updated:2",
      severity: "success",
    })
    expect(result.current.currentPasswordValue).toBe("")
    expect(result.current.newPasswordValue).toBe("")
    expect(result.current.confirmPasswordValue).toBe("")
  })

  it("delegates a required step-up challenge without showing a generic error", async () => {
    const openStepUpFor = vi.fn()
    const error = new AxiosError("step up required")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.post.mockRejectedValue(error)
    const { result, setSnackbar } = renderPasswordChange(openStepUpFor)
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("shows a fallback error and snackbar for an unclassified API failure", async () => {
    mocks.post.mockRejectedValue(new Error("offline"))
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.passwordError).toBe("settings:security.password.failed")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.password.failed",
      severity: "error",
    })
  })
})
