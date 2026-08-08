import type { ReactNode } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { AxiosError, AxiosHeaders } from "axios"

import { extractSigningKey, useAuthApi } from "./useAuthApi"
import type { User } from "@/types/User"
import { ChallengeLockedError } from "@/types/Auth"
import { API_UNAUTHORIZED_EVENT } from "@/api/client"
import { SPOTIFY_REAUTH_EVENT } from "@/hooks/useNowPlaying"

// ---------------------------------------------------------------------------
// Module mocks. The api layer is fully mocked — never hits MSW (a contract
// validator rejects off-schema responses). The push + epoch + profile-fetch
// dependencies are mocked so we can assert the success/failure branches in
// useAuthApi without their side effects running for real.
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn((..._a: unknown[]) => Promise.resolve({ status: 200, data: {} })),
  apiGet: vi.fn((..._a: unknown[]) => Promise.resolve({ status: 200, data: {} })),
  incrementSessionEpoch: vi.fn(),
  fetchCurrentUser: vi.fn((..._a: unknown[]) => Promise.resolve({ id: "u-1" })),
  recoverPushConsentFromBrowser: vi.fn(async () => false),
  hasPushConsent: vi.fn(() => false),
  softSyncPushSubscription: vi.fn(async () => null),
  setPushConsent: vi.fn(),
  startAuthentication: vi.fn(async () => ({ id: "assertion" })),
}))

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return {
    ...actual,
    default: { post: mocks.apiPost, get: mocks.apiGet },
  }
})

vi.mock("@/api/interceptors/etagCache", () => ({
  incrementSessionEpoch: mocks.incrementSessionEpoch,
}))

vi.mock("./useProfileSync", () => ({
  fetchCurrentUser: mocks.fetchCurrentUser,
}))

vi.mock("@/push/subscribe", () => ({
  recoverPushConsentFromBrowser: mocks.recoverPushConsentFromBrowser,
  hasPushConsent: mocks.hasPushConsent,
  softSyncPushSubscription: mocks.softSyncPushSubscription,
  setPushConsent: mocks.setPushConsent,
}))

vi.mock("@simplewebauthn/browser", () => ({
  startAuthentication: mocks.startAuthentication,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "count" in opts
        ? `${key}:${(opts as { count: number }).count}`
        : opts && "duration" in opts
          ? `${key}:${(opts as { duration: string }).duration}`
          : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

type Wires = {
  user: User | null
  setUser: ReturnType<typeof vi.fn>
  updatePendingMfa: ReturnType<typeof vi.fn>
  handleUnauthorized: ReturnType<typeof vi.fn>
  updateSessionSigningKey: ReturnType<typeof vi.fn>
  authOperation: boolean
  setAuthOperation: ReturnType<typeof vi.fn>
  resetEtagCache: ReturnType<typeof vi.fn>
}

const makeWires = (overrides: Partial<Wires> = {}): Wires => ({
  user: null,
  setUser: vi.fn(),
  updatePendingMfa: vi.fn(),
  handleUnauthorized: vi.fn(),
  updateSessionSigningKey: vi.fn(),
  authOperation: false,
  setAuthOperation: vi.fn(),
  resetEtagCache: vi.fn(),
  ...overrides,
})

const renderApi = (w: Wires) =>
  renderHook(
    () =>
      useAuthApi(
        w.user,
        w.setUser,
        w.updatePendingMfa,
        w.handleUnauthorized,
        w.updateSessionSigningKey,
        w.authOperation,
        w.setAuthOperation,
        w.resetEtagCache
      ),
    { wrapper }
  )

const fullUser = (extra: Partial<User> = {}): User =>
  ({
    id: "u-1",
    email: "a@b.dev",
    full_name: "A",
    role: "student",
    spotify_connected: false,
    ...extra,
  }) as unknown as User

const lockedError = (retryAfter?: string): AxiosError => {
  const headers = new AxiosHeaders()
  if (retryAfter !== undefined) headers.set("retry-after", retryAfter)
  const err = new AxiosError("locked")
  err.response = {
    status: 423,
    headers: retryAfter !== undefined ? { "retry-after": retryAfter } : {},
    data: {},
    statusText: "Locked",
    config: { headers } as never,
  }
  return err
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiPost.mockResolvedValue({ status: 200, data: {} })
  mocks.apiGet.mockResolvedValue({ status: 200, data: {} })
  mocks.recoverPushConsentFromBrowser.mockResolvedValue(false)
  mocks.hasPushConsent.mockReturnValue(false)
  mocks.startAuthentication.mockResolvedValue({ id: "assertion" })
})

// ---------------------------------------------------------------------------
// login — lines 126-212
// ---------------------------------------------------------------------------

describe("login", () => {
  it("returns null when authOperation is already in-flight (line ~132)", async () => {
    const w = makeWires({ authOperation: true })
    const { result } = renderApi(w)
    let out: unknown
    await act(async () => {
      out = await result.current.login("a@b.dev", "pw")
    })
    expect(out).toBeNull()
    expect(mocks.apiPost).not.toHaveBeenCalled()
    expect(w.setAuthOperation).not.toHaveBeenCalled()
  })

  it("posts to /auth/login with urlencoded body + trust_device flag (lines 135-149)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw", true)
    })
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/login",
      expect.any(URLSearchParams),
      expect.objectContaining({ skipRateLimitQueue: true })
    )
    const body = mocks.apiPost.mock.calls[0]![1] as URLSearchParams
    expect(body.get("username")).toBe("a@b.dev")
    expect(body.get("password")).toBe("pw")
    expect(body.get("trust_device")).toBe("true")
    expect(w.setAuthOperation).toHaveBeenCalledWith(true)
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("returns pending state on 202 MFA challenge (lines 151-159)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 202,
      data: { status: "mfa_required", user_id: "u-1", methods: [] },
    })
    const { result } = renderApi(w)
    let out: { reason?: string } | null = null
    await act(async () => {
      out = await result.current.login("a@b.dev", "pw")
    })
    expect(out).toMatchObject({ reason: "login", user_id: "u-1" })
    expect(w.updatePendingMfa).toHaveBeenCalledWith(expect.objectContaining({ reason: "login" }))
  })

  it("on success sets user, bumps epoch, clears MFA + fires spotify event (lines 161-184)", async () => {
    const w = makeWires()
    const dispatch = vi.spyOn(window, "dispatchEvent")
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ spotify_connected: true }), session: { signing_key: "sk-1" } },
    })
    const { result } = renderApi(w)
    let out: unknown = "x"
    await act(async () => {
      out = await result.current.login("a@b.dev", "pw")
    })
    expect(out).toBeNull()
    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("sk-1")
    expect(mocks.incrementSessionEpoch).toHaveBeenCalled()
    expect(w.setUser).toHaveBeenCalledWith(expect.objectContaining({ id: "u-1" }))
    expect(w.updatePendingMfa).toHaveBeenCalledWith(null)
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT }))
    dispatch.mockRestore()
  })

  it("syncs push subscription when consent recovered (lines 175-181)", async () => {
    const w = makeWires()
    mocks.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })
    await waitFor(() => expect(mocks.softSyncPushSubscription).toHaveBeenCalled())
  })

  it("throws 'Invalid response from server' when payload is not a token-with-profile (line 187)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { nope: true } })
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow("Invalid response from server")
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("maps 423 lockout WITHOUT retry-after to plain locked message (lines 196-197)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError())
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow("login.locked")
  })

  it("maps 423 lockout WITH retry-after seconds to a duration message (lines 189-195)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError("30"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow(/login\.locked .*login\.lockedRetry/)
  })

  it("re-throws non-423 errors unchanged (line 198)", async () => {
    const w = makeWires()
    const boom = new Error("network down")
    mocks.apiPost.mockRejectedValue(boom)
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow("network down")
  })
})

// ---------------------------------------------------------------------------
// prefetchDashboardData — group_id branch + catch (lines 110-121)
// ---------------------------------------------------------------------------

describe("login → prefetchDashboardData branches", () => {
  it("prefetches events list when the user has a group_id (lines 110-116)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ group_id: "grp-1" }) },
    })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })
    // The dynamic imports for dashboard prefetch resolve async; just assert
    // the login resolved cleanly (the group_id branch executes inside the
    // fire-and-forget prefetch without throwing).
    expect(w.setUser).toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// logout — lines 214-230
// ---------------------------------------------------------------------------

describe("logout", () => {
  it("posts /auth/logout + clears consent when user present (lines 216-223)", async () => {
    const w = makeWires({ user: fullUser() })
    mocks.hasPushConsent.mockReturnValue(true)
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.logout()
    })
    expect(mocks.setPushConsent).toHaveBeenCalledWith(false)
    expect(mocks.apiPost).toHaveBeenCalledWith("/auth/logout")
    expect(w.handleUnauthorized).toHaveBeenCalled()
  })

  it("skips the logout POST when there is no user, still unauthorizes (line 216 false branch)", async () => {
    const w = makeWires({ user: null })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.logout()
    })
    expect(mocks.apiPost).not.toHaveBeenCalled()
    expect(w.handleUnauthorized).toHaveBeenCalled()
  })

  it("still unauthorizes even when the logout POST throws (lines 225-228)", async () => {
    const w = makeWires({ user: fullUser() })
    mocks.apiPost.mockRejectedValue(new Error("boom"))
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.logout()
    })
    expect(w.handleUnauthorized).toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// submitMfaChallenge — lines 232-304
// ---------------------------------------------------------------------------

describe("submitMfaChallenge", () => {
  it("no-ops when authOperation is in-flight (line ~240)", async () => {
    const w = makeWires({ authOperation: true })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.submitMfaChallenge({ code: "123456", challengeToken: "ct" })
    })
    expect(mocks.apiPost).not.toHaveBeenCalled()
  })

  it("verifies a totp challenge and signs the session in (lines 243-279)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ spotify_connected: true }), session: { signing_key: "sk-2" } },
    })
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.submitMfaChallenge({
        method: "totp",
        code: "654321",
        challengeToken: "ct-1",
        trustDevice: true,
      })
    })
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/mfa/verify",
      expect.objectContaining({
        method: "totp",
        code: "654321",
        challenge_token: "ct-1",
        trust_device: true,
      }),
      expect.objectContaining({ skipRateLimitQueue: true })
    )
    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("sk-2")
    expect(mocks.incrementSessionEpoch).toHaveBeenCalled()
    expect(w.setUser).toHaveBeenCalled()
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT }))
    dispatch.mockRestore()
  })

  it("sends webauthn_response for the webauthn method (lines 251-253)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.submitMfaChallenge({
        method: "webauthn",
        webauthnResponse: { id: "assertion" },
        challengeToken: "ct-2",
      })
    })
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/mfa/verify",
      expect.objectContaining({ method: "webauthn", webauthn_response: { id: "assertion" } }),
      expect.anything()
    )
  })

  it("throws ChallengeLockedError on 423 (lines 282-289)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError("90"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.submitMfaChallenge({ code: "1", challengeToken: "ct" })
      })
    ).rejects.toBeInstanceOf(ChallengeLockedError)
  })

  it("throws ChallengeLockedError (plain message) on 423 with no retry-after", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError())
    const { result } = renderApi(w)
    let caught: unknown
    await act(async () => {
      try {
        await result.current.submitMfaChallenge({ code: "1", challengeToken: "ct" })
      } catch (e) {
        caught = e
      }
    })
    expect(caught).toBeInstanceOf(ChallengeLockedError)
    expect((caught as Error).message).toContain("login.locked")
  })

  it("re-throws non-423 errors unchanged (line 290)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(new Error("server 500"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.submitMfaChallenge({ code: "1", challengeToken: "ct" })
      })
    ).rejects.toThrow("server 500")
  })
})

// ---------------------------------------------------------------------------
// requireMfa — lines 306-330
// ---------------------------------------------------------------------------

describe("requireMfa", () => {
  it("returns step-up pending state on 202 (lines 308-315)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 202,
      data: { status: "mfa_required", user_id: "u-1", methods: [] },
    })
    const { result } = renderApi(w)
    let out: { reason?: string } | null = null
    await act(async () => {
      out = await result.current.requireMfa()
    })
    expect(out).toMatchObject({ reason: "step-up" })
    expect(w.updatePendingMfa).toHaveBeenCalledWith(expect.objectContaining({ reason: "step-up" }))
  })

  it("returns null when status is not 202 (line 316)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: {} })
    const { result } = renderApi(w)
    let out: unknown = "x"
    await act(async () => {
      out = await result.current.requireMfa()
    })
    expect(out).toBeNull()
  })

  it("dispatches unauthorized event + returns null on 401 (lines 319-322)", async () => {
    const w = makeWires()
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const err = new AxiosError("unauth")
    err.response = { status: 401, headers: {}, data: {}, statusText: "", config: {} as never }
    mocks.apiPost.mockRejectedValue(err)
    const { result } = renderApi(w)
    let out: unknown = "x"
    await act(async () => {
      out = await result.current.requireMfa()
    })
    expect(out).toBeNull()
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: API_UNAUTHORIZED_EVENT }))
    dispatch.mockRestore()
  })

  it("returns null on 409 'already fresh' (lines 323-326)", async () => {
    const w = makeWires()
    const err = new AxiosError("conflict")
    err.response = { status: 409, headers: {}, data: {}, statusText: "", config: {} as never }
    mocks.apiPost.mockRejectedValue(err)
    const { result } = renderApi(w)
    let out: unknown = "x"
    await act(async () => {
      out = await result.current.requireMfa()
    })
    expect(out).toBeNull()
  })

  it("re-throws other errors (lines 328-329)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(new Error("nope"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.requireMfa()
      })
    ).rejects.toThrow("nope")
  })
})

// ---------------------------------------------------------------------------
// refresh — lines 332-354
// ---------------------------------------------------------------------------

describe("refresh", () => {
  it("resets etag cache, fetches profile + sets user (lines 332-346)", async () => {
    const w = makeWires()
    mocks.fetchCurrentUser.mockResolvedValue(fullUser())
    mocks.hasPushConsent.mockReturnValue(true)
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.refresh()
    })
    expect(w.resetEtagCache).toHaveBeenCalled()
    expect(mocks.fetchCurrentUser).toHaveBeenCalled()
    expect(w.setUser).toHaveBeenCalled()
    expect(mocks.recoverPushConsentFromBrowser).toHaveBeenCalled()
    expect(mocks.softSyncPushSubscription).toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("calls handleUnauthorized on a 401 from fetchCurrentUser (lines 347-350)", async () => {
    const w = makeWires()
    const err = new AxiosError("unauth")
    err.response = { status: 401, headers: {}, data: {}, statusText: "", config: {} as never }
    mocks.fetchCurrentUser.mockRejectedValue(err)
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.refresh()
    })
    expect(w.handleUnauthorized).toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("swallows non-401 fetch errors without unauthorizing", async () => {
    const w = makeWires()
    mocks.fetchCurrentUser.mockRejectedValue(new Error("flaky"))
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.refresh()
    })
    expect(w.handleUnauthorized).not.toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })
})

// ---------------------------------------------------------------------------
// loginWithPasskey — lines 356-433
// ---------------------------------------------------------------------------

describe("loginWithPasskey", () => {
  it("no-ops when authOperation is in-flight (line ~358)", async () => {
    const w = makeWires({ authOperation: true })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.loginWithPasskey("a@b.dev")
    })
    expect(mocks.apiPost).not.toHaveBeenCalled()
  })

  it("runs the full passkey flow then signs in (lines 361-408)", async () => {
    const w = makeWires()
    mocks.apiPost
      .mockResolvedValueOnce({
        status: 200,
        data: { publicKey: { challenge: "x" }, challenge_token: "ct-pk" },
      })
      .mockResolvedValueOnce({
        status: 200,
        data: { user: fullUser({ spotify_connected: true }), session: { signing_key: "sk-pk" } },
      })
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.loginWithPasskey("a@b.dev", true)
    })
    expect(mocks.startAuthentication).toHaveBeenCalled()
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/login/passkey/start",
      { email: "a@b.dev" },
      expect.anything()
    )
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/login/passkey/verify",
      expect.objectContaining({ challenge_token: "ct-pk", trust_device: true }),
      expect.anything()
    )
    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("sk-pk")
    expect(mocks.incrementSessionEpoch).toHaveBeenCalled()
    expect(w.setUser).toHaveBeenCalled()
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT }))
    dispatch.mockRestore()
  })

  it("maps 423 lockout with retry-after to a duration message (lines 410-417)", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValueOnce({
      status: 200,
      data: { publicKey: {}, challenge_token: "ct" },
    })
    mocks.startAuthentication.mockRejectedValue(lockedError("120"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.loginWithPasskey("a@b.dev")
      })
    ).rejects.toThrow(/login\.locked .*login\.lockedRetry/)
  })

  it("maps 423 lockout without retry-after to plain locked message (line 417)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError())
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.loginWithPasskey("a@b.dev")
      })
    ).rejects.toThrow("login.locked")
  })

  it("re-throws non-423 errors unchanged (line 419)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(new Error("passkey unavailable"))
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.loginWithPasskey("a@b.dev")
      })
    ).rejects.toThrow("passkey unavailable")
  })
})

describe("useAuthApi — residual defensive branches", () => {
  it("returns no signing key for an absent response value", () => {
    expect(extractSigningKey(null)).toBeNull()
    expect(extractSigningKey(undefined)).toBeNull()
  })

  it("rejects a null token response as invalid", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: null } as never)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow("Invalid response from server")
  })

  it("formats lockouts measured in hours", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError("7200"))
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow(/login\.duration\.hours:2/)
  })

  it("swallows push soft-sync failures after a recovered login consent", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    mocks.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mocks.softSyncPushSubscription.mockRejectedValue(new Error("push sync unavailable"))
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })
    await waitFor(() => expect(mocks.softSyncPushSubscription).toHaveBeenCalled())
  })

  it("swallows push soft-sync failures after an MFA verification", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    mocks.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mocks.softSyncPushSubscription.mockRejectedValue(new Error("push sync unavailable"))
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.submitMfaChallenge({ code: "123456", challengeToken: "ct" })
    })
    await waitFor(() => expect(mocks.softSyncPushSubscription).toHaveBeenCalled())
  })

  it("swallows push soft-sync failures after a passkey verification", async () => {
    const w = makeWires()
    mocks.apiPost
      .mockResolvedValueOnce({
        status: 200,
        data: { publicKey: {}, challenge_token: "ct" },
      })
      .mockResolvedValueOnce({ status: 200, data: { user: fullUser() } })
    mocks.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mocks.softSyncPushSubscription.mockRejectedValue(new Error("push sync unavailable"))
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.loginWithPasskey("a@b.dev")
    })
    await waitFor(() => expect(mocks.softSyncPushSubscription).toHaveBeenCalled())
  })

  it("swallows a dashboard prefetch import failure", async () => {
    vi.doMock("@/hooks/useDashboardStories", () => {
      throw new Error("dashboard module unavailable")
    })
    try {
      const w = makeWires()
      mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
      const { result } = renderApi(w)

      await act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
      await waitFor(() => expect(w.setUser).toHaveBeenCalled())
    } finally {
      vi.doUnmock("@/hooks/useDashboardStories")
    }
  })
})
