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
import * as logger from "@/app/logger"
import { testUser } from "@/tests/mocks/handlers"
import { withExpectedConsole } from "@/tests/strictConsole"
import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  buildSsrStubUser,
  buildLhciMockUser,
  createOptimisticUser,
  encryptData,
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

const writeSignedEnvelope = (payload: CacheSignaturePayload, signature = signEnvelope(payload)) => {
  localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ ...payload, signature }))
  localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
}

const writeEncryptedEnvelope = async (
  data: CachedUserSnapshot,
  overrides: Partial<CacheSignaturePayload> = {}
): Promise<CacheSignaturePayload> => {
  const encrypted = await encryptData(data, signingKey)
  expect(encrypted).toEqual(expect.any(String))
  const payload = {
    version: PROFILE_CACHE_SCHEMA_VERSION,
    expiresAt: Date.now() + 60_000,
    data: encrypted as string,
    ...overrides,
  } as CacheSignaturePayload
  writeSignedEnvelope(payload)
  return payload
}

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

  it("keeps the SSR stub defaults non-sensitive and deterministic", () => {
    expect(buildSsrStubUser("teacher")).toMatchObject({
      id: "ssr-stub",
      role: "teacher",
      full_name: "",
      spotify_connected: false,
      totp_enrollments: [],
    })
  })

  it("keeps the LHCI synthetic profile defaults stable", () => {
    expect(buildLhciMockUser()).toMatchObject({
      id: "lhci-mock-user",
      full_name: "LHCI Test User",
      spotify_connected: false,
      totp_enrollments: [],
    })
  })

  it("keeps optimistic-user construction restricted to object snapshots", () => {
    expect(createOptimisticUser(snapshot("valid-optimistic-user")).id).toBe("valid-optimistic-user")
    expect(() => createOptimisticUser(42 as unknown as CachedUserSnapshot)).toThrow(
      "Profile cache snapshot must be an object"
    )
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

      const verify = async () => {
        const { result, unmount } = renderProfile()
        await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
        expect(result.current.user?.id).toBe("-1")
        unmount()
      }
      if (data === "00:00:%%%") {
        await withExpectedConsole("warn", "profile_cache.decryption_failed", verify)
      } else {
        await verify()
      }
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

  it("does not retry an Axios response error when no cache envelope exists", async () => {
    const responseError = { isAxiosError: true, response: { status: 503 } }
    const getSpy = vi.spyOn(api, "get").mockRejectedValue(responseError)

    await expect(fetchCurrentUser()).rejects.toBe(responseError)

    expect(getSpy).toHaveBeenCalledTimes(1)
  })

  it("restores a valid encrypted snapshot while the authoritative request is pending", async () => {
    await writeEncryptedEnvelope(snapshot("encrypted-cache-user"))

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() => expect(result.current.user?.id).toBe("encrypted-cache-user"))
    unmount()
  })

  it("preserves encrypted key material when parsing odd-length hex segments", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "abc:def:AA==",
    }
    writeSignedEnvelope(payload)
    const deriveKeySpy = vi
      .spyOn(window.crypto.subtle, "deriveKey")
      .mockResolvedValue({} as CryptoKey)
    const decryptSpy = vi
      .spyOn(window.crypto.subtle, "decrypt")
      .mockResolvedValue(
        new TextEncoder().encode(JSON.stringify(snapshot("parsed-hex-user"))).buffer
      )

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() => expect(result.current.user?.id).toBe("parsed-hex-user"))
    const algorithm = deriveKeySpy.mock.calls[0]?.[0] as unknown as { salt: Uint8Array }
    expect(Array.from(algorithm.salt)).toEqual([0xab, 0x0c])
    expect(deriveKeySpy.mock.calls[0]?.[3]).toBe(false)
    const decryptAlgorithm = decryptSpy.mock.calls[0]?.[0] as unknown as { iv: Uint8Array }
    expect(Array.from(decryptAlgorithm.iv)).toEqual([0xde, 0x0f])
    unmount()
  })

  it("fails closed when encrypted cache key material cannot be imported", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "000102:030405:AA==",
    }
    writeSignedEnvelope(payload)
    const originalImportKey = window.crypto.subtle.importKey.bind(window.crypto.subtle)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")
    importKeySpy.mockImplementationOnce((...args) => originalImportKey(...args))
    importKeySpy.mockResolvedValueOnce(null as never)
    const deriveKeySpy = vi.spyOn(window.crypto.subtle, "deriveKey")
    const decryptSpy = vi.spyOn(window.crypto.subtle, "decrypt")
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(result.current.user?.id).not.toBe("parsed-hex-user")
    expect(deriveKeySpy).not.toHaveBeenCalled()
    expect(decryptSpy).not.toHaveBeenCalled()
    unmount()
  })

  it("does not decrypt when encrypted cache key derivation fails", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "000102:030405:AA==",
    }
    writeSignedEnvelope(payload)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue(null as never)
    const decryptSpy = vi
      .spyOn(window.crypto.subtle, "decrypt")
      .mockResolvedValue(
        new TextEncoder().encode(JSON.stringify(snapshot("derived-key-user"))).buffer
      )
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(result.current.user?.id).not.toBe("derived-key-user")
    expect(decryptSpy).not.toHaveBeenCalled()
    unmount()
  })

  it("rejects an encrypted payload with extra segments before importing its key", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "aa:bb:ZmFr:extra",
    }
    writeSignedEnvelope(payload)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")

    const { unmount } = renderProfile(signingKey)

    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    // The one import belongs to HMAC envelope verification. A malformed
    // encrypted payload must not proceed to PBKDF2 key import.
    expect(importKeySpy).toHaveBeenCalledTimes(1)
    unmount()
  })

  it("short-circuits encrypted-cache parsing when Web Crypto is unavailable", async () => {
    const payload = await writeEncryptedEnvelope(snapshot("no-crypto-cache-user"))
    const splitSpy = vi.spyOn(String.prototype, "split")
    const originalSubtle = window.crypto.subtle
    let subtleReads = 0
    vi.spyOn(window.crypto, "subtle", "get").mockImplementation(() => {
      subtleReads += 1
      return (subtleReads === 1 ? originalSubtle : undefined) as SubtleCrypto
    })

    const { unmount } = renderProfile(signingKey)

    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    // One read verifies the HMAC envelope; the second is the decrypt guard.
    // No parser/import work is allowed after that guard returns null.
    expect(subtleReads).toBe(2)
    expect(splitSpy.mock.instances.some((instance) => instance === payload.data)).toBe(false)
    unmount()
  })

  it.each([":bb:ZmFr", "aa::ZmFr"])(
    "does not derive or decrypt when an encrypted cache segment is empty (%s)",
    async (data) => {
      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + 60_000,
        data,
      }
      writeSignedEnvelope(payload)
      const deriveKeySpy = vi.spyOn(window.crypto.subtle, "deriveKey")
      const decryptSpy = vi.spyOn(window.crypto.subtle, "decrypt")
      const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

      const { unmount } = renderProfile(signingKey)

      await waitFor(() =>
        expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
          reason: "invalid_data",
        })
      )
      expect(deriveKeySpy).not.toHaveBeenCalled()
      expect(decryptSpy).not.toHaveBeenCalled()
      unmount()
    }
  )

  it("clears cache through the no-key path without attempting cryptography", async () => {
    await writeEncryptedEnvelope(snapshot("no-key-cache-user"))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")

    const { unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          storageArea: localStorage,
        })
      )
    })

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", { reason: "parse_error" })
    )
    expect(importKeySpy).not.toHaveBeenCalled()
    unmount()
  })

  it("evicts a stale signed envelope before restoring its snapshot", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION - 1,
      expiresAt: Date.now() + 60_000,
      data: snapshot("stale-cache-user"),
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "version_mismatch",
      })
    )
    expect(result.current.user?.id).not.toBe("stale-cache-user")
    unmount()
  })

  it("rejects a validly signed encrypted envelope with a non-numeric expiry", async () => {
    const encrypted = await encryptData(snapshot("invalid-expiry-user"), signingKey)
    expect(encrypted).toEqual(expect.any(String))
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: String(Date.now() + 60_000),
      data: encrypted as string,
    } as unknown as CacheSignaturePayload
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(result.current.user?.id).not.toBe("invalid-expiry-user")
    unmount()
  })

  it("rejects a non-string signature before Web Crypto verification", async () => {
    const encrypted = await encryptData(snapshot("invalid-signature-type-user"), signingKey)
    expect(encrypted).toEqual(expect.any(String))
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: encrypted as string,
    }
    writeSignedEnvelope(payload, 123 as unknown as string)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(importKeySpy).not.toHaveBeenCalled()
    unmount()
  })

  it("reports the exact expiry reason when a cache reaches its boundary", async () => {
    const now = 1_800_000_000_000
    vi.spyOn(Date, "now").mockReturnValue(now)
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: now,
      data: snapshot("expired-cache-user"),
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", { reason: "expired" })
    )
    unmount()
  })

  it("reports the exact invalid-signature reason for a tampered envelope", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("tampered-cache-user"),
    }
    writeSignedEnvelope(payload, "tampered")
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    unmount()
  })

  it("rejects an encrypted snapshot whose decrypted id is not a string", async () => {
    const invalidSnapshot = {
      ...snapshot("invalid-decrypted-id"),
      id: 42,
    } as unknown as CachedUserSnapshot
    await writeEncryptedEnvelope(invalidSnapshot)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(result.current.user?.id).not.toBe(42)
    unmount()
  })

  it("rejects a truthy primitive received through cross-tab cache sync", async () => {
    const { result, unmount } = renderProfile(signingKey)
    await act(async () => {
      await Promise.resolve()
    })

    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: 42,
    } as unknown as CacheSignaturePayload
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const serialized = JSON.stringify({ ...payload, signature: signEnvelope(payload) })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, serialized)
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          newValue: serialized,
        })
      )
    })

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(result.current.user).toBeNull()
    unmount()
  })

  it("fails closed when synchronous signature verification throws", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("sync-verifier-error-user"),
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    vi.spyOn(TextEncoder.prototype, "encode").mockImplementation(() => {
      throw new Error("encoder unavailable")
    })

    const { result, unmount } = renderProfile(signingKey)

    expect(result.current.user).toBeNull()
    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(warningSpy).not.toHaveBeenCalledWith("profile_cache.cleared", {
      reason: "parse_error",
    })
    unmount()
  })
})
