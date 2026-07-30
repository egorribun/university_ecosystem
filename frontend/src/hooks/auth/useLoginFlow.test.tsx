import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { AxiosError } from "axios"

import { useLoginForm, useMfaFlow } from "./useLoginFlow"
import { ChallengeLockedError } from "@/types/Auth"
import type { PendingMfaState } from "@/types/Auth"

// ---------------------------------------------------------------------------
// Module mocks — auth api + router + WebAuthn. No real network.
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => ({
  login: vi.fn((..._a: unknown[]) => Promise.resolve(null as PendingMfaState | null)),
  loginWithPasskey: vi.fn((..._a: unknown[]) => Promise.resolve()),
  submitMfaChallenge: vi.fn((..._a: unknown[]) => Promise.resolve()),
  pendingMfa: null as PendingMfaState | null,
  navigate: vi.fn(),
  routerSearch: {} as Record<string, unknown>,
  routerState: null as unknown,
  startAuthentication: vi.fn(async () => ({ id: "assertion" })),
  browserSupportsWebAuthn: vi.fn(() => true),
  suggestEmailDomain: vi.fn((v: string) => v),
}))

vi.mock("@/contexts/AuthContext", async () => {
  const { ChallengeLockedError: RealChallengeLockedError } =
    await vi.importActual<typeof import("@/types/Auth")>("@/types/Auth")
  return {
    useAuth: () => ({
      login: mocks.login,
      loginWithPasskey: mocks.loginWithPasskey,
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

vi.mock("@simplewebauthn/browser", () => ({
  startAuthentication: mocks.startAuthentication,
  browserSupportsWebAuthn: mocks.browserSupportsWebAuthn,
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
  mocks.loginWithPasskey.mockResolvedValue(undefined)
  mocks.submitMfaChallenge.mockResolvedValue(undefined)
  mocks.pendingMfa = null
  mocks.routerSearch = {}
  mocks.routerState = null
  mocks.startAuthentication.mockResolvedValue({ id: "assertion" })
  mocks.browserSupportsWebAuthn.mockReturnValue(true)
  mocks.suggestEmailDomain.mockImplementation((v: string) => v)
  try {
    window.localStorage.clear()
  } catch {
    /* ignore */
  }
})

const mfaLogin = (): PendingMfaState => ({
  status: "mfa_required",
  user_id: "u-1",
  reason: "login",
  methods: [
    {
      method: "totp",
      challenge_token: "ct-totp",
    } as PendingMfaState["methods"][number],
    {
      method: "webauthn",
      challenge_token: "ct-wa",
      options: { challenge: "x" },
    } as unknown as PendingMfaState["methods"][number],
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

  it("persists savedEmail when trustDevice is on (lines 126-128)", async () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "trust@me.dev")
      result.current.form.setValue("password", "Password123!")
      result.current.form.setValue("trustDevice", true)
    })
    await act(async () => {
      await result.current.onSubmit()
    })
    expect(mocks.login).toHaveBeenCalledWith("trust@me.dev", "Password123!", true)
    await waitFor(() =>
      expect(window.localStorage.getItem("auth:lastEmail")).toContain("trust@me.dev")
    )
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
})

// ---------------------------------------------------------------------------
// useLoginForm.applySuggestion — lines 157-161
// ---------------------------------------------------------------------------

describe("useLoginForm suggestion + trustDevice setter", () => {
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

  it("setTrustDevice updates the form value (lines 188-190)", () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.setTrustDevice(true)
    })
    expect(result.current.trustDevice).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// useLoginForm.handlePasskeyLogin — lines 163-182
// ---------------------------------------------------------------------------

describe("useLoginForm.handlePasskeyLogin", () => {
  it("stops before WebAuthn when the email field already has a validation error", async () => {
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setError("email", { type: "manual", message: "Required" })
    })
    await waitFor(() => expect(result.current.form.formState.errors.email).toBeTruthy())

    await act(async () => {
      await result.current.handlePasskeyLogin()
    })

    expect(mocks.loginWithPasskey).not.toHaveBeenCalled()
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it("logs in with passkey then redirects (lines 170-173)", async () => {
    mocks.routerSearch = { redirect: "/dashboard" }
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
    })
    await act(async () => {
      await result.current.handlePasskeyLogin()
    })
    expect(mocks.loginWithPasskey).toHaveBeenCalledWith("a@b.dev", false)
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/dashboard", replace: true })
  })

  it("surfaces a passkey error from an Error instance (lines 174-180)", async () => {
    mocks.loginWithPasskey.mockRejectedValue(new Error("biometric cancelled"))
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
    })
    await act(async () => {
      await result.current.handlePasskeyLogin()
    })
    await waitFor(() => expect(result.current.passkeyError).toBe("biometric cancelled"))
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it("prefers axios detail for the passkey error (lines 177-179)", async () => {
    const err = new AxiosError("bad")
    err.response = {
      status: 400,
      headers: {},
      data: { detail: "No passkey registered" },
      statusText: "",
      config: {} as never,
    }
    mocks.loginWithPasskey.mockRejectedValue(err)
    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "a@b.dev")
    })
    await act(async () => {
      await result.current.handlePasskeyLogin()
    })
    await waitFor(() => expect(result.current.passkeyError).toBe("No passkey registered"))
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
      await result.current.handleRecoveryVerify("RECOVERY", false)
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
      await result.current.handleRecoveryVerify("RECOVERY-123", true)
    })

    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith({
      method: "recovery_code",
      code: "RECOVERY-123",
      challengeToken: "ct-totp",
      trustDevice: true,
    })
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/secure", replace: true })
    expect(result.current.mfaBusy).toBe(false)
  })

  it("routes a locked recovery challenge to the general banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new ChallengeLockedError("Recovery locked"))
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("LOCKED", false)
    })

    expect(result.current.mfaError).toBe("Recovery locked")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("keeps a generic recovery error in the general banner", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new Error("Invalid recovery code"))
    const { result } = renderHook(() => useMfaFlow())

    await act(async () => {
      await result.current.handleRecoveryVerify("BAD", false)
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
      await result.current.handleRecoveryVerify("BAD", false)
    })

    expect(result.current.mfaError).toBe("Recovery code rejected")
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
      await result.current.handleOtpVerify("123456", false)
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
      await result.current.handleOtpVerify("654321", true)
    })
    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "totp",
        code: "654321",
        challengeToken: "ct-totp",
        trustDevice: true,
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
      await result.current.handleOtpVerify("000000", false)
    })
    expect(result.current.mfaError).toBe("Locked out")
    expect(result.current.mfaErrorSource).toBe("general")
  })

  it("keeps non-locked totp errors in the per-input source (lines 293-303)", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.submitMfaChallenge.mockRejectedValue(new Error("Bad code"))
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleOtpVerify("999999", false)
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
      await result.current.handleOtpVerify("111111", false)
    })
    expect(result.current.mfaError).toBe("Code expired")
    expect(result.current.mfaErrorSource).toBe("totp")
  })
})

// ---------------------------------------------------------------------------
// useMfaFlow.handleWebAuthnVerify — lines 311-352
// ---------------------------------------------------------------------------

describe("useMfaFlow.handleWebAuthnVerify", () => {
  it("surfaces a general 'expired' error when challenge/options absent (lines 313-317)", async () => {
    mocks.pendingMfa = null
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleWebAuthnVerify(false)
    })
    expect(result.current.mfaError).toBe("auth:mfa.errors.expired")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(mocks.startAuthentication).not.toHaveBeenCalled()
  })

  it("runs startAuthentication + submits then redirects (lines 319-336)", async () => {
    mocks.pendingMfa = mfaLogin()
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleWebAuthnVerify(true)
    })
    expect(mocks.startAuthentication).toHaveBeenCalled()
    expect(mocks.submitMfaChallenge).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "webauthn",
        challengeToken: "ct-wa",
        trustDevice: true,
      })
    )
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/dashboard", replace: true })
    expect(result.current.mfaBusy).toBe(false)
  })

  it("surfaces a webauthn error to the general banner (lines 337-346)", async () => {
    mocks.pendingMfa = mfaLogin()
    mocks.startAuthentication.mockRejectedValue(new Error("user cancelled"))
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleWebAuthnVerify(false)
    })
    expect(result.current.mfaError).toBe("user cancelled")
    expect(result.current.mfaErrorSource).toBe("general")
    expect(result.current.generalMfaError).toBe("user cancelled")
  })

  it("prefers axios detail for a webauthn error (lines 342-344)", async () => {
    mocks.pendingMfa = mfaLogin()
    const err = new AxiosError("bad")
    err.response = {
      status: 400,
      headers: {},
      data: { detail: "Assertion rejected" },
      statusText: "",
      config: {} as never,
    }
    mocks.submitMfaChallenge.mockRejectedValue(err)
    const { result } = renderHook(() => useMfaFlow())
    await act(async () => {
      await result.current.handleWebAuthnVerify(false)
    })
    expect(result.current.mfaError).toBe("Assertion rejected")
    expect(result.current.mfaErrorSource).toBe("general")
  })
})
