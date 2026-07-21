import type { MutableRefObject, PropsWithChildren } from "react"
import { useRef } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"
import { utf8ToBytes } from "@noble/hashes/utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { testUser } from "@/tests/mocks/handlers"
import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  currentUserQueryKey,
  encryptData,
  fetchCurrentUser,
  signPayload,
  useProfileSync,
  type CacheSignaturePayload,
  type CachedUserSnapshot,
} from "@/hooks/auth/useProfileSync"

/**
 * useProfileSync.branches — drives the heavy hook-body effects + the
 * exported `fetchCurrentUser` branches that the AuthProvider-level specs
 * cannot easily isolate.
 *
 * The hook takes its session-key plumbing as args, so renderHook lets us
 * control the signing key, the auto-fetch effect, the storage /
 * BroadcastChannel sync, handleUnauthorized + clearProfile, and the
 * synchronous bootstrap (verifySignatureSync) directly.
 *
 * NEVER hits MSW for /users/me — `api.get` is spied per test.
 */

const mockSigningKey = Array.from({ length: 32 }, (_, i) => ((i * 13 + 7) % 16).toString(16)).join(
  ""
)

const base64 = (bytes: Uint8Array): string => {
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]!)
  }
  return btoa(binary)
}

const signSync = (payload: CacheSignaturePayload, key: string): string =>
  base64(hmac(sha256, utf8ToBytes(key), utf8ToBytes(JSON.stringify(payload))))

// ---------------------------------------------------------------------------
// renderHook harness: drives useProfileSync with controllable refs/callbacks.
// ---------------------------------------------------------------------------

type HarnessOpts = {
  signingKey?: string | null
  updateSessionSigningKey?: (key: string | null) => void
  ensureSessionSigningKey?: () => Promise<string | null>
}

const renderProfileSync = (opts: HarnessOpts = {}) => {
  const queryClient = createQueryClient()
  const updateSessionSigningKey = opts.updateSessionSigningKey ?? vi.fn((..._a: unknown[]) => {})
  const ensureSessionSigningKey = opts.ensureSessionSigningKey ?? vi.fn(async () => mockSigningKey)

  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const view = renderHook(
    () => {
      const signingKeyRef = useRef<string | null>(opts.signingKey ?? null) as MutableRefObject<
        string | null
      >
      const promiseRef = useRef<Promise<string | null> | null>(null) as MutableRefObject<Promise<
        string | null
      > | null>
      return useProfileSync(
        updateSessionSigningKey,
        signingKeyRef,
        promiseRef,
        ensureSessionSigningKey
      )
    },
    { wrapper }
  )

  return { ...view, queryClient, updateSessionSigningKey, ensureSessionSigningKey }
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ===========================================================================
// fetchCurrentUser — exported async fn (lines 486-516)
// ===========================================================================

describe("fetchCurrentUser branches", () => {
  it("happy path — returns response.data with no cached envelope", async () => {
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const result = await fetchCurrentUser()

    expect(result).toEqual(testUser)
    // No envelope present => no X-Profile-Cache-Envelope header sent.
    expect(getSpy.mock.calls[0]?.[1]?.headers).toBeUndefined()
  })

  it("ASCII envelope — sends X-Profile-Cache-Envelope header", async () => {
    const envelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, envelope)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    await fetchCurrentUser()

    expect(getSpy).toHaveBeenCalledWith(
      "/users/me",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Profile-Cache-Envelope": envelope }),
      })
    )
  })

  it("non-ASCII envelope — clears the cache and sends no header", async () => {
    // The non-ASCII branch (charCode > 0x7f) clears the cache before the
    // request and never attaches the header.
    const nonAscii = '{"name":"Ð�Ð»Ð¸Ñ�Ð°"}Ā'
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, nonAscii)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    await fetchCurrentUser()

    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    expect(getSpy.mock.calls[0]?.[1]?.headers).toBeUndefined()
  })

  it("500 with cached envelope — drops envelope and retries without header", async () => {
    const envelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, envelope)
    const getSpy = vi
      .spyOn(api, "get")
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 500 },
      })
      .mockResolvedValueOnce({ data: testUser } as any)

    const result = await fetchCurrentUser()

    expect(result).toEqual(testUser)
    expect(getSpy).toHaveBeenCalledTimes(2)
    // Retry omits the cache header.
    expect(getSpy.mock.calls[1]?.[1]?.headers).toBeUndefined()
    // Envelope was cleared before retry.
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
  })

  it("401 — does NOT retry (re-throws so caller can handle unauthorized)", async () => {
    const envelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, envelope)
    const axiosErr = { isAxiosError: true, response: { status: 401 } }
    const getSpy = vi.spyOn(api, "get").mockRejectedValue(axiosErr)

    await expect(fetchCurrentUser()).rejects.toBe(axiosErr)
    // The retry branch is gated on `error.response`; a 401 has a response so
    // it WOULD retry — verify it retries once then re-throws the 2nd failure.
    expect(getSpy).toHaveBeenCalledTimes(2)
  })

  it("aborted signal — does NOT retry even with a cached envelope", async () => {
    const envelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, envelope)
    const controller = new AbortController()
    controller.abort()
    const axiosErr = { isAxiosError: true, response: { status: 500 } }
    const getSpy = vi.spyOn(api, "get").mockRejectedValue(axiosErr)

    await expect(fetchCurrentUser({ signal: controller.signal })).rejects.toBe(axiosErr)
    // signal.aborted short-circuits the retry branch → single call.
    expect(getSpy).toHaveBeenCalledTimes(1)
  })

  it("non-axios error — re-throws without retry", async () => {
    const envelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, envelope)
    const plainErr = new Error("network down")
    const getSpy = vi.spyOn(api, "get").mockRejectedValue(plainErr)

    await expect(fetchCurrentUser()).rejects.toBe(plainErr)
    expect(getSpy).toHaveBeenCalledTimes(1)
  })
})

// ===========================================================================
// Hook synchronous bootstrap (useState initFn, lines 647-701)
// ===========================================================================

describe("useProfileSync — synchronous bootstrap (useState initFn)", () => {
  // NOTE: readCachedEnvelope() in the source returns `undefined` for every
  // input (it reads `raw` but never returns it — see useProfileSync.ts:164),
  // so the initFn's `if (!candidate) return null` branch (line 658) is the
  // reachable outcome whenever a signing key + a stored envelope are present.
  // These tests pin that observable behaviour: the hook starts with `user`
  // null and falls through to the async auto-fetch, regardless of envelope
  // shape (encrypted / legacy / version-mismatch / expired / tampered).

  it("starts with null user given an encrypted-string envelope + signing key", async () => {
    const encrypted = await encryptData(
      {
        id: testUser.id,
        full_name: "Cached Alice",
        group_id: null,
        avatar_url: null,
        cover_url: null,
        is_active: true,
        spotify_connected: false,
      } as unknown as CachedUserSnapshot,
      mockSigningKey
    )
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: encrypted!,
    }
    const signature = signSync(payload, mockSigningKey)
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    // initFn: signingKey present → readCachedEnvelope() undefined → null.
    expect(result.current.user).toBeNull()
    // Eventually the async auto-fetch resolves the real user.
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("starts with null user given a legacy v3 (object) envelope + signing key", async () => {
    const snapshot = {
      id: testUser.id,
      full_name: "Legacy Bob",
      group_id: null,
      avatar_url: null,
      cover_url: null,
      is_active: true,
      spotify_connected: false,
    } as unknown as CachedUserSnapshot
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot, // object, not encrypted string
    }
    const signature = signSync(payload, mockSigningKey)
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("starts with null user when no signing key is present (initFn early return)", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: { id: testUser.id } as unknown as CachedUserSnapshot,
    }
    const signature = signSync(payload, mockSigningKey)
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    // No signing key → initFn returns null at the `if (!signingKey) return null`
    // guard before even reading the envelope.
    const { result } = renderProfileSync({ signingKey: null })

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("starts with null user for a version-mismatched envelope", async () => {
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION - 1, // stale version
      expiresAt: Date.now() + 60_000,
      data: { id: testUser.id } as unknown as CachedUserSnapshot,
    }
    const signature = signSync(payload as CacheSignaturePayload, mockSigningKey)
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("starts with null user for an expired envelope", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() - 1, // expired
      data: { id: testUser.id } as unknown as CachedUserSnapshot,
    }
    const signature = signSync(payload, mockSigningKey)
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("starts with null user for a tampered-signature envelope", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: { id: testUser.id } as unknown as CachedUserSnapshot,
    }
    localStorage.setItem(
      PROFILE_CACHE_STORAGE_KEY,
      JSON.stringify({ ...payload, signature: "tampered" })
    )

    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(result.current.loading).toBe(false))
  })
})

// ===========================================================================
// Auto-fetch effect (lines 957-1093)
// ===========================================================================

describe("useProfileSync — auto-fetch effect", () => {
  it("fetches /users/me and pushes the result into user state (happy path)", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it("invokes handleUnauthorized on a 401 (clears user state)", async () => {
    const updateKey = vi.fn((..._a: unknown[]) => {})
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.reject({ isAxiosError: true, response: { status: 401 } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({
      signingKey: mockSigningKey,
      updateSessionSigningKey: updateKey,
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    // 401 → handleUnauthorized → updateSessionSigningKey(null) + clear user.
    expect(updateKey).toHaveBeenCalledWith(null)
    expect(result.current.user).toBeNull()
  })

  it("logs but does not clear on a non-401 server error (e.g. 500)", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        // Pre-seed envelope present so the 500 path inside fetchCurrentUser
        // retries once; both reject so the outer catch runs the logError path.
        return Promise.reject({ isAxiosError: true, response: { status: 503 } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result, updateSessionSigningKey } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.loading).toBe(false))
    // Non-401 → no unauthorized handling; key untouched, user stays null.
    expect(updateSessionSigningKey).not.toHaveBeenCalledWith(null)
  })

  it("ensureSessionSigningKey rejection does not break the fetch (warning path)", async () => {
    const ensure = vi.fn(async () => {
      throw new Error("key fetch failed")
    })
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({
      signingKey: mockSigningKey,
      ensureSessionSigningKey: ensure,
    })

    // Even though ensureSessionSigningKey throws, the user is still set.
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    expect(ensure).toHaveBeenCalled()
  })

  it("consumes a pre-populated query cache without re-fetching (bridge)", async () => {
    const queryClient = createQueryClient()
    queryClient.setQueryData(currentUserQueryKey, testUser)

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(
      () => {
        const signingKeyRef = useRef<string | null>(mockSigningKey) as MutableRefObject<
          string | null
        >
        const promiseRef = useRef<Promise<string | null> | null>(null) as MutableRefObject<Promise<
          string | null
        > | null>
        return useProfileSync(
          vi.fn((..._a: unknown[]) => {}),
          signingKeyRef,
          promiseRef,
          vi.fn(async () => mockSigningKey)
        )
      },
      { wrapper }
    )

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(0)

    queryClient.clear()
  })
})

// ===========================================================================
// handleUnauthorized + clearProfile + setUser (lines 785-860)
// ===========================================================================

describe("useProfileSync — handleUnauthorized / clearProfile / setUser", () => {
  it("setUser populates the query cache and user state", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result, queryClient } = renderProfileSync({ signingKey: mockSigningKey })

    // Let the auto-fetch effect settle first so it cannot overwrite our
    // setUser call afterwards.
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      result.current.setUser({ ...testUser, full_name: "Renamed" } as any)
    })

    expect(result.current.user?.full_name).toBe("Renamed")
    expect((queryClient.getQueryData(currentUserQueryKey) as any)?.full_name).toBe("Renamed")
  })

  it("handleUnauthorized clears the key, the user, and pending MFA", async () => {
    const updateKey = vi.fn((..._a: unknown[]) => {})
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({
      signingKey: mockSigningKey,
      updateSessionSigningKey: updateKey,
    })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    await act(async () => {
      result.current.handleUnauthorized({ broadcast: false })
    })

    expect(updateKey).toHaveBeenCalledWith(null)
    expect(result.current.user).toBeNull()
    expect(result.current.pendingMfa).toBeNull()
  })

  it("updatePendingMfa sets and then clears the pending challenge", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    const challenge = {
      ticket: "t-1",
      methods: ["totp"],
      expiresAt: Date.now() + 60_000,
    } as any

    await act(async () => {
      result.current.updatePendingMfa(challenge, { broadcast: false })
    })
    expect(result.current.pendingMfa).toEqual(challenge)

    await act(async () => {
      result.current.updatePendingMfa(null, { broadcast: false })
    })
    expect(result.current.pendingMfa).toBeNull()
  })

  it("setAuthOperation toggles the combined loading flag", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      result.current.setAuthOperation(true)
    })
    expect(result.current.loading).toBe(true)
    expect(result.current.authOperation).toBe(true)
  })
})

// ===========================================================================
// Cross-tab sync — storage event + BroadcastChannel (lines 869-951)
// ===========================================================================

describe("useProfileSync — cross-tab sync effect", () => {
  it("a storage event for a deleted cache clears the user state", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    // Removing the cache + firing a storage event triggers syncFromCache,
    // which finds no envelope and clears the user.
    act(() => {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          newValue: null,
          storageArea: localStorage,
        })
      )
    })

    await waitFor(() => expect(result.current.user).toBeNull())
  })

  it("ignores storage events for unrelated keys", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "some.unrelated.key",
          newValue: "x",
          storageArea: localStorage,
        })
      )
    })

    // Unrelated key → no syncFromCache → user unchanged.
    expect(result.current.user?.id).toBe(testUser.id)
  })

  it("a BroadcastChannel 'unauthorized' message clears the user state", async () => {
    const updateKey = vi.fn((..._a: unknown[]) => {})
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({
      signingKey: mockSigningKey,
      updateSessionSigningKey: updateKey,
    })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    // Post an 'unauthorized' message from a sibling tab → onBroadcastMessage
    // → handleUnauthorized({ broadcast:false, persist:false }).
    await act(async () => {
      const channel = new BroadcastChannel("ecosystem.profile.sync")
      channel.postMessage({ type: "unauthorized" })
      channel.close()
      // Let the message dispatch microtask settle.
      await new Promise((r) => setTimeout(r, 0))
    })

    await waitFor(() => expect(result.current.user).toBeNull())
  })

  it("a BroadcastChannel 'mfa-pending' message surfaces the pending challenge", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    const payload = { ticket: "broadcast-ticket", methods: ["totp"] } as any
    await act(async () => {
      const channel = new BroadcastChannel("ecosystem.profile.sync")
      channel.postMessage({ type: "mfa-pending", payload })
      channel.close()
      await new Promise((r) => setTimeout(r, 0))
    })

    await waitFor(() => expect(result.current.pendingMfa).toEqual(payload))
  })

  it("a BroadcastChannel 'mfa-cleared' message clears the pending challenge", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    // First set a pending challenge locally.
    const payload = { ticket: "t-1", methods: ["totp"] } as any
    await act(async () => {
      result.current.updatePendingMfa(payload, { broadcast: false })
    })
    expect(result.current.pendingMfa).toEqual(payload)

    // Then a sibling tab clears it.
    await act(async () => {
      const channel = new BroadcastChannel("ecosystem.profile.sync")
      channel.postMessage({ type: "mfa-cleared" })
      channel.close()
      await new Promise((r) => setTimeout(r, 0))
    })

    await waitFor(() => expect(result.current.pendingMfa).toBeNull())
  })

  it("ignores malformed BroadcastChannel messages", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderProfileSync({ signingKey: mockSigningKey })

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    await act(async () => {
      const channel = new BroadcastChannel("ecosystem.profile.sync")
      channel.postMessage(null)
      channel.postMessage({ noType: true })
      channel.close()
      await new Promise((r) => setTimeout(r, 0))
    })

    // Malformed messages are ignored → user untouched.
    expect(result.current.user?.id).toBe(testUser.id)
  })
})

// ===========================================================================
// signPayload — round-trips against an externally-built signature
// (locks the encrypt+sign+persist invariant the hook relies on)
// ===========================================================================

describe("signPayload parity with the cached-bootstrap signature", () => {
  it("async signPayload matches the noble HMAC used to seed the cache", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: 1_700_000_000_000,
      data: { id: "u-1" } as unknown as CachedUserSnapshot,
    }
    const fromHook = await signPayload(payload, mockSigningKey)
    const external = signSync(payload, mockSigningKey)
    expect(fromHook).toBe(external)
  })
})
