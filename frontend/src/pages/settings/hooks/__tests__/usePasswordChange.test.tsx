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

  it("reports a missing confirmation and keeps the confirm message visible", async () => {
    const { result } = renderPasswordChange()
    act(() => {
      result.current.setCurrentPasswordValue("old-password")
      result.current.setNewPasswordValue("new-password")
    })

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.passwordError).toBe("settings:security.password.errors.confirmRequired")
    expect(result.current.confirmPasswordMessage).toBe(
      "settings:security.password.errors.confirmRequired"
    )
  })

  it("marks the new-required error as a new-password error", async () => {
    const { result } = renderPasswordChange()
    act(() => result.current.setCurrentPasswordValue("old-password"))

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.passwordError).toBe("settings:security.password.errors.newRequired")
    expect(result.current.isNewPasswordError).toBe(true)
    expect(result.current.confirmPasswordMessage).toBeNull()
  })

  it("updates the password, clears fields, and refreshes session data", async () => {
    mocks.post.mockResolvedValue({ data: { ok: true, revoked_sessions: 2 } })
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(mocks.post).toHaveBeenCalledWith("/users/me/password", {
      current_password: "old-password", // pragma: allowlist secret
      new_password: "new-password", // pragma: allowlist secret
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

  it("clears fields and refreshes sessions even when the API reports ok=false", async () => {
    mocks.post.mockResolvedValue({ data: { ok: false, revoked_sessions: 0 } })
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(setSnackbar).not.toHaveBeenCalled()
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: sessionsQueryKey })
    expect(result.current.currentPasswordValue).toBe("")
  })

  it("uses zero as the revoked-session count when the success payload omits it", async () => {
    mocks.post.mockResolvedValue({ data: { ok: true } })
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.password.updated:0",
      severity: "success",
    })
  })

  it("delegates a required step-up challenge without showing a generic error", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    const error = new AxiosError("step up required")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.post.mockRejectedValueOnce(error).mockResolvedValueOnce({
      data: { ok: true, revoked_sessions: 1 },
    })
    const { result, setSnackbar } = renderPasswordChange(openStepUpFor)
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()

    await act(async () => {
      await retry?.()
    })
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.password.updated:1",
      severity: "success",
    })
  })

  it("falls back to the generic error when step-up is unavailable", async () => {
    const error = new AxiosError("step up required")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.post.mockRejectedValue(error)
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

  it("does not reopen step-up when a retry explicitly skips it", async () => {
    const error = new AxiosError("step up required")
    error.response = { status: 428 } as AxiosError["response"]
    const openStepUpFor = vi.fn()
    mocks.post.mockRejectedValue(error)
    const { result } = renderPasswordChange(openStepUpFor)
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit({ skipStepUp: true })
    })

    expect(openStepUpFor).not.toHaveBeenCalled()
    expect(result.current.passwordError).toBe("settings:security.password.failed")
  })

  it("handles classified Axios details without a generic snackbar", async () => {
    const currentInvalid = new AxiosError("bad current")
    currentInvalid.response = {
      status: 400,
      data: { detail: "settings:security.password.errors.currentInvalid" },
    } as AxiosError["response"]
    const samePassword = new AxiosError("same")
    samePassword.response = {
      status: 400,
      data: { detail: "settings:security.password.errors.same" },
    } as AxiosError["response"]
    const genericDetail = new AxiosError("generic")
    genericDetail.response = {
      status: 400,
      data: { detail: "Server rejected password" },
    } as AxiosError["response"]
    mocks.post
      .mockRejectedValueOnce(currentInvalid)
      .mockRejectedValueOnce(samePassword)
      .mockRejectedValueOnce(genericDetail)
    const { result, setSnackbar } = renderPasswordChange()

    setValidPasswords(result)
    await act(async () => {
      await result.current.handlePasswordSubmit()
    })
    expect(result.current.currentPasswordError).toBe(
      "settings:security.password.errors.currentInvalid"
    )
    expect(setSnackbar).not.toHaveBeenCalled()

    setValidPasswords(result)
    await act(async () => {
      await result.current.handlePasswordSubmit()
    })
    expect(result.current.passwordError).toBe("settings:security.password.errors.same")
    expect(result.current.isNewPasswordError).toBe(true)
    expect(result.current.confirmPasswordMessage).toBeNull()

    setValidPasswords(result)
    await act(async () => {
      await result.current.handlePasswordSubmit()
    })
    expect(result.current.passwordError).toBe("Server rejected password")
    expect(result.current.confirmPasswordMessage).toBe("Server rejected password")
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("joins validation-array details and reports the combined error", async () => {
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      data: { detail: [{ msg: "Too short" }, { ignored: true }, { msg: "Too common" }] },
    } as AxiosError["response"]
    mocks.post.mockRejectedValue(error)
    const { result, setSnackbar } = renderPasswordChange()
    setValidPasswords(result)

    await act(async () => {
      await result.current.handlePasswordSubmit()
    })

    expect(result.current.passwordError).toBe("Too short; Too common")
    expect(setSnackbar).toHaveBeenCalledWith({ text: "Too short; Too common", severity: "error" })
  })

  it("ignores a second submit while the first request is still busy", async () => {
    let resolvePost!: (value: unknown) => void
    mocks.post.mockReturnValue(new Promise((resolve) => (resolvePost = resolve)))
    const { result } = renderPasswordChange()
    setValidPasswords(result)

    let firstSubmit!: Promise<void>
    act(() => {
      firstSubmit = result.current.handlePasswordSubmit()
    })
    await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1))
    await act(async () => {
      await result.current.handlePasswordSubmit()
    })
    expect(mocks.post).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolvePost({ data: { ok: false, revoked_sessions: 0 } })
      await firstSubmit
    })
    expect(result.current.passwordBusy).toBe(false)
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

  it("falls back when an Axios validation array contains no messages", async () => {
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      data: { detail: [null, { code: "ignored" }] },
    } as AxiosError["response"]
    mocks.post.mockRejectedValue(error)
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
