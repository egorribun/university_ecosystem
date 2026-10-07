import type { ReactNode } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosError, AxiosHeaders } from "axios"

import { extractSigningKey, useAuthApi } from "./useAuthApi"
import type { User } from "@/types/User"
import { ChallengeLockedError, type PendingMfaState } from "@/types/Auth"
import type { PendingMfaResponse } from "@/types/Mfa"
import {
  acceptBrowserSessionGeneration,
  captureSessionEpoch,
  invalidateSessionEpoch,
} from "@/stores/sessionEpoch"
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
  i18n: {
    resolvedLanguage: "en" as string | undefined,
    language: "en" as string | undefined,
  },
  incrementSessionEpoch: vi.fn(),
  fetchCurrentUser: vi.fn((..._a: unknown[]) => Promise.resolve({ id: "u-1" })),
  hasPushConsent: vi.fn(() => false),
  setPushConsent: vi.fn(),
  syncPushForConfirmedIdentity: vi.fn(async (..._a: unknown[]) => null as unknown),
  releasePushServerBinding: vi.fn(async () => undefined as void),
  prefetchDashboardStories: vi.fn(),
  prefetchDashboardNews: vi.fn(),
  prefetchDashboardEvents: vi.fn(),
  prefetchEventsListQuery: vi.fn(),
  logWarning: vi.fn(),
  logError: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  API_UNAUTHORIZED_EVENT: "auth:unauthorized",
  default: { post: mocks.apiPost, get: mocks.apiGet },
}))

vi.mock("@/api/interceptors/etagCache", () => ({
  incrementSessionEpoch: mocks.incrementSessionEpoch,
}))

vi.mock("./useProfileSync", () => ({
  fetchCurrentUser: mocks.fetchCurrentUser,
}))

vi.mock("@/push/subscribe", () => ({
  hasPushConsent: mocks.hasPushConsent,
  setPushConsent: mocks.setPushConsent,
  syncPushForConfirmedIdentity: mocks.syncPushForConfirmedIdentity,
  releasePushServerBinding: mocks.releasePushServerBinding,
}))

vi.mock("@/i18n/config", () => ({ default: mocks.i18n }))

vi.mock("@/hooks/useDashboardStories", () => ({
  prefetchDashboardStories: mocks.prefetchDashboardStories,
}))

vi.mock("@/hooks/useDashboardNews", () => ({
  prefetchDashboardNews: mocks.prefetchDashboardNews,
}))

vi.mock("@/hooks/useDashboardEvents", () => ({
  prefetchDashboardEvents: mocks.prefetchDashboardEvents,
}))

vi.mock("@/api/hooks/events", () => ({
  EVENTS_PAGE_SIZE: 20,
  prefetchEventsListQuery: mocks.prefetchEventsListQuery,
}))

vi.mock("@/app/logger", () => ({
  logWarning: mocks.logWarning,
  logError: mocks.logError,
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

type UseAuthApiArgs = Parameters<typeof useAuthApi>

type Wires = {
  user: UseAuthApiArgs[0]
  setUser: UseAuthApiArgs[1]
  updatePendingMfa: UseAuthApiArgs[2]
  handleUnauthorized: UseAuthApiArgs[3]
  updateSessionSigningKey: UseAuthApiArgs[4]
  authOperation: boolean
  setAuthOperation: UseAuthApiArgs[6]
  resetEtagCache: UseAuthApiArgs[7]
  pendingMfa?: PendingMfaState | null
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
        w.resetEtagCache,
        w.pendingMfa
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
  mocks.i18n.resolvedLanguage = "en"
  mocks.i18n.language = "en"
  mocks.apiPost.mockResolvedValue({ status: 200, data: {} })
  mocks.apiGet.mockResolvedValue({ status: 200, data: {} })
  mocks.hasPushConsent.mockReturnValue(false)
  mocks.syncPushForConfirmedIdentity.mockResolvedValue(null)
  mocks.releasePushServerBinding.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.unstubAllEnvs()
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

  it("no-ops when authOperation becomes in-flight after login callback creation", async () => {
    const w = makeWires({ authOperation: false })
    const { result, rerender } = renderApi(w)
    w.authOperation = true
    rerender()

    let output: unknown
    await act(async () => {
      output = await result.current.login("a@b.dev", "pw")
    })

    expect(output).toBeNull()
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

  it("omits trusted-device enrollment when login uses its default", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValueOnce({
      status: 200,
      data: { user: fullUser() },
    })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    const body = mocks.apiPost.mock.calls[0]![1] as URLSearchParams
    expect(body.has("trust_device")).toBe(false)
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

  it("does not request Spotify reauthorization for an unconnected login profile", async () => {
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const w = makeWires()
    mocks.apiPost.mockResolvedValueOnce({
      status: 200,
      data: { user: fullUser({ spotify_connected: false }) },
    })
    const { result } = renderApi(w)

    try {
      await act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
      expect(dispatch).not.toHaveBeenCalledWith(
        expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT })
      )
    } finally {
      dispatch.mockRestore()
    }
  })
  it("hands push sync to the identity gate for exactly the logged-in account", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser({ id: 42 } as never) } })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })
    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledOnce()
    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledWith({ expectedUserId: "42" })
  })

  it("does not start a push sync for a pending MFA challenge", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 202,
      data: { challenge_token: "ct", methods: [], expires_in: 60 },
    })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })
    expect(mocks.syncPushForConfirmedIdentity).not.toHaveBeenCalled()
  })

  it.each([
    ["missing user property", { nope: true }],
    ["null response payload", null],
    ["truthy non-object user", { user: "malformed-profile" }],
  ] as const)(
    "rejects malformed login response payloads before changing auth state (%s)",
    async (_caseName, data) => {
      const w = makeWires()
      mocks.apiPost.mockResolvedValueOnce({ status: 200, data } as never)
      const { result } = renderApi(w)

      await expect(
        act(async () => {
          await result.current.login("test@example.com", "password")
        })
      ).rejects.toThrow("Invalid response from server")

      expect(w.setUser).not.toHaveBeenCalled()
      expect(w.updateSessionSigningKey).not.toHaveBeenCalled()
      expect(mocks.incrementSessionEpoch).not.toHaveBeenCalled()
      expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
    }
  )

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
    const cause = lockedError("30")
    mocks.apiPost.mockRejectedValue(cause)
    const { result } = renderApi(w)
    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toMatchObject({
      message: expect.stringMatching(/login\.locked .*login\.lockedRetry/),
      cause,
    })
  })

  it.each([
    ["60", /login\.duration\.minutes:1/],
    ["3600", /login\.duration\.hours:1/],
  ])("uses the next lockout unit at the %s second boundary", async (retryAfter, expected) => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError(retryAfter))
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toThrow(expected)
  })

  it.each(["not-a-number", "-1"])(
    "keeps a plain lockout message for unusable Retry-After value %s",
    async (retryAfter) => {
      const w = makeWires()
      const cause = lockedError(retryAfter)
      mocks.apiPost.mockRejectedValue(cause)
      const { result } = renderApi(w)

      await expect(
        act(async () => {
          await result.current.login("a@b.dev", "pw")
        })
      ).rejects.toMatchObject({ message: "login.locked", cause })
      expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
    }
  )
  describe("lockout Retry-After public behavior", () => {
    it("keeps zero retry-after as the plain locked error", async () => {
      const w = makeWires()
      const cause = lockedError("0")
      mocks.apiPost.mockRejectedValue(cause)
      const { result } = renderApi(w)

      await expect(
        act(async () => {
          await result.current.login("a@b.dev", "pw")
        })
      ).rejects.toMatchObject({ message: "login.locked", cause })
    })

    it("reports the rounded positive seconds in the login lockout error", async () => {
      const w = makeWires()
      const cause = lockedError("30")
      mocks.apiPost.mockRejectedValue(cause)
      const { result } = renderApi(w)

      await expect(
        act(async () => {
          await result.current.login("a@b.dev", "pw")
        })
      ).rejects.toMatchObject({
        message: "login.locked login.lockedRetry:login.duration.seconds:30",
        cause,
      })
    })
  })

  it("rethrows an Axios transport error when the response is absent", async () => {
    const w = makeWires()
    const error = new AxiosError("transport failure")
    mocks.apiPost.mockRejectedValue(error)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toBe(error)
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
  it("skips dashboard prefetches in LHCI synthetic-auth builds", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ group_id: "grp-1" }) },
    })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
      await result.current.submitMfaChallenge({ code: "123456", challengeToken: "ct" })
    })

    expect(mocks.prefetchDashboardStories).not.toHaveBeenCalled()
    expect(mocks.prefetchDashboardNews).not.toHaveBeenCalled()
    expect(mocks.prefetchDashboardEvents).not.toHaveBeenCalled()
    expect(mocks.prefetchEventsListQuery).not.toHaveBeenCalled()
  })

  it("prefetches dashboard data after login and events when the user has a group_id", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ group_id: "grp-1" }) },
    })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() => {
      expect(mocks.prefetchDashboardStories).toHaveBeenCalledWith(expect.anything())
      expect(mocks.prefetchDashboardNews).toHaveBeenCalledWith(expect.anything(), "en")
      expect(mocks.prefetchDashboardEvents).toHaveBeenCalledWith(expect.anything())
      expect(mocks.prefetchEventsListQuery).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ language: "en", is_active: true, limit: 20 })
      )
    })
    expect(w.setUser).toHaveBeenCalled()
  })

  it("falls back to the configured language and normalizes non-English locales to Russian", async () => {
    mocks.i18n.resolvedLanguage = undefined
    mocks.i18n.language = "fr"
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() =>
      expect(mocks.prefetchDashboardNews).toHaveBeenCalledWith(expect.anything(), "ru")
    )
  })

  it("uses English from the configured language when the resolved language is absent", async () => {
    mocks.i18n.resolvedLanguage = undefined
    mocks.i18n.language = "en"
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() =>
      expect(mocks.prefetchDashboardNews).toHaveBeenCalledWith(expect.anything(), "en")
    )
  })

  it("defaults dashboard prefetching to Russian when i18n exposes no active language", async () => {
    mocks.i18n.resolvedLanguage = undefined
    mocks.i18n.language = undefined
    const w = makeWires({})
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ group_id: "grp-1" }) },
    })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() =>
      expect(mocks.prefetchEventsListQuery).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ language: "ru" })
      )
    )
  })

  it("suppresses dashboard prefetch diagnostics outside development", async () => {
    vi.stubEnv("DEV", false)
    mocks.prefetchDashboardStories.mockImplementationOnce(() => {
      throw new Error("prefetch unavailable")
    })
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() => expect(mocks.prefetchDashboardStories).toHaveBeenCalled())
    expect(mocks.logWarning).not.toHaveBeenCalled()
  })

  it("reports dashboard prefetch failures in development", async () => {
    // The prefetch is deliberately best-effort, but diagnostics remain
    // visible to developers when a statically linked prefetch callback throws.
    vi.stubEnv("DEV", true)
    const failure = new Error("prefetch unavailable")
    mocks.prefetchDashboardStories.mockImplementationOnce(() => {
      throw failure
    })
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.login("a@b.dev", "pw")
    })

    await waitFor(() => expect(mocks.prefetchDashboardStories).toHaveBeenCalled())
    expect(mocks.logWarning).toHaveBeenCalledWith(
      "Failed to prefetch dashboard data",
      expect.objectContaining({ error: failure })
    )
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

  it("unbinds this browser endpoint on the server before ending the session", async () => {
    const w = makeWires({ user: fullUser() })
    const order: string[] = []
    mocks.releasePushServerBinding.mockImplementation(async () => {
      order.push("release")
    })
    mocks.apiPost.mockImplementation(async (url: unknown) => {
      order.push(String(url))
      return { status: 200, data: {} }
    })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.logout()
    })

    // The unbind needs the still-valid session, so it must finish first.
    expect(order).toEqual(["release", "/auth/logout"])
    expect(mocks.setPushConsent).not.toHaveBeenCalled()
    expect(w.handleUnauthorized).toHaveBeenCalledOnce()
  })

  it("still ends the session when the push unbind fails", async () => {
    const w = makeWires({ user: fullUser() })
    const failure = new Error("unbind failed")
    mocks.releasePushServerBinding.mockRejectedValue(failure)
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.logout()
    })

    expect(mocks.logWarning).toHaveBeenCalledWith(
      "Failed to release push binding on logout",
      failure
    )
    expect(mocks.apiPost).toHaveBeenCalledWith("/auth/logout")
    expect(mocks.logError).not.toHaveBeenCalled()
    expect(w.handleUnauthorized).toHaveBeenCalledOnce()
  })

  it("skips the logout POST when there is no user, still unauthorizes (line 216 false branch)", async () => {
    const w = makeWires({ user: null })
    const { result } = renderApi(w)
    await act(async () => {
      await result.current.logout()
    })
    expect(mocks.apiPost).not.toHaveBeenCalled()
    expect(mocks.releasePushServerBinding).not.toHaveBeenCalled()
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

  it("uses the latest signed-in profile when logout follows an auth-state rerender", async () => {
    const w = makeWires({ user: null })
    const { result, rerender } = renderApi(w)
    w.user = fullUser({ id: "current-account" })
    rerender()

    await act(async () => {
      await result.current.logout()
    })

    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
    expect(mocks.apiPost).toHaveBeenCalledWith("/auth/logout")
    expect(w.handleUnauthorized).toHaveBeenCalledTimes(1)
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

  it("does not submit when authOperation becomes in-flight after MFA callback creation", async () => {
    const storageKey = "ecosystem.session.generation.v1"
    const previousGeneration = localStorage.getItem(storageKey)
    const w = makeWires({
      pendingMfa: { status: "mfa_required", user_id: "u-1", methods: [], reason: "login" },
    })
    let unmount = () => {}

    try {
      acceptBrowserSessionGeneration()
      const stillOwnsCapturedSession = captureSessionEpoch()
      const { result, rerender, unmount: unmountHook } = renderApi(w)
      unmount = unmountHook
      w.authOperation = true
      rerender()

      await act(async () => {
        await result.current.submitMfaChallenge({
          code: "123456",
          challengeToken: "ct",
        })
      })

      expect(stillOwnsCapturedSession()).toBe(true)
      expect(localStorage.getItem(storageKey)).toBe(previousGeneration)
      expect(mocks.apiPost).not.toHaveBeenCalled()
      expect(w.setAuthOperation).not.toHaveBeenCalled()
      expect(w.setUser).not.toHaveBeenCalled()
      expect(w.updatePendingMfa).not.toHaveBeenCalled()
    } finally {
      unmount()
      if (previousGeneration === null) localStorage.removeItem(storageKey)
      else localStorage.setItem(storageKey, previousGeneration)
      acceptBrowserSessionGeneration()
    }
  })

  it("verifies a totp challenge and signs the session in (lines 243-279)", async () => {
    const w = makeWires({ updateSessionSigningKey: vi.fn(() => invalidateSessionEpoch()) })
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
      })
    })
    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/mfa/verify",
      expect.objectContaining({
        method: "totp",
        code: "654321",
        challenge_token: "ct-1",
      }),
      expect.objectContaining({ skipRateLimitQueue: true })
    )
    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("sk-2")
    expect(w.setAuthOperation).toHaveBeenCalledTimes(2)
    expect(w.setAuthOperation).toHaveBeenNthCalledWith(1, true)
    expect(w.setAuthOperation).toHaveBeenNthCalledWith(2, false)
    expect(mocks.incrementSessionEpoch).toHaveBeenCalled()
    expect(w.setUser).toHaveBeenCalled()
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT }))
    dispatch.mockRestore()

    await waitFor(() => {
      expect(mocks.prefetchDashboardStories).toHaveBeenCalledWith(expect.anything())
      expect(mocks.prefetchDashboardNews).toHaveBeenCalledWith(expect.anything(), "en")
      expect(mocks.prefetchDashboardEvents).toHaveBeenCalledWith(expect.anything())
    })
    expect(mocks.prefetchEventsListQuery).not.toHaveBeenCalled()
  })

  it("does not request Spotify reauthorization for an unconnected login MFA profile", async () => {
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const w = makeWires({ pendingMfa: { reason: "login" } as PendingMfaState })
    mocks.apiPost.mockResolvedValueOnce({
      status: 200,
      data: { user: fullUser({ spotify_connected: false }) },
    })
    const { result } = renderApi(w)

    try {
      await act(async () => {
        await result.current.submitMfaChallenge({ code: "123456" })
      })
      expect(dispatch).not.toHaveBeenCalledWith(
        expect.objectContaining({ type: SPOTIFY_REAUTH_EVENT })
      )
    } finally {
      dispatch.mockRestore()
    }
  })
  it("sends an empty challenge token when the optional token is absent", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.submitMfaChallenge({ code: "654321" })
    })

    expect(mocks.apiPost).toHaveBeenCalledWith(
      "/auth/mfa/verify",
      expect.objectContaining({ challenge_token: "" }),
      expect.anything()
    )
  })

  it("throws ChallengeLockedError on 423 (lines 282-289)", async () => {
    const w = makeWires()
    mocks.apiPost.mockRejectedValue(lockedError("90"))
    const { result } = renderApi(w)
    let caught: unknown
    await act(async () => {
      try {
        await result.current.submitMfaChallenge({ code: "1", challengeToken: "ct" })
      } catch (error) {
        caught = error
      }
    })
    expect(caught).toBeInstanceOf(ChallengeLockedError)
    expect((caught as ChallengeLockedError).refreshable).toBe(false)
    expect((caught as ChallengeLockedError).message).toBe(
      "login.locked login.lockedRetry:login.duration.minutes:2"
    )
    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
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

  it("rethrows an Axios MFA transport error without dereferencing response", async () => {
    const w = makeWires()
    const error = new AxiosError("MFA transport failure")
    mocks.apiPost.mockRejectedValue(error)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.submitMfaChallenge({ code: "1", challengeToken: "ct" })
      })
    ).rejects.toBe(error)
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

  it("leaves auth state untouched for a malformed successful payload", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValue({ status: 200, data: {} })
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.submitMfaChallenge({ code: "123456", challengeToken: "ct" })
    })

    expect(w.setUser).not.toHaveBeenCalled()
    expect(w.updatePendingMfa).not.toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
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

  it("rethrows a non-Axios response-shaped 401 without dispatching unauthorized", async () => {
    const w = makeWires()
    const error = Object.assign(new Error("application-level failure"), {
      response: { status: 401 },
    })
    const dispatch = vi.spyOn(window, "dispatchEvent")
    mocks.apiPost.mockRejectedValueOnce(error)
    const { result } = renderApi(w)

    try {
      await expect(
        act(async () => {
          await result.current.requireMfa()
        })
      ).rejects.toBe(error)
      expect(
        dispatch.mock.calls.filter(([event]) => event.type === API_UNAUTHORIZED_EVENT)
      ).toHaveLength(0)
      expect(w.updatePendingMfa).not.toHaveBeenCalled()
      expect(w.setUser).not.toHaveBeenCalled()
    } finally {
      dispatch.mockRestore()
    }
  })

  it("rethrows an Axios error without a response from step-up", async () => {
    const w = makeWires()
    const error = new AxiosError("step-up transport failure")
    mocks.apiPost.mockRejectedValue(error)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.requireMfa()
      })
    ).rejects.toBe(error)
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

  it("re-throws non-auth Axios failures", async () => {
    const w = makeWires()
    const err = new AxiosError("upstream unavailable")
    err.response = { status: 500, headers: {}, data: {}, statusText: "", config: {} as never }
    mocks.apiPost.mockRejectedValue(err)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.requireMfa()
      })
    ).rejects.toBe(err)
  })
})

// ---------------------------------------------------------------------------
// refresh — lines 332-354
// ---------------------------------------------------------------------------

describe("refresh", () => {
  it("does not restore a profile after logout overtakes refresh", async () => {
    let finish!: (value: User) => void
    mocks.fetchCurrentUser.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    const w = makeWires({ user: fullUser() })
    const { result } = renderApi(w)
    let pending!: Promise<void>
    act(() => {
      pending = result.current.refresh()
    })
    await act(() => result.current.logout())
    await act(async () => {
      finish(fullUser())
      await pending
    })
    expect(w.setUser).not.toHaveBeenCalled()
    expect(mocks.syncPushForConfirmedIdentity).not.toHaveBeenCalled()
  })

  it("does not let a stale refresh 401 clear a newly signed-in profile", async () => {
    const storageKey = "ecosystem.session.generation.v1"
    const previousGeneration = localStorage.getItem(storageKey)
    let finishCurrentUser!: (value: User) => void
    let rejectCurrentUser!: (reason: unknown) => void
    let refreshSettled = false
    let refreshPending!: Promise<void>
    const rerenderHook: { current?: () => void } = {}
    const replacement = fullUser({ id: "new-account", email: "new@b.dev" })
    const handleUnauthorized = vi.fn(() => {
      w.user = null
      rerenderHook.current?.()
    })
    const w: Wires = makeWires({
      user: fullUser({ id: "old-account", email: "old@b.dev" }),
      handleUnauthorized,
    })
    mocks.fetchCurrentUser.mockImplementationOnce(
      () =>
        new Promise<User>((resolve, reject) => {
          finishCurrentUser = resolve
          rejectCurrentUser = reject
        })
    )
    const { result, rerender } = renderApi(w)
    rerenderHook.current = rerender

    try {
      act(() => {
        refreshPending = result.current.refresh()
      })
      await act(() => result.current.logout())
      expect(w.user).toBeNull()
      handleUnauthorized.mockClear()

      mocks.apiPost.mockResolvedValueOnce({
        status: 200,
        data: { user: replacement },
      } as never)
      await act(async () => {
        await result.current.login("new@b.dev", "password")
      })
      w.user = replacement
      rerender()

      const unauthorized = new AxiosError("stale unauthorized")
      unauthorized.response = {
        status: 401,
        headers: {},
        data: {},
        statusText: "Unauthorized",
        config: {} as never,
      }
      await act(async () => {
        rejectCurrentUser(unauthorized)
        refreshSettled = true
        await refreshPending
      })

      expect(w.setUser).toHaveBeenCalledWith(replacement)
      expect(handleUnauthorized).not.toHaveBeenCalled()
      expect(w.user).toBe(replacement)
    } finally {
      if (!refreshSettled && finishCurrentUser) {
        finishCurrentUser(fullUser({ id: "old-account", email: "old@b.dev" }))
        await act(async () => {
          await refreshPending
        })
      }
      if (previousGeneration === null) localStorage.removeItem(storageKey)
      else localStorage.setItem(storageKey, previousGeneration)
      acceptBrowserSessionGeneration()
    }
  })

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
    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledWith({ expectedUserId: "u-1" })
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("finishes the refresh without waiting for the identity-gated push sync", async () => {
    const w = makeWires()
    mocks.fetchCurrentUser.mockResolvedValue(fullUser())
    // The gate only resolves after authOperation is cleared; awaiting it
    // inside the refresh would deadlock.
    mocks.syncPushForConfirmedIdentity.mockReturnValue(new Promise(() => {}))
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.refresh()
    })

    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledOnce()
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

  it("swallows an Axios refresh error when the response is absent", async () => {
    const w = makeWires()
    const error = new AxiosError("refresh transport failure")
    mocks.fetchCurrentUser.mockRejectedValue(error)
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.refresh()
    })

    expect(w.handleUnauthorized).not.toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("logs an asynchronous push-sync failure after refresh", async () => {
    const w = makeWires()
    const failure = new Error("push unavailable")
    mocks.fetchCurrentUser.mockResolvedValue(fullUser())
    mocks.syncPushForConfirmedIdentity.mockRejectedValue(failure)
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.refresh()
    })

    await waitFor(() =>
      expect(mocks.logWarning).toHaveBeenCalledWith(
        "Push sync after authentication failed",
        failure
      )
    )
    expect(w.handleUnauthorized).not.toHaveBeenCalled()
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })

  it("uses the latest unauthorized handler when refresh follows callback rerender", async () => {
    const previousHandler = vi.fn()
    const currentHandler = vi.fn()
    const w = makeWires({ handleUnauthorized: previousHandler })
    const { result, rerender } = renderApi(w)
    w.handleUnauthorized = currentHandler
    rerender()

    const unauthorized = new AxiosError("unauthorized")
    unauthorized.response = {
      status: 401,
      headers: {},
      data: {},
      statusText: "Unauthorized",
      config: {} as never,
    }
    mocks.fetchCurrentUser.mockRejectedValueOnce(unauthorized)

    await act(async () => {
      await result.current.refresh()
    })

    expect(currentHandler).toHaveBeenCalledTimes(1)
    expect(previousHandler).not.toHaveBeenCalled()
  })
})

describe("useAuthApi — residual defensive branches", () => {
  it("returns no signing key for an absent response value", () => {
    expect(extractSigningKey(null)).toBeNull()
    expect(extractSigningKey(undefined)).toBeNull()
  })

  it("returns no key when a response has no usable session signing key", () => {
    expect(extractSigningKey({})).toBeNull()
    expect(extractSigningKey({ session: null })).toBeNull()
    expect(extractSigningKey({ session: { signing_key: "" } })).toBeNull()
    expect(extractSigningKey({ session: { signing_key: "valid-key" } })).toBe("valid-key")
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
    const cause = lockedError("7200")
    mocks.apiPost.mockRejectedValue(cause)
    const { result } = renderApi(w)

    await expect(
      act(async () => {
        await result.current.login("a@b.dev", "pw")
      })
    ).rejects.toMatchObject({
      message: "login.locked login.lockedRetry:login.duration.hours:2",
      cause,
    })
  })

  it("logs a push-sync rejection after login without failing the login", async () => {
    const w = makeWires()
    const failure = new Error("push sync unavailable")
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser() } })
    mocks.syncPushForConfirmedIdentity.mockRejectedValue(failure)
    const { result } = renderApi(w)

    let out: unknown = "x"
    await act(async () => {
      out = await result.current.login("a@b.dev", "pw")
    })

    expect(out).toBeNull()
    await waitFor(() =>
      expect(mocks.logWarning).toHaveBeenCalledWith(
        "Push sync after authentication failed",
        failure
      )
    )
  })

  it("hands push sync to the identity gate after an MFA verification", async () => {
    const w = makeWires()
    const failure = new Error("push sync unavailable")
    mocks.apiPost.mockResolvedValue({ status: 200, data: { user: fullUser({ id: "mfa-user" }) } })
    mocks.syncPushForConfirmedIdentity.mockRejectedValue(failure)
    const { result } = renderApi(w)

    await act(async () => {
      await result.current.submitMfaChallenge({ code: "123456", challengeToken: "ct" })
    })

    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledWith({
      expectedUserId: "mfa-user",
    })
    await waitFor(() =>
      expect(mocks.logWarning).toHaveBeenCalledWith(
        "Push sync after authentication failed",
        failure
      )
    )
    expect(w.setAuthOperation).toHaveBeenLastCalledWith(false)
  })
})

describe("late authentication responses", () => {
  it.each(["login", "mfa"])("ignores a late %s response after logout", async (operation) => {
    let finish!: (value: {
      status: number
      data: { user: User; session: { signing_key: string } }
    }) => void
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    const w = makeWires()
    const { result } = renderApi(w)
    let pending!: Promise<unknown>
    act(() => {
      pending =
        operation === "login"
          ? result.current.login("a@b.dev", "pw")
          : result.current.submitMfaChallenge({
              method: "totp",
              code: "123456",
              challengeToken: "challenge",
            })
    })
    await act(() => result.current.logout())
    await act(async () => {
      finish({ status: 200, data: { user: fullUser(), session: { signing_key: "old-key" } } })
      await pending
    })
    expect(w.setUser).not.toHaveBeenCalled()
    expect(w.updateSessionSigningKey).not.toHaveBeenCalled()
  })
})

describe("login MFA browser-session boundary", () => {
  it("rotates the browser session at the login MFA boundary", async () => {
    const w = makeWires()
    mocks.apiPost.mockResolvedValueOnce({
      status: 202,
      data: { status: "mfa_required", user_id: "u-1", methods: [] },
    })
    const { result, rerender } = renderApi(w)
    let challenge: PendingMfaState | null = null
    await act(async () => {
      challenge = await result.current.login("a@b.dev", "pw")
    })
    expect(challenge).toMatchObject({ reason: "login" })
    if (challenge === null) throw new Error("Expected a login MFA challenge")

    w.pendingMfa = challenge
    rerender()
    const challengeSessionWork = captureSessionEpoch()
    expect(challengeSessionWork()).toBe(true)

    let resolveVerification!: (value: {
      status: number
      data: { user: User; session: { signing_key: string } }
    }) => void
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveVerification = resolve
        })
    )
    let verification!: Promise<void>
    act(() => {
      verification = result.current.submitMfaChallenge({
        method: "totp",
        code: "123456",
        challengeToken: "ct-login",
      })
    })

    try {
      expect(challengeSessionWork()).toBe(false)
    } finally {
      await act(async () => {
        resolveVerification({
          status: 200,
          data: { user: fullUser(), session: { signing_key: "sk-login" } },
        })
        await verification
      })
    }

    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("sk-login")
    expect(w.setUser).toHaveBeenCalledWith(expect.objectContaining({ id: "u-1" }))
  })
})

describe("authenticated MFA step-up", () => {
  it("switches accounts after login MFA even when a prior user is still present", async () => {
    const priorUser = fullUser({ id: "prior-account" })
    const nextUser = fullUser({ id: "new-account" })
    const w = makeWires({ user: priorUser })
    const loginChallengeResponse = {
      status: "mfa_required",
      user_id: "new-account",
      methods: [
        {
          method: "totp",
          challenge_token: "new-account-challenge",
          challenge_expires_at: new Date(Date.now() + 60_000).toISOString(),
        },
      ],
    } satisfies PendingMfaResponse
    mocks.apiPost
      .mockResolvedValueOnce({
        status: 202,
        data: loginChallengeResponse,
      })
      .mockResolvedValueOnce({
        status: 200,
        data: { user: nextUser, session: { signing_key: "new-account-key" } },
      })
    const { result, rerender } = renderApi(w)
    const challengeHolder: { current: PendingMfaState | null } = { current: null }

    await act(async () => {
      challengeHolder.current = await result.current.login("new@example.com", "password")
    })

    const loginChallenge = challengeHolder.current
    expect(loginChallenge).toMatchObject({ reason: "login", user_id: "new-account" })
    expect(w.setUser).not.toHaveBeenCalled()
    expect(w.updatePendingMfa).toHaveBeenCalledWith(loginChallenge)

    if (loginChallenge === null) throw new Error("Expected a login MFA challenge")
    const loginTotpMethod = loginChallenge.methods.find(({ method }) => method === "totp")
    if (!loginTotpMethod) throw new Error("Expected the login challenge to include TOTP")
    w.pendingMfa = loginChallenge
    rerender()

    await act(async () => {
      await result.current.submitMfaChallenge({
        method: "totp",
        code: "123456",
        challengeToken: loginTotpMethod.challenge_token,
      })
    })

    expect(w.updateSessionSigningKey).toHaveBeenCalledWith("new-account-key")
    expect(w.setUser).toHaveBeenCalledWith(nextUser)
    expect(w.updatePendingMfa).toHaveBeenLastCalledWith(null)
  })

  it("preserves the same account's captured retry lifetime and signing key", async () => {
    const currentUser = fullUser()
    const w = makeWires({ user: currentUser, pendingMfa: { reason: "step-up" } as PendingMfaState })
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: currentUser, session: { signing_key: "same-session-key" } },
    } as never)
    const { result } = renderApi(w)
    const retryOwnsSession = captureSessionEpoch()
    await act(() =>
      result.current.submitMfaChallenge({
        method: "totp",
        code: "123456",
        challengeToken: "step-up",
      })
    )
    expect(retryOwnsSession()).toBe(true)
    expect(w.setUser).toHaveBeenCalledWith(currentUser)
    expect(w.updateSessionSigningKey).not.toHaveBeenCalled()
    expect(mocks.incrementSessionEpoch).not.toHaveBeenCalled()
    expect(mocks.syncPushForConfirmedIdentity).not.toHaveBeenCalled()
  })

  it("rejects another account's profile returned to an authenticated step-up", async () => {
    const w = makeWires({ user: fullUser(), pendingMfa: { reason: "step-up" } as PendingMfaState })
    mocks.apiPost.mockResolvedValue({
      status: 200,
      data: { user: fullUser({ id: "other-account" }) },
    } as never)
    const { result } = renderApi(w)
    await expect(
      act(() =>
        result.current.submitMfaChallenge({
          method: "totp",
          code: "123456",
          challengeToken: "step-up",
        })
      )
    ).rejects.toThrow("MFA response does not match")
    expect(w.setUser).not.toHaveBeenCalled()
  })
})

describe("authentication cancellation boundaries", () => {
  it.each(["login", "mfa", "refresh", "requireMfa"] as const)(
    "does not apply a late %s failure after unmount",
    async (operation) => {
      let reject!: (reason: Error) => void
      const response = new Promise<never>((_resolve, fail) => {
        reject = fail
      })
      if (operation === "refresh") mocks.fetchCurrentUser.mockReturnValueOnce(response)
      else mocks.apiPost.mockReturnValueOnce(response)
      const w = makeWires()
      const { result, unmount } = renderApi(w)
      let pending!: Promise<unknown>
      act(() => {
        pending =
          operation === "login"
            ? result.current.login("a@b.dev", crypto.randomUUID())
            : operation === "mfa"
              ? result.current.submitMfaChallenge({ code: "123456" })
              : result.current[operation]()
      })
      unmount()
      reject(lockedError())
      await expect(pending).resolves.toBe(
        operation === "login" || operation === "requireMfa" ? null : undefined
      )
      expect(w.setUser).not.toHaveBeenCalled()
      expect(w.handleUnauthorized).not.toHaveBeenCalled()
      expect(w.updatePendingMfa).not.toHaveBeenCalled()
      expect(w.setAuthOperation).not.toHaveBeenCalledWith(false)
    }
  )

  it.each(["refresh", "requireMfa", "submitMfaChallenge"] as const)(
    "does not dispatch retained %s actions after unmount",
    async (operation) => {
      const { result, unmount } = renderApi(makeWires({ user: fullUser() }))
      const actions = result.current
      unmount()
      if (operation === "submitMfaChallenge") await actions.submitMfaChallenge({ code: "123456" })
      else await actions[operation]()
      expect(mocks.apiPost).not.toHaveBeenCalled()
      expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
    }
  )

  it("drops a successful step-up challenge after its caller unmounts", async () => {
    let resolve!: (value: { status: number; data: object }) => void
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const w = makeWires()
    const { result, unmount } = renderApi(w)
    const pending = result.current.requireMfa()
    unmount()
    resolve({ status: 202, data: { methods: [] } })
    await expect(pending).resolves.toBeNull()
    expect(w.updatePendingMfa).not.toHaveBeenCalled()
  })

  it("does not clear a newer session when logout settles after unmount", async () => {
    let resolve!: (value: { status: number; data: object }) => void
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const w = makeWires({ user: fullUser() })
    const { result, unmount } = renderApi(w)
    const pending = result.current.logout()
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith("/auth/logout"))
    unmount()
    resolve({ status: 200, data: {} })
    await pending
    expect(w.handleUnauthorized).not.toHaveBeenCalled()
  })
})
