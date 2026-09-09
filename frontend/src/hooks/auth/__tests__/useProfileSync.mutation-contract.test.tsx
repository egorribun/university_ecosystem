import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { MutableRefObject, PropsWithChildren } from "react"
import { QueryClientProvider } from "@tanstack/react-query"
import { hmac } from "@noble/hashes/hmac.js"
import { sha256 } from "@noble/hashes/sha2.js"
import { utf8ToBytes } from "@noble/hashes/utils.js"
import { AxiosError } from "axios"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { testUser } from "@/tests/mocks/handlers"
import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  buildLhciMockUser,
  fetchCurrentUser,
  isProfileSyncBrowserRuntime,
  useProfileSync,
  type CacheSignaturePayload,
  type CachedUserSnapshot,
} from "@/hooks/auth/useProfileSync"

const PROFILE_CACHE_VERSION_KEY = "ecosystem.profile.cache.version"
const signingKey = "mutation-contract-signing-key"

const bytesToBase64 = (bytes: Uint8Array): string => {
  let binary = ""
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index]!)
  }
  return btoa(binary)
}

const signEnvelope = (payload: CacheSignaturePayload): string =>
  bytesToBase64(hmac(sha256, utf8ToBytes(signingKey), utf8ToBytes(JSON.stringify(payload))))

const snapshot = (id = "cached-user"): CachedUserSnapshot =>
  ({
    id,
    full_name: "Cached User",
    group_id: null,
    avatar_url: null,
    cover_url: null,
    is_active: true,
    spotify_connected: false,
  }) as CachedUserSnapshot

const renderProfile = (
  key: string | null = signingKey,
  queryOutcome: { value?: unknown; error?: unknown } = {}
) => {
  const queryClient = createQueryClient()
  const fetchQuery = vi.spyOn(queryClient, "fetchQuery")
  if ("error" in queryOutcome) {
    fetchQuery.mockRejectedValue(queryOutcome.error)
  } else if ("value" in queryOutcome) {
    fetchQuery.mockResolvedValue(queryOutcome.value as never)
  } else {
    fetchQuery.mockReturnValue(new Promise(() => undefined) as never)
  }
  const signingKeyRef = { current: key } as MutableRefObject<string | null>
  const signingKeyPromiseRef = { current: null } as MutableRefObject<Promise<string | null> | null>
  const updateSessionSigningKey = vi.fn()
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const view = renderHook(
    () =>
      useProfileSync(
        updateSessionSigningKey,
        signingKeyRef,
        signingKeyPromiseRef,
        vi.fn(async () => key)
      ),
    { wrapper }
  )
  return { ...view, queryClient, fetchQuery, updateSessionSigningKey }
}

describe("useProfileSync mutation contracts", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it.each([
    ["document", { location: {} }],
    ["location", { document: {} }],
    ["document and location", {}],
  ])("rejects a browser runtime without %s", (_missing, windowValue) => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", windowValue)

    try {
      expect(isProfileSyncBrowserRuntime()).toBe(false)
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("keeps the LHCI identity deterministic on the first render and skips the API", () => {
    vi.stubEnv("VITE_LHCI", "true")
    const { result, queryClient, unmount } = renderProfile(null)

    expect(result.current.user).toEqual(buildLhciMockUser())
    expect(result.current.user).toMatchObject({
      id: "lhci-mock-user",
      role: "student",
      email: "",
      is_active: true,
      mfa_required: false,
    })
    expect(queryClient.fetchQuery).not.toHaveBeenCalled()
    unmount()
  })

  it.each([
    ["exactly at", 0, true],
    ["one millisecond after", 1, false],
  ])("honors the cache expiry boundary (%s expiry)", async (_label, offset, expired) => {
    const now = 1_800_000_000_000
    vi.spyOn(Date, "now").mockReturnValue(now)
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: now + offset,
      data: snapshot("expiry-boundary-user"),
    }
    localStorage.setItem(
      PROFILE_CACHE_STORAGE_KEY,
      JSON.stringify({ ...payload, signature: signEnvelope(payload) })
    )
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))

    const { result, unmount } = renderProfile()
    if (expired) {
      expect(result.current.user).toBeNull()
      await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    } else {
      expect(result.current.user?.id).toBe("expiry-boundary-user")
      expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).not.toBeNull()
    }
    unmount()
  })

  it("fails closed for a signed envelope with null data instead of constructing a user", async () => {
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: null,
    } as unknown as CacheSignaturePayload
    localStorage.setItem(
      PROFILE_CACHE_STORAGE_KEY,
      JSON.stringify({ ...payload, signature: signEnvelope(payload) })
    )
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))

    const { result, unmount } = renderProfile()
    expect(result.current.user).toBeNull()
    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    unmount()
  })

  it.each(["", "00:00:%%%", "salt:iv"])(
    "clears a signed but malformed encrypted cache payload (%s)",
    async (data) => {
      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + 60_000,
        data,
      }
      localStorage.setItem(
        PROFILE_CACHE_STORAGE_KEY,
        JSON.stringify({ ...payload, signature: signEnvelope(payload) })
      )
      localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))

      const { result, unmount } = renderProfile()
      await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
      expect(result.current.user?.id).toBe("-1")
      unmount()
    }
  )

  it("clears the complete auth state without broadcasting when logout is local", async () => {
    const { result, updateSessionSigningKey, unmount } = renderProfile(null, { value: testUser })
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))

    const pending = { ticket: "logout-ticket", methods: ["totp"] } as never
    await act(async () => {
      result.current.updatePendingMfa(pending, { broadcast: false })
    })
    expect(result.current.pendingMfa).toEqual(pending)

    await act(async () => {
      result.current.handleUnauthorized({ broadcast: false, persist: false })
    })

    expect(result.current.user).toBeNull()
    expect(result.current.pendingMfa).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(updateSessionSigningKey).toHaveBeenCalledWith(null)
    unmount()
  })

  it("handles a cookie-backed 401 by revoking local state and settling loading", async () => {
    const unauthorized = { isAxiosError: true, response: { status: 401 } }
    const { result, updateSessionSigningKey, unmount } = renderProfile(null, {
      error: unauthorized,
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(updateSessionSigningKey).toHaveBeenCalledWith(null)
    unmount()
  })

  it("silently settles a cancelled auto-fetch without invoking logout", async () => {
    const { result, updateSessionSigningKey, unmount } = renderProfile(null, {
      error: { __CANCEL__: true },
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(updateSessionSigningKey).not.toHaveBeenCalled()
    unmount()
  })

  it("broadcasts only real pending-MFA state transitions", async () => {
    const channels: Array<{
      postMessage: ReturnType<typeof vi.fn>
      addEventListener: ReturnType<typeof vi.fn>
      removeEventListener: ReturnType<typeof vi.fn>
      close: ReturnType<typeof vi.fn>
    }> = []
    class FakeBroadcastChannel {
      postMessage = vi.fn()
      addEventListener = vi.fn()
      removeEventListener = vi.fn()
      close = vi.fn()

      constructor(_name: string) {
        channels.push(this)
      }
    }
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel)

    const { result, unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
    })
    expect(channels).toHaveLength(1) // the inbound subscription

    await act(async () => {
      result.current.updatePendingMfa(null)
    })
    expect(channels).toHaveLength(1) // null -> null is a no-op

    const pending = { ticket: "mutation-ticket", methods: ["totp"] } as never
    await act(async () => {
      result.current.updatePendingMfa(pending)
    })
    await act(async () => {
      result.current.updatePendingMfa(null)
    })

    const posted = channels.flatMap((channel) => channel.postMessage.mock.calls)
    expect(posted).toEqual([[{ type: "mfa-pending", payload: pending }], [{ type: "mfa-cleared" }]])
    unmount()
  })

  it("treats DEL (0x7f) as ASCII and preserves the cache envelope header", async () => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "\u007f")
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as never)

    await expect(fetchCurrentUser()).resolves.toEqual(testUser)

    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(getSpy.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        headers: { "X-Profile-Cache-Envelope": "\u007f" },
        skipRateLimitQueue: true,
      })
    )
  })

  it("rejects the first non-ASCII byte and clears the envelope before requesting", async () => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "\u0080")
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as never)

    await expect(fetchCurrentUser()).resolves.toEqual(testUser)

    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(getSpy.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        headers: undefined,
        skipRateLimitQueue: true,
      })
    )
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBeNull()
  })

  it("does not retry a cached request when an Axios network error has no response", async () => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "cache-envelope")
    const networkError = new AxiosError("network unavailable", "ERR_NETWORK")
    const getSpy = vi.spyOn(api, "get").mockRejectedValue(networkError)

    await expect(fetchCurrentUser()).rejects.toBe(networkError)

    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBe("cache-envelope")
  })
})
