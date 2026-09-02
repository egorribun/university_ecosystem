import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { AxiosError } from "axios"

import { useLoginForm, useMfaFlow } from "./useLoginFlow"
import { ChallengeLockedError } from "@/types/Auth"
import type { PendingMfaState } from "@/types/Auth"

// ---------------------------------------------------------------------------
// Module mocks — auth API + router. No real network.
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => ({
  login: vi.fn((..._a: unknown[]) => Promise.resolve(null as PendingMfaState | null)),
  submitMfaChallenge: vi.fn((..._a: unknown[]) => Promise.resolve()),
  resendEmailMfaChallenge: vi.fn(),
  pendingMfa: null as PendingMfaState | null,
  navigate: vi.fn(),
  routerSearch: {} as Record<string, unknown>,
  routerState: null as unknown,
  suggestEmailDomain: vi.fn((v: string) => v),
}))

vi.mock("@/contexts/AuthContext", async () => {
  const { ChallengeLockedError: RealChallengeLockedError } =
    await vi.importActual<typeof import("@/types/Auth")>("@/types/Auth")
  return {
    useAuth: () => ({
      login: mocks.login,
      submitMfaChallenge: mocks.submitMfaChallenge,
      pendingMfa: mocks.pendingMfa,
    }),
    ChallengeLockedError: RealChallengeLockedError,
  }
})

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useRouterState: ({ select }: { select: (s: unknown) => unknown }) =>
    select({ location: { search: mocks.routerSearch, state: mocks.routerState } }),
}))

vi.mock("@/api/mfa", () => ({
  resendEmailMfaChallenge: mocks.resendEmailMfaChallenge,
}))

vi.mock("@/utils/authUtils", () => ({
  suggestEmailDomain: mocks.suggestEmailDomain,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.login.mockResolvedValue(null)
  mocks.submitMfaChallenge.mockResolvedValue(undefined)
  mocks.resendEmailMfaChallenge.mockResolvedValue({
    method: "email_otp",
    challenge_token: "ct-email-rotated",
    challenge_expires_at: "2026-08-25T16:00:00Z",
    resend_available_at: "2026-08-25T15:51:00Z",
  })
  mocks.pendingMfa = null
  mocks.routerSearch = {}
  mocks.routerState = null
  mocks.suggestEmailDomain.mockImplementation((v: string) => v)
  try {
    window.localStorage.clear()
  } catch {
    /* ignore */
  }
})

const mfaLogin = (resendAvailableAt = "2020-01-01T00:00:00Z"): PendingMfaState => ({
  status: "mfa_required",
  user_id: "u-1",
  reason: "login",
  methods: [
    {
      method: "totp",
      challenge_token: "ct-totp",
    } as PendingMfaState["methods"][number],
    {
      method: "email_otp",
      challenge_token: "ct-email",
      challenge_expires_at: "2026-08-25T16:00:00Z",
      delivery_hint: "u***@example.com",
      resend_available_at: resendAvailableAt,
    } as PendingMfaState["methods"][number],
  ],
})

// ---------------------------------------------------------------------------
// useLoginForm.onSubmit — lines 121-146
// ---------------------------------------------------------------------------

describe("useLoginForm.onSubmit", () => {
  it("redirects to resolved path on a successful login (line 134)", async () => {
    mocks.routerSearch = { redirect: "/events" }
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
      result.current.form.setValue("password", "Password123!")
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    expect(mocks.login).toHaveBeenCalledWith("a@b.dev", "Password123!", false)
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/events", replace: true })
  })

  it("remembers the email without requesting trusted-device MFA bypass", async () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "remember@me.dev")
      result.current.form.setValue("password", "Password123!")
      ;(result.current.form.setValue as (name: string, value: boolean) => void)(
        "rememberEmail",
        true
      )
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    expect(mocks.login).toHaveBeenCalledWith("remember@me.dev", "Password123!", false)
    await waitFor(() =>
      expect(window.localStorage.getItem("auth:lastEmail")).toContain("remember@me.dev")
    )
  })

  it("trusts the device only for the current login and does not remember the email", async () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "private@shared.dev")
      result.current.form.setValue("password", "Password123!")
      result.current.form.setValue("trustDevice", true)
    })

    await act(async () => {
      await result.current.onSubmit()
    })

    expect(mocks.login).toHaveBeenCalledWith("private@shared.dev", "Password123!", true)
    expect(JSON.parse(window.localStorage.getItem("auth:lastEmail") ?? "null")).toBe("")
  })

  it("does not hydrate trusted-device consent from legacy localStorage", () => {
    window.localStorage.setItem("auth:trustDevice", JSON.stringify("1"))

    const { result } = renderHook(() => useLoginForm())

    expect(result.current.form.getValues("trustDevice")).toBe(false)
  })

  it("returns early (no navigate) when login surfaces a challenge (lines 130-132)", async () => {
    mocks.login.mockResolvedValue(mfaLogin())
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
      result.current.form.setValue("password", "Password123!")
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it("surfaces an Error.message as the root server error (lines 135-144)", async () => {
    mocks.login.mockRejectedValue(new Error("Account locked"))
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
      result.current.form.setValue("password", "Password123!")
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    await waitFor(() => expect(result.current.submitError).toBe("Account locked"))
  })

  it("prefers axios response.data.detail for the root error (line 140-142)", async () => {
    const err = new AxiosError("bad")
    err.response = {
      status: 400,
      headers: {},
      data: { detail: "Invalid credentials" },
      statusText: "",
      config: {} as never,
    }
    mocks.login.mockRejectedValue(err)
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
      result.current.form.setValue("password", "Password123!")
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    await waitFor(() => expect(result.current.submitError).toBe("Invalid credentials"))
  })

  it("keeps the translated fallback when login rejects with a non-Error value", async () => {
    mocks.login.mockRejectedValue("authentication unavailable")
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
      result.current.form.setValue("password", "Password123!")
    })

    await act(async () => {
      await result.current.onSubmit()
    })

    await waitFor(() => expect(result.current.submitError).toBe("auth:login.error"))
  })
})

// ---------------------------------------------------------------------------
// useLoginForm.applySuggestion — lines 157-161
// ---------------------------------------------------------------------------

describe("useLoginForm suggestion", () => {
  it("applySuggestion writes the suggestion + clears the banner (lines 158-160)", async () => {
    mocks.suggestEmailDomain.mockReturnValue("user@gmail.com")
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "user@gmial.com")
    })
    await act(async () => {
      await result.current.handleEmailBlur()
    })
    expect(result.current.emailSuggestion).toBe("user@gmail.com")
    act(() => {
      result.current.applySuggestion()
    })
    expect(result.current.emailSuggestion).toBeNull()
    expect(result.current.form.getValues("email")).toBe("user@gmail.com")
  })

  it("applySuggestion is a no-op when there is no suggestion (line 158 guard)", () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.applySuggestion()
    })
    expect(result.current.emailSuggestion).toBeNull()
  })

  it("does not ask for a domain suggestion when the trimmed email is empty", async () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "   ")
    })

    await act(async () => {
      await result.current.handleEmailBlur()
    })

    expect(mocks.suggestEmailDomain).not.toHaveBeenCalled()
    expect(result.current.emailSuggestion).toBeNull()
  })

  it("clears the suggestion when the helper returns the same email", async () => {
    mocks.suggestEmailDomain.mockReturnValue("same@example.com")
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "same@example.com")
    })

    await act(async () => {
      await result.current.handleEmailBlur()
    })

    expect(mocks.suggestEmailDomain).toHaveBeenCalledWith("same@example.com")
    expect(result.current.emailSuggestion).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// useMfaFlow.handleRecoveryVerify — lines 356-395
// ---------------------------------------------------------------------------

describe("useMfaFlow.handleRecoveryVerify", () => {
  it("surfaces a general expired error when the login challenge is absent", async () => {
    mocks.pendingMfa = null
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("RECOVERY")
    })

    expect(result.current.mfaError).toBe("auth:mfa.errors.expired")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(mocks.submitMfaChallenge).not.toHaveBeenCalled()
  })

  it("submits a recovery code and redirects on success", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.routerState = { from: { pathname: "/secure" } }
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("RECOVERY-123")
    })

    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith({
      method: "recovery_code",
      code: "RECOVERY-123",
      challengeToken: "ct-totp",
    })
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/secure", replace: true })
    expect(result.current.mfaBusy).toBe(false)
  })

  it("routes a locked recovery challenge to the general banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new ChallengeLockedError("Recovery locked"))
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("LOCKED")
    })

    expect(result.current.mfaError).toBe("Recovery locked")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("keeps a generic recovery error in the general banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new Error("Invalid recovery code"))
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("BAD")
    })

    expect(result.current.mfaError).toBe("Invalid recovery code")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("prefers Axios detail for a recovery error", async () => {
    mocks.pendingMfa = mfaLogin()
    const err = new AxiosError("bad")
    err.response = {
      status: 400,
      headers: {},
      data: { detail: "Recovery code rejected" },
      statusText: "",
      config: {} as never,
    }
    mocks.submitMfaChallenge.mockRejectedValue(err)
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("BAD")
    })

    expect(result.current.mfaError).toBe("Recovery code rejected")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("keeps the translated fallback when recovery verification rejects with a non-Error", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue("recovery unavailable")
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("BAD")
    })

    expect(result.current.mfaError).toBe("auth:mfa.errors.generic")
    expect(result.current.mfaErrorSource).toBe("general")
  })
})

// ---------------------------------------------------------------------------
// useMfaFlow.handleOtpVerify — lines 269-309
// ---------------------------------------------------------------------------

describe("useMfaFlow.handleOtpVerify", () => {
  it("surfaces a general 'expired' error when there is no challenge (lines 271-275)", async () => {
    mocks.pendingMfa = null
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("123456")
    })
    expect(result.current.mfaError).toBe("auth:mfa.errors.expired")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(mocks.submitMfaChallenge).not.toHaveBeenCalled()
  })

  it("verifies the otp challenge then redirects (lines 277-288)", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.routerState = { from: { pathname: "/secure" } }
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("654321")
    })
    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "totp",
        code: "654321",
        challengeToken: "ct-totp",
      })
    )
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/secure", replace: true })
    expect(result.current.mfaBusy).toBe(false)
  })

  it("routes a ChallengeLockedError to the general banner (lines 290-292)", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new ChallengeLockedError("Locked out"))
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("000000")
    })
    expect(result.current.mfaError).toBe("Locked out")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("keeps non-locked totp errors in the per-input source (lines 293-303)", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new Error("Bad code"))
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("999999")
    })
    expect(result.current.mfaError).toBe("Bad code")
    expect(result.current.mfaErrorSource).toBe("totp")
  })

  it("prefers axios detail for a totp error", async () => {
    mocks.pendingMfa = mfaLogin()
    const err = new AxiosError("bad")
    err.response = {
      status: 400,
      headers: {},
      data: { detail: "Code expired" },
      statusText: "",
      config: {} as never,
    }
    mocks.submitMfaChallenge.mockRejectedValue(err)
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("111111")
    })
    expect(result.current.mfaError).toBe("Code expired")
    expect(result.current.mfaErrorSource).toBe("totp")
  })

  it("keeps the translated fallback when OTP verification rejects with a non-Error", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue("otp unavailable")
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleOtpVerify("111111")
    })

    expect(result.current.mfaError).toBe("auth:mfa.errors.generic")
    expect(result.current.mfaErrorSource).toBe("totp")
  })
})

// ---------------------------------------------------------------------------
// useMfaFlow email OTP verify + resend
// ---------------------------------------------------------------------------

describe("useMfaFlow email OTP", () => {
  it("surfaces a general expired error when the email challenge is absent", async () => {
    mocks.pendingMfa = null
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleEmailOtpVerify("123456")
    })
    expect(result.current.mfaError).toBe("auth:mfa.errors.expired")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(mocks.submitMfaChallenge).not.toHaveBeenCalled()
  })

  it("submits the email method with the current rotated token", async () => {
    mocks.pendingMfa = mfaLogin()
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleResendEmailOtp()
    })
    await waitFor(() =>
      expect(result.current.emailChallenge?.challenge_token).toBe("ct-email-rotated")
    )
    await act(async () => {
      await result.current.handleEmailOtpVerify("654321")
    })
    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith({
      method: "email_otp",
      code: "654321",
      challengeToken: "ct-email-rotated",
    })
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/dashboard", replace: true })
  })

  it("atomically replaces the challenge after resend", async () => {
    mocks.pendingMfa = mfaLogin()
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleResendEmailOtp()
    })
    expect(mocks.resendEmailMfaChallenge).toHaveBeenCalledWith("ct-email")
    expect(result.current.emailChallenge?.challenge_token).toBe("ct-email-rotated")
  })

  it("keeps resend errors in the general live banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.resendEmailMfaChallenge.mockRejectedValue(new Error("Cooldown active"))
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleResendEmailOtp()
    })
    expect(result.current.mfaError).toBe("Cooldown active")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("counts down a future resend window and cancels its timer on unmount", () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date("2026-08-25T15:50:00Z"))
      mocks.pendingMfa = mfaLogin("2026-08-25T15:50:02Z")
      const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
      const { result, unmount } = renderHook(() => useMfaFlow())

      expect(result.current.resendSeconds).toBe(2)
      act(() => vi.advanceTimersByTime(1000))
      expect(result.current.resendSeconds).toBe(1)

      unmount()
      expect(clearTimeoutSpy).toHaveBeenCalled()
      clearTimeoutSpy.mockRestore()
    } finally {
      vi.useRealTimers()
    }
  })

  it("does not resend before the server cooldown expires", async () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date("2026-08-25T15:50:00Z"))
      mocks.pendingMfa = mfaLogin("2026-08-25T15:51:00Z")
      const { result } = renderHook(() => useMfaFlow())

      await act(() => result.current.handleResendEmailOtp())

      expect(result.current.resendSeconds).toBe(60)
      expect(mocks.resendEmailMfaChallenge).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps a regular email-code error beside the email input", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValueOnce(new Error("Invalid email code"))
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleEmailOtpVerify("000000"))

    expect(result.current.mfaError).toBe("Invalid email code")
    expect(result.current.mfaErrorSource).toBe("email_otp")
    expect(result.current.mfaBusy).toBe(false)
  })

  it("prefers the API detail for an email-code error", async () => {
    mocks.pendingMfa = mfaLogin()
    const error = new AxiosError("bad")
    error.response = {
      status: 400,
      headers: {},
      data: { detail: "Email code expired" },
      statusText: "",
      config: {} as never,
    }
    mocks.submitMfaChallenge.mockRejectedValueOnce(error)
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleEmailOtpVerify("000000"))

    expect(result.current.mfaError).toBe("Email code expired")
    expect(result.current.mfaErrorSource).toBe("email_otp")
  })

  it("routes a locked email-code challenge to the general banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValueOnce(new ChallengeLockedError("Email MFA locked"))
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleEmailOtpVerify("000000"))

    expect(result.current.mfaError).toBe("Email MFA locked")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(result.current.generalMfaError).toBe("Email MFA locked")
  })

  it("uses the translated fallback for a non-Error email-code rejection", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValueOnce("email verification unavailable")
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleEmailOtpVerify("000000"))

    expect(result.current.mfaError).toBe("auth:mfa.errors.generic")
    expect(result.current.mfaErrorSource).toBe("email_otp")
  })

  it("prefers the API detail when resend is rejected", async () => {
    mocks.pendingMfa = mfaLogin()
    const error = new AxiosError("bad")
    error.response = {
      status: 429,
      headers: {},
      data: { detail: "Resend cooldown active" },
      statusText: "",
      config: {} as never,
    }
    mocks.resendEmailMfaChallenge.mockRejectedValueOnce(error)
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleResendEmailOtp())

    expect(result.current.mfaError).toBe("Resend cooldown active")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("uses the translated fallback for a non-Error resend rejection", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.resendEmailMfaChallenge.mockRejectedValueOnce("resend unavailable")
    const { result } = renderHook(() => useMfaFlow())

    await act(() => result.current.handleResendEmailOtp())

    expect(result.current.mfaError).toBe("auth:mfa.errors.generic")
    expect(result.current.mfaErrorSource).toBe("general")
  })
})
