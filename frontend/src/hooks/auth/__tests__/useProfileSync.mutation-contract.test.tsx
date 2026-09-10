import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { MutableRefObject, PropsWithChildren } from "react"
import { renderToString } from "react-dom/server"
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
import type { UserState } from "@/types/Auth"
import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  buildSsrStubUser,
  buildLhciMockUser,
  createOptimisticUser,
  currentUserQueryKey,
  decryptData,
  encryptData,
  getCachedEnvelopeHeader,
  areDeepEqual,
  fetchCurrentUser,
  isAscii,
  isProfileSyncBrowserRuntime,
  isCachedSnapshotObject,
  migrateProfileCache,
  persistUserToCacheAsync,
  readCachedUserAsync,
  resolveInitialInitializingState,
  resolveInitialUserState,
  resolveSsrInitialInitializing,
  resolveSsrInitialUserState,
  verifyHmacAsync,
  useProfileSync,
  type CacheSignaturePayload,
  type CachedUserSnapshot,
  type SsrAuthHint,
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

const signEnvelopeForKey = (payload: CacheSignaturePayload, key: string): string =>
  bytesToBase64(hmac(sha256, utf8ToBytes(key), utf8ToBytes(JSON.stringify(payload))))

const signEnvelope = (payload: CacheSignaturePayload): string =>
  signEnvelopeForKey(payload, signingKey)

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

  it("renders deterministic LHCI and SSR loading states before effects can run", () => {
    vi.stubEnv("VITE_LHCI", "true")
    const Probe = ({ hint }: { hint?: SsrAuthHint }) => {
      const state = useProfileSync(
        vi.fn(),
        { current: null },
        { current: null },
        vi.fn(async () => null),
        hint
      )
      return <output>{`${state.user?.id ?? "none"}:${state.loading}`}</output>
    }

    const lhciHtml = renderToString(
      <QueryClientProvider client={createQueryClient()}>
        <Probe />
      </QueryClientProvider>
    )
    expect(lhciHtml).toContain("lhci-mock-user:false")

    vi.stubEnv("VITE_LHCI", "false")
    const authenticatedSsrHtml = renderToString(
      <QueryClientProvider client={createQueryClient()}>
        <Probe hint={{ isAuth: true, user: { role: "teacher" } }} />
      </QueryClientProvider>
    )
    const anonymousSsrHtml = renderToString(
      <QueryClientProvider client={createQueryClient()}>
        <Probe hint={{ isAuth: false, user: null }} />
      </QueryClientProvider>
    )
    expect(authenticatedSsrHtml).toContain("ssr-stub:false")
    expect(anonymousSsrHtml).toContain("none:true")
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

  it.each([
    ["no hint", undefined, null],
    ["anonymous hint", { isAuth: false, user: null }, null],
    ["authenticated hint without user", { isAuth: true, user: null }, null],
    ["authenticated teacher hint", { isAuth: true, user: { role: "teacher" } }, "teacher"],
    ["authenticated unknown-role hint", { isAuth: true, user: { role: "unknown" } }, "student"],
  ] as const)("resolves SSR initial user for %s", (_label, hint, expectedRole) => {
    const resolved = resolveSsrInitialUserState(hint)
    if (expectedRole === null) {
      expect(resolved).toBeNull()
    } else {
      expect(resolved).toMatchObject({ id: "ssr-stub", role: expectedRole })
    }
  })

  it.each([
    ["no hint", undefined, true],
    ["anonymous hint", { isAuth: false, user: null }, true],
    ["authenticated hint", { isAuth: true, user: { role: "student" } }, false],
  ] as const)("resolves SSR initializing state for %s", (_label, hint, expected) => {
    expect(resolveSsrInitialInitializing(hint)).toBe(expected)
  })

  it.each([
    ["LHCI", { lhci: true, isServer: false, signingKey: null }, "lhci-mock-user"],
    [
      "authenticated SSR",
      {
        lhci: false,
        isServer: true,
        signingKey: null,
        ssrAuthHint: { isAuth: true, user: { role: "teacher" } },
      },
      "ssr-stub",
    ],
    [
      "anonymous SSR",
      { lhci: false, isServer: true, signingKey: null, ssrAuthHint: { isAuth: false, user: null } },
      null,
    ],
    [
      "authenticated hydration hint",
      {
        lhci: false,
        isServer: false,
        signingKey: null,
        ssrAuthHint: { isAuth: true, user: { role: "student" } },
      },
      "ssr-stub",
    ],
    ["missing signing key", { lhci: false, isServer: false, signingKey: null }, null],
  ] as const)("resolves initial user for %s", (_label, options, expectedId) => {
    const resolved = resolveInitialUserState(options)
    expect(resolved?.id ?? null).toBe(expectedId)
  })

  it("does not consult a signed cache during an anonymous server render", () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("server-cache-user"),
    }
    writeSignedEnvelope(payload)
    const serialized = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)

    expect(
      resolveInitialUserState({
        lhci: false,
        isServer: true,
        signingKey,
        ssrAuthHint: { isAuth: false, user: null },
      })
    ).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBe(serialized)
  })

  it.each([
    ["empty", ""],
    ["null", null],
  ] as const)("refuses to hydrate a valid signed cache with a %s signing key", (_label, key) => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("missing-signing-key-cache-user"),
    }
    // The empty-key case is signed with the empty key; the null-key case is
    // signed with the normal key and must still fail closed before verifying.
    writeSignedEnvelope(payload, signEnvelopeForKey(payload, key ?? signingKey))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey: key })).toBeNull()
    expect(warningSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).not.toBeNull()
  })

  it("returns no user for a cold client cache", () => {
    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
  })

  it("does not retry cache reads when localStorage is unavailable", () => {
    const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: () => {
        throw new Error("private browsing")
      },
    })

    try {
      expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
      expect(warningSpy).toHaveBeenCalledTimes(1)
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.storage_unavailable")
    } finally {
      if (storageDescriptor) Object.defineProperty(globalThis, "localStorage", storageDescriptor)
    }
  })

  it.each([
    ["an array", Object.assign([], { id: "array-cache-user" })],
    ["a function", Object.assign(() => undefined, { id: "function-cache-user" })],
  ] as const)(
    "rejects a %s returned by the async cache parser even when it has an id",
    async (_label, data) => {
      localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "malformed-runtime-boundary")
      vi.spyOn(JSON, "parse").mockReturnValue({
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + 60_000,
        data,
        signature: btoa("x".repeat(32)),
      } as never)
      vi.spyOn(window.crypto.subtle, "verify").mockResolvedValue(true)

      await expect(readCachedUserAsync(signingKey)).resolves.toBeUndefined()
      expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    }
  )

  it.each([
    ["a schema mismatch", PROFILE_CACHE_SCHEMA_VERSION - 1, Date.now() + 60_000],
    ["an expired envelope", PROFILE_CACHE_SCHEMA_VERSION, Date.now() - 1],
  ] as const)("rejects %s before synchronous cache hydration", (_label, version, expiresAt) => {
    const payload: CacheSignaturePayload = {
      version,
      expiresAt,
      data: snapshot("rejected-bootstrap-cache-user"),
    }
    writeSignedEnvelope(payload)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
  })

  it("hydrates a valid signed legacy snapshot synchronously", () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("synchronous-legacy-cache-user"),
    }
    writeSignedEnvelope(payload)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toMatchObject({
      id: "synchronous-legacy-cache-user",
      role: "student",
      email: "",
      is_active: false,
    })
  })

  it.each([
    ["exactly at", 0, null],
    ["one millisecond after", 1, "synchronous-expiry-boundary-user"],
  ] as const)(
    "applies the synchronous cache expiry boundary (%s)",
    (_label, offset, expectedId) => {
      const now = 1_800_000_000_000
      vi.spyOn(Date, "now").mockReturnValue(now)
      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: now + offset,
        data: snapshot("synchronous-expiry-boundary-user"),
      }
      writeSignedEnvelope(payload)

      expect(
        resolveInitialUserState({ lhci: false, isServer: false, signingKey })?.id ?? null
      ).toBe(expectedId)
    }
  )

  it("returns a minimal placeholder for a valid encrypted envelope", () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "encrypted-cache-payload",
    }
    writeSignedEnvelope(payload)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toMatchObject({
      id: "-1",
      role: "student",
      email: "",
      is_active: false,
    })
  })

  it("seeds the query cache from a legacy snapshot but never from the encrypted placeholder", async () => {
    const legacyPayload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("legacy-query-cache-user"),
    }
    writeSignedEnvelope(legacyPayload)

    const legacy = renderProfile(signingKey)
    expect(legacy.result.current.user?.id).toBe("legacy-query-cache-user")
    expect(legacy.queryClient.getQueryData<UserState>(currentUserQueryKey)?.id).toBe(
      "legacy-query-cache-user"
    )
    legacy.unmount()

    const encryptedPayload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "encrypted-cache-placeholder",
    }
    writeSignedEnvelope(encryptedPayload)

    const encrypted = renderProfile(signingKey)
    expect(encrypted.result.current.user?.id).toBe("-1")
    expect(encrypted.queryClient.getQueryData<UserState>(currentUserQueryKey)).toBeUndefined()
    await act(async () => {
      await Promise.resolve()
    })
    expect(encrypted.queryClient.getQueryData<UserState>(currentUserQueryKey)).toBeUndefined()
    encrypted.unmount()
  })

  it("clears a signed legacy snapshot with an invalid id", () => {
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: { ...snapshot("invalid-synchronous-id"), id: 42 },
    } as unknown as CacheSignaturePayload
    writeSignedEnvelope(payload)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
  })

  it("clears invalid non-string legacy data from the synchronous cache resolver", () => {
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: 42,
    } as unknown as CacheSignaturePayload
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
    expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
      reason: "invalid_data",
    })
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBeNull()
  })

  it("rejects a tampered synchronous cache signature", () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("tampered-synchronous-cache-user"),
    }
    writeSignedEnvelope(payload, "tampered-signature")

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
  })

  it("rejects a different-length signature in the synchronous cache resolver", () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("length-mismatch-synchronous-user"),
    }
    const validSignature = signEnvelope(payload)
    writeSignedEnvelope(payload, `${validSignature}A`)

    expect(resolveInitialUserState({ lhci: false, isServer: false, signingKey })).toBeNull()
  })

  it.each([
    ["LHCI", { lhci: true, isServer: false, userState: null }, false],
    [
      "authenticated SSR",
      {
        lhci: false,
        isServer: true,
        ssrAuthHint: { isAuth: true, user: { role: "student" } },
        userState: null,
      },
      false,
    ],
    [
      "anonymous SSR",
      { lhci: false, isServer: true, ssrAuthHint: { isAuth: false, user: null }, userState: null },
      true,
    ],
    ["hydrated user", { lhci: false, isServer: false, userState: buildLhciMockUser() }, false],
    ["cold browser", { lhci: false, isServer: false, userState: null }, true],
  ] as const)("resolves initial loading flag for %s", (_label, options, expected) => {
    expect(resolveInitialInitializingState(options)).toBe(expected)
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
    const optimisticUser = createOptimisticUser(snapshot("valid-optimistic-user"))
    expect(optimisticUser).toMatchObject({
      id: "valid-optimistic-user",
      email: "",
      role: "student",
      is_active: false,
    })
    expect(optimisticUser.totp_enrollments).toEqual([])
    expect(() => createOptimisticUser(42 as unknown as CachedUserSnapshot)).toThrow(
      "Profile cache snapshot must be an object"
    )
    expect(() => createOptimisticUser([] as unknown as CachedUserSnapshot)).toThrow(
      "Profile cache snapshot must be an object"
    )
    expect(() => createOptimisticUser(null as unknown as CachedUserSnapshot)).toThrow(
      "Profile cache snapshot must be an object"
    )
  })

  it.each([
    ["a plain object", snapshot("predicate-object"), true],
    ["null", null, false],
    ["a primitive", 42, false],
    ["an array", [], false],
    ["a function", Object.assign(() => undefined, { id: "function-snapshot" }), false],
  ] as const)("classifies %s as a cache snapshot object=%s", (_label, value, expected) => {
    expect(isCachedSnapshotObject(value)).toBe(expected)
  })

  it.each([
    ["empty", "", true],
    ["ASCII text", "Profile-Cache_123", true],
    ["DEL", "\u007f", true],
    ["leading non-ASCII", "\u0080cache", false],
    ["trailing non-ASCII", "cache\u0080", false],
    ["emoji", "cache🔒", false],
  ] as const)("classifies %s cache headers as ASCII=%s", (_label, value, expected) => {
    expect(isAscii(value)).toBe(expected)
  })

  it.each([
    ["the same primitive", "same", "same", true],
    ["different primitives", "left", "right", false],
    ["a primitive and object", "left", {}, false],
    ["an object and primitive", {}, "right", false],
    ["null and object", null, {}, false],
    ["object and null", {}, null, false],
    ["a string and record with matching enumerable keys", "0", { 0: "0" }, false],
    ["a record and string with matching enumerable keys", { 0: "0" }, "0", false],
    ["empty records", {}, {}, true],
    ["different key counts", { id: "u", role: "student" }, { id: "u" }, false],
    [
      "a record whose keys are a strict subset of the other record",
      { id: "u" },
      { id: "u", role: "student" },
      false,
    ],
    ["a missing key", { id: "u", name: "Alice" }, { id: "u", email: "a@example.test" }, false],
    ["an undefined-valued key missing from the other record", { optional: undefined }, {}, false],
    [
      "equal nested records",
      { profile: { id: "u", tags: ["one", "two"] } },
      { profile: { id: "u", tags: ["one", "two"] } },
      true,
    ],
    [
      "different nested records",
      { profile: { id: "u", tags: ["one", "two"] } },
      { profile: { id: "u", tags: ["one", "three"] } },
      false,
    ],
  ] as const)(
    "compares %s with the expected structural result",
    (_label, left, right, expected) => {
      expect(areDeepEqual(left, right)).toBe(expected)
    }
  )

  it("returns true for the same object reference", () => {
    const value = snapshot("same-reference")
    expect(areDeepEqual(value, value)).toBe(true)
  })

  it("persists only the allowlisted profile snapshot with a bounded TTL", async () => {
    const persistedUser = {
      ...testUser,
      full_name: "Persisted User",
      group_id: "group-1",
      avatar_url: "https://cdn.example.test/avatar.png",
      cover_url: "https://cdn.example.test/cover.png",
      spotify_connected: true,
      preferences: { dnd_enabled: true, timezone: "Europe/Moscow", dnd_start: null, dnd_end: null },
      is_active: true,
      mfa_required: true,
      mfa_default_method: "totp" as const,
      mfa_last_verified_at: "2026-09-10T00:00:00Z",
      totp_enrollments: [
        {
          id: "enrollment-1",
          user_id: testUser.id,
          is_active: true,
          created_at: "2026-09-01T00:00:00Z",
          label: "primary",
          confirmed_at: "2026-09-01T00:00:00Z",
          revoked_at: null,
        },
      ],
    }
    let encryptedSnapshot: unknown
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockImplementation(async (_algorithm, _key, data) => {
      encryptedSnapshot = JSON.parse(new TextDecoder().decode(data as ArrayBuffer))
      return Uint8Array.from([1, 2, 3]).buffer
    })
    vi.spyOn(window.crypto.subtle, "sign").mockResolvedValue(Uint8Array.from([4, 5, 6]).buffer)
    vi.spyOn(Date, "now").mockReturnValue(1_700_000_000_000)

    await persistUserToCacheAsync(persistedUser, signingKey)

    expect(encryptedSnapshot).toEqual({
      id: persistedUser.id,
      full_name: persistedUser.full_name,
      group_id: persistedUser.group_id,
      avatar_url: persistedUser.avatar_url,
      cover_url: persistedUser.cover_url,
      spotify_connected: persistedUser.spotify_connected,
      preferences: persistedUser.preferences,
      is_active: persistedUser.is_active,
      mfa_required: persistedUser.mfa_required,
      mfa_default_method: persistedUser.mfa_default_method,
      mfa_last_verified_at: persistedUser.mfa_last_verified_at,
      totp_enrollments: persistedUser.totp_enrollments,
    })
    expect(Object.keys(encryptedSnapshot as object)).not.toContain("email")
    expect(Object.keys(encryptedSnapshot as object)).not.toContain("role")
    expect(JSON.parse(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY) ?? "")).toMatchObject({
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: 1_700_000_300_000,
      data: expect.any(String),
      signature: expect.any(String),
    })
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
  })

  it("uses an empty enrollment list when the profile has no TOTP enrollments", async () => {
    let encryptedSnapshot: unknown
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockImplementation(async (_algorithm, _key, data) => {
      encryptedSnapshot = JSON.parse(new TextDecoder().decode(data as ArrayBuffer))
      return Uint8Array.from([1, 2, 3]).buffer
    })
    vi.spyOn(window.crypto.subtle, "sign").mockResolvedValue(Uint8Array.from([4, 5, 6]).buffer)

    const userWithoutEnrollments = {
      ...testUser,
      totp_enrollments: undefined,
    } as unknown as typeof testUser
    await persistUserToCacheAsync(userWithoutEnrollments, signingKey)

    expect(encryptedSnapshot).toMatchObject({ totp_enrollments: [] })
  })

  it.each([
    ["null value", null, signingKey],
    ["missing signing key", testUser, null],
  ] as const)(
    "clears the cache when persistence inputs are incomplete (%s)",
    async (_label, value, key) => {
      localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "stale")
      localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
      const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

      await persistUserToCacheAsync(value, key)

      expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
      expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBeNull()
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", { reason: "parse_error" })
    }
  )

  it("does not write an encrypted snapshot after the component unmounts", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    const isMounted = vi.fn(() => false)
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockResolvedValue(Uint8Array.from([1]).buffer)
    vi.spyOn(window.crypto.subtle, "sign").mockResolvedValue(Uint8Array.from([2]).buffer)

    await persistUserToCacheAsync(testUser, signingKey, isMounted)

    expect(isMounted).toHaveBeenCalledTimes(1)
    expect(setItemSpy).not.toHaveBeenCalledWith(PROFILE_CACHE_STORAGE_KEY, expect.any(String))
    expect(setItemSpy).not.toHaveBeenCalledWith(PROFILE_CACHE_VERSION_KEY, expect.any(String))
  })

  it("does not write a signed snapshot when unmount happens during signing", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    const isMounted = vi.fn().mockReturnValueOnce(true).mockReturnValueOnce(false)
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockResolvedValue(Uint8Array.from([1]).buffer)
    vi.spyOn(window.crypto.subtle, "sign").mockResolvedValue(Uint8Array.from([2]).buffer)

    await persistUserToCacheAsync(testUser, signingKey, isMounted)

    expect(isMounted).toHaveBeenCalledTimes(2)
    expect(setItemSpy).not.toHaveBeenCalledWith(PROFILE_CACHE_STORAGE_KEY, expect.any(String))
    expect(setItemSpy).not.toHaveBeenCalledWith(PROFILE_CACHE_VERSION_KEY, expect.any(String))
  })

  it("does not start cache encryption when localStorage is unavailable", async () => {
    const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: () => {
        throw new Error("private browsing")
      },
    })

    try {
      await expect(persistUserToCacheAsync(testUser, signingKey)).resolves.toBeUndefined()
      expect(importKeySpy).not.toHaveBeenCalled()
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.storage_unavailable")
    } finally {
      if (storageDescriptor) Object.defineProperty(globalThis, "localStorage", storageDescriptor)
    }
  })

  it("swallows storage failures while persisting an encrypted snapshot", async () => {
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockResolvedValue(Uint8Array.from([1]).buffer)
    vi.spyOn(window.crypto.subtle, "sign").mockResolvedValue(Uint8Array.from([2]).buffer)
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage quota exceeded")
    })

    await expect(persistUserToCacheAsync(testUser, signingKey)).resolves.toBeUndefined()
  })

  it("migrates every legacy cache key and writes the current schema marker", () => {
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, "7")
    for (const key of [
      "ecosystem.profile.cache.v1",
      "ecosystem.profile.cache.v4",
      "ecosystem.profile.cache.v5",
      "ecosystem.profile.cache.v7",
    ]) {
      localStorage.setItem(key, "legacy")
    }

    migrateProfileCache()

    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
    for (const key of [
      "ecosystem.profile.cache.v1",
      "ecosystem.profile.cache.v4",
      "ecosystem.profile.cache.v5",
      "ecosystem.profile.cache.v7",
      PROFILE_CACHE_STORAGE_KEY,
    ]) {
      expect(localStorage.getItem(key)).toBeNull()
    }
  })

  it("evicts an unknown dynamic cache key for an older schema version", () => {
    const dynamicLegacyKey = "ecosystem.profile.cache.v6"
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, "6")
    localStorage.setItem(dynamicLegacyKey, "legacy")

    migrateProfileCache()

    expect(localStorage.getItem(dynamicLegacyKey)).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
  })

  it("does not evict a dynamic cache key when the stored schema marker is empty", () => {
    const emptyVersionKey = "ecosystem.profile.cache.v"
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, "")
    localStorage.setItem(emptyVersionKey, "sentinel")

    migrateProfileCache()

    expect(localStorage.getItem(emptyVersionKey)).toBe("sentinel")
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
  })

  it("fails closed and emits only a generic diagnostic when the storage accessor throws", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: () => {
        throw new Error("private browsing")
      },
    })

    try {
      expect(getCachedEnvelopeHeader()).toBeNull()
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.storage_unavailable")
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor)
    }
  })

  it("leaves an already-current cache version untouched during migration", () => {
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "current-envelope")
    localStorage.setItem("ecosystem.profile.cache.v7", "legacy")

    migrateProfileCache()

    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBe("current-envelope")
    expect(localStorage.getItem("ecosystem.profile.cache.v7")).toBe("legacy")
  })

  it("does not emit a cache-cleared diagnostic when localStorage is unavailable", async () => {
    const originalStorage = globalThis.localStorage
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    try {
      const { result, unmount } = renderProfile(null, { value: testUser })
      await waitFor(() => expect(result.current.loading).toBe(false))
      warningSpy.mockClear()
      vi.stubGlobal("localStorage", undefined)

      act(() => {
        window.dispatchEvent(
          new StorageEvent("storage", {
            key: PROFILE_CACHE_STORAGE_KEY,
          })
        )
      })
      await waitFor(() => expect(result.current.user).toBeNull())

      expect(warningSpy).not.toHaveBeenCalledWith(
        "profile_cache.cleared",
        expect.objectContaining({ reason: "parse_error" })
      )
      unmount()
    } finally {
      vi.stubGlobal("localStorage", originalStorage)
    }
  })

  it("returns a null cache header without touching an unavailable storage object", () => {
    const originalStorage = globalThis.localStorage
    vi.stubGlobal("localStorage", undefined)

    try {
      expect(getCachedEnvelopeHeader()).toBeNull()
    } finally {
      vi.stubGlobal("localStorage", originalStorage)
    }
  })

  it("normalizes a storage read failure to a null cache header", () => {
    const storageSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("private mode")
    })

    expect(getCachedEnvelopeHeader()).toBeNull()
    storageSpy.mockRestore()
  })

  it("leaves an empty cache envelope untouched instead of treating it as malformed JSON", async () => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "")
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { fetchQuery, unmount } = renderProfile(signingKey)
    await waitFor(() => expect(fetchQuery).toHaveBeenCalled())

    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBe("")
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
    expect(warningSpy).not.toHaveBeenCalledWith("profile_cache.cleared", {
      reason: "parse_error",
    })
    unmount()
  })

  it.each([
    ["malformed JSON", "not-json"],
    ["JSON null", "null"],
    ["a JSON primitive", "42"],
  ])("clears %s with the parse_error reason", async (_label, rawEnvelope) => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, rawEnvelope)
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { unmount } = renderProfile(signingKey)
    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "parse_error",
      })
    )
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    // The migration effect restores the current schema marker after the
    // malformed envelope has been evicted.
    expect(localStorage.getItem(PROFILE_CACHE_VERSION_KEY)).toBe(
      String(PROFILE_CACHE_SCHEMA_VERSION)
    )
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

  it("fails closed for a signed legacy snapshot whose id is not a string", async () => {
    const payload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: { ...snapshot("numeric-id"), id: 42 },
    } as unknown as CacheSignaturePayload
    localStorage.setItem(
      PROFILE_CACHE_STORAGE_KEY,
      JSON.stringify({ ...payload, signature: signEnvelope(payload) })
    )
    localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile()

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
      reason: "invalid_data",
    })
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
    const errorSpy = vi.spyOn(logger, "logError").mockImplementation(() => undefined)
    const { result, updateSessionSigningKey, unmount } = renderProfile(null, {
      error: { __CANCEL__: true },
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(updateSessionSigningKey).not.toHaveBeenCalled()
    expect(errorSpy).not.toHaveBeenCalledWith("Failed to fetch current user", expect.anything())
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

    const localPending = { ticket: "local-only-ticket", methods: ["totp"] } as never
    await act(async () => {
      result.current.updatePendingMfa(localPending, { broadcast: false })
    })
    expect(result.current.pendingMfa).toEqual(localPending)
    expect(channels.flatMap((channel) => channel.postMessage.mock.calls)).toEqual([])
    await act(async () => {
      result.current.updatePendingMfa(null, { broadcast: false })
    })
    expect(channels.flatMap((channel) => channel.postMessage.mock.calls)).toEqual([])

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

  it("honors handleUnauthorized defaults and explicit broadcast/persistence options", async () => {
    const channels: Array<{ postMessage: ReturnType<typeof vi.fn> }> = []
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

    const { result, queryClient, unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
    })
    expect(channels).toHaveLength(1)
    const cancelQueriesSpy = vi.spyOn(queryClient, "cancelQueries")

    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "stale-cache")
    const pending = { ticket: "local-pending", methods: ["totp"] } as never
    await act(async () => {
      result.current.updatePendingMfa(pending, { broadcast: false })
    })

    await act(async () => {
      result.current.handleUnauthorized({ broadcast: false, persist: true })
    })

    expect(cancelQueriesSpy).toHaveBeenCalledWith({ queryKey: currentUserQueryKey })
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    expect(channels.flatMap((channel) => channel.postMessage.mock.calls)).toEqual([])

    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, "stale-cache")
    await act(async () => {
      result.current.handleUnauthorized()
    })

    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    expect(channels.flatMap((channel) => channel.postMessage.mock.calls)).toEqual([
      [{ type: "unauthorized" }],
    ])
    unmount()
  })

  it("keeps BroadcastChannel diagnostics generic while retaining the failure context", async () => {
    class ThrowingBroadcastChannel {
      constructor() {
        throw new Error("channel unavailable")
      }
    }
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    vi.stubGlobal("BroadcastChannel", ThrowingBroadcastChannel)

    const { result, unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
    })
    expect(warningSpy).toHaveBeenCalledWith(
      "Failed to subscribe to profile broadcast channel",
      expect.objectContaining({ error: expect.any(Error) })
    )
    warningSpy.mockClear()

    await act(async () => {
      result.current.updatePendingMfa({ ticket: "channel-error", methods: [] } as never)
    })

    expect(warningSpy).toHaveBeenCalledWith(
      "Failed to broadcast profile event",
      expect.objectContaining({ error: expect.any(Error) })
    )
    unmount()
  })

  it("ignores null, primitive, unknown, and payload-less broadcast messages", async () => {
    type MessageListener = (event: MessageEvent<unknown>) => void
    const listeners: MessageListener[] = []
    class DeterministicBroadcastChannel {
      addEventListener = vi.fn((_type: string, listener: EventListener) => {
        listeners.push(listener as MessageListener)
      })
      removeEventListener = vi.fn()
      postMessage = vi.fn()
      close = vi.fn()

      constructor(_name: string) {}

      emit(data: unknown) {
        for (const listener of listeners) {
          listener(new MessageEvent("message", { data }))
        }
      }
    }
    vi.stubGlobal("BroadcastChannel", DeterministicBroadcastChannel)

    const { result, unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
    })
    const channel = new DeterministicBroadcastChannel("ecosystem.profile.sync")

    await act(async () => {
      channel.emit(null)
      channel.emit(42)
      channel.emit({ noType: true })
      channel.emit({ type: "ignored" })
      channel.emit({ type: "ignored", payload: { ticket: "not-a-challenge" } })
      channel.emit({ type: "mfa-pending" })
      await Promise.resolve()
    })

    expect(result.current.pendingMfa).toBeNull()
    unmount()
  })

  it("does not echo remote profile events back to sibling tabs", async () => {
    type MessageListener = (event: MessageEvent<unknown>) => void
    const listeners: MessageListener[] = []
    const channels: Array<{
      postMessage: ReturnType<typeof vi.fn>
      addEventListener: ReturnType<typeof vi.fn>
      removeEventListener: ReturnType<typeof vi.fn>
      close: ReturnType<typeof vi.fn>
      emit: (data: unknown) => void
    }> = []
    class DeterministicBroadcastChannel {
      postMessage = vi.fn()
      addEventListener = vi.fn((_type: string, listener: EventListener) => {
        listeners.push(listener as MessageListener)
      })
      removeEventListener = vi.fn()
      close = vi.fn()

      constructor(_name: string) {
        channels.push(this)
      }

      emit(data: unknown) {
        for (const listener of listeners) listener(new MessageEvent("message", { data }))
      }
    }
    vi.stubGlobal("BroadcastChannel", DeterministicBroadcastChannel)

    const { result, unmount } = renderProfile(null)
    await act(async () => {
      await Promise.resolve()
    })
    expect(channels).toHaveLength(1)
    const inbound = channels[0]!

    const pending = { ticket: "remote-ticket", methods: ["totp"] } as never
    await act(async () => {
      inbound.emit({ type: "mfa-pending", payload: pending })
      await Promise.resolve()
    })
    expect(result.current.pendingMfa).toEqual(pending)

    await act(async () => {
      inbound.emit({ type: "mfa-cleared" })
      await Promise.resolve()
    })
    expect(result.current.pendingMfa).toBeNull()

    await act(async () => {
      inbound.emit({ type: "unauthorized" })
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.user).toBeNull())

    expect(channels.flatMap((channel) => channel.postMessage.mock.calls)).toEqual([])
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

  it("imports HMAC verification keys as non-extractable verify-only keys", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("legacy-object-cache-user"),
    }
    writeSignedEnvelope(payload)
    const importKeySpy = vi.spyOn(window.crypto.subtle, "importKey")

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() => expect(result.current.user?.id).toBe("legacy-object-cache-user"))
    await waitFor(() =>
      expect(
        importKeySpy.mock.calls.some((call) => Array.isArray(call[4]) && call[4].includes("verify"))
      ).toBe(true)
    )

    const verifyCall = importKeySpy.mock.calls.find(
      (call) => Array.isArray(call[4]) && call[4].includes("verify")
    )
    expect(verifyCall?.[3]).toBe(false)
    expect(verifyCall?.[4]).toEqual(["verify"])
    unmount()
  })

  it("converts async HMAC crypto failures into invalid-signature cache eviction", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("async-hmac-error-cache-user"),
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const importKeySpy = vi
      .spyOn(window.crypto.subtle, "importKey")
      .mockRejectedValueOnce(new Error("HMAC key import unavailable"))

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(importKeySpy).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    unmount()
  })

  it("returns an explicit false result when async HMAC verification throws", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("direct-hmac-error-user"),
    }
    vi.spyOn(window.crypto.subtle, "importKey").mockRejectedValueOnce(new Error("HMAC unavailable"))

    await expect(verifyHmacAsync(payload, signEnvelope(payload), signingKey)).resolves.toBe(false)
  })

  it("returns true for a valid async HMAC signature while Web Crypto is available", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("direct-hmac-valid-user"),
    }

    await expect(verifyHmacAsync(payload, signEnvelope(payload), signingKey)).resolves.toBe(true)
  })

  it("returns false immediately when async HMAC verification has no Web Crypto", async () => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", undefined)

    try {
      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + 60_000,
        data: snapshot("direct-hmac-no-crypto-user"),
      }

      await expect(verifyHmacAsync(payload, signEnvelope(payload), signingKey)).resolves.toBe(false)
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("does not invoke key derivation after Web Crypto disappears", async () => {
    const originalWindow = globalThis.window
    let subtleReads = 0
    const fakeSubtle = {
      importKey: vi.fn(async () => ({}) as CryptoKey),
      deriveKey: vi.fn(async () => ({}) as CryptoKey),
    } as unknown as SubtleCrypto
    const fakeWindow = {
      crypto: {
        get subtle() {
          subtleReads += 1
          return (subtleReads <= 2 ? fakeSubtle : undefined) as SubtleCrypto
        },
        getRandomValues: (bytes: Uint8Array) => bytes,
      },
    } as unknown as Window
    vi.stubGlobal("window", fakeWindow)

    try {
      await expect(encryptData(snapshot("derive-guard-user"), signingKey)).resolves.toBeNull()
      expect(subtleReads).toBeGreaterThanOrEqual(3)
      expect(fakeSubtle.deriveKey).not.toHaveBeenCalled()
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
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

  it("keeps the encryption failure diagnostic error payload intact", async () => {
    const encryptionError = new Error("encryption primitive unavailable")
    vi.spyOn(window.crypto.subtle, "importKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "deriveKey").mockResolvedValue({} as CryptoKey)
    vi.spyOn(window.crypto.subtle, "encrypt").mockRejectedValue(encryptionError)
    const errorSpy = vi.spyOn(logger, "logError").mockImplementation(() => undefined)

    await expect(encryptData(snapshot("encryption-error-user"), signingKey)).resolves.toBeNull()

    expect(errorSpy).toHaveBeenCalledWith("Encryption failed", { error: encryptionError })
  })

  it("performs encryption when Web Crypto is available", async () => {
    const encrypted = await encryptData(snapshot("direct-encryption-user"), signingKey)

    expect(encrypted).toEqual(expect.any(String))
    expect(encrypted?.split(":")).toHaveLength(3)
  })

  it("performs decryption when Web Crypto is available", async () => {
    const encrypted = await encryptData(snapshot("direct-decryption-user"), signingKey)
    expect(encrypted).toEqual(expect.any(String))

    await expect(decryptData(encrypted as string, signingKey)).resolves.toMatchObject({
      id: "direct-decryption-user",
    })
  })

  it("does not emit an encryption error when Web Crypto is unavailable", async () => {
    const errorSpy = vi.spyOn(logger, "logError").mockImplementation(() => undefined)
    vi.spyOn(window.crypto, "subtle", "get").mockReturnValue(undefined as unknown as SubtleCrypto)

    await expect(encryptData(snapshot("no-encryption-crypto-user"), signingKey)).resolves.toBeNull()

    expect(errorSpy).not.toHaveBeenCalled()
  })

  it("returns null without parsing when Web Crypto is unavailable for decryption", async () => {
    const splitSpy = vi.spyOn(String.prototype, "split")
    vi.spyOn(window.crypto, "subtle", "get").mockReturnValue(undefined as unknown as SubtleCrypto)

    await expect(decryptData("aa:bb:ZmFr", signingKey)).resolves.toBeNull()

    expect(splitSpy).not.toHaveBeenCalledWith(":")
  })

  it("does not emit an encryption error when Web Crypto disappears before derivation", async () => {
    const originalSubtle = window.crypto.subtle
    let subtleReads = 0
    const errorSpy = vi.spyOn(logger, "logError").mockImplementation(() => undefined)
    vi.spyOn(window.crypto, "subtle", "get").mockImplementation(() => {
      subtleReads += 1
      return (subtleReads <= 2 ? originalSubtle : undefined) as SubtleCrypto
    })

    await expect(
      encryptData(snapshot("derive-crypto-unavailable-user"), signingKey)
    ).resolves.toBeNull()

    expect(subtleReads).toBeGreaterThanOrEqual(3)
    expect(errorSpy).not.toHaveBeenCalled()
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
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
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
    expect(warningSpy).not.toHaveBeenCalledWith("profile_cache.decryption_failed")
    unmount()
  })

  it("fails closed when async HMAC verification has no Web Crypto", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("no-hmac-crypto-cache-user"),
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    vi.spyOn(window.crypto, "subtle", "get").mockReturnValue(undefined as unknown as SubtleCrypto)

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    unmount()
  })

  it("keeps crypto loss at key derivation on the invalid-data path without a decryption diagnostic", async () => {
    await writeEncryptedEnvelope(snapshot("derive-crypto-loss-user"))
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)
    const originalSubtle = window.crypto.subtle
    let subtleReads = 0
    vi.spyOn(window.crypto, "subtle", "get").mockImplementation(() => {
      subtleReads += 1
      return (subtleReads <= 3 ? originalSubtle : undefined) as SubtleCrypto
    })

    const { unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_data",
      })
    )
    expect(warningSpy).not.toHaveBeenCalledWith("profile_cache.decryption_failed")
    expect(subtleReads).toBeGreaterThanOrEqual(4)
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
      expect(warningSpy).not.toHaveBeenCalledWith("profile_cache.decryption_failed")
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

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(result.current.user).toBeNull()
    unmount()
  })

  it("rejects same-length signature tampering before restoring a cache placeholder", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("same-length-tampered-user"),
    }
    const validSignature = signEnvelope(payload)
    const tamperedSignature = `${validSignature[0] === "A" ? "B" : "A"}${validSignature.slice(1)}`
    writeSignedEnvelope(payload, tamperedSignature)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    expect(result.current.user).toBeNull()
    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(result.current.user).toBeNull()
    unmount()
  })

  it("rejects signatures whose length differs despite an otherwise valid prefix", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("length-mismatch-cache-user"),
    }
    const validSignature = signEnvelope(payload)
    writeSignedEnvelope(payload, `${validSignature}A`)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => undefined)

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith("profile_cache.cleared", {
        reason: "invalid_signature",
      })
    )
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
    unmount()
  })

  it("bounds the constant-time signature comparison to both string lengths", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("bounded-signature-cache-user"),
    }
    const validSignature = signEnvelope(payload)
    writeSignedEnvelope(payload, validSignature)
    const originalCharCodeAt = String.prototype.charCodeAt
    const observedIndexes: number[] = []
    const charCodeAtSpy = vi.spyOn(String.prototype, "charCodeAt").mockImplementation(function (
      this: string,
      index: number
    ) {
      if (String(this) === validSignature) {
        if (index < 0 || index >= validSignature.length) {
          throw new Error(`signature comparison escaped bounds at ${index}`)
        }
        observedIndexes.push(index)
      }
      return originalCharCodeAt.call(this, index)
    })

    const { result, unmount } = renderProfile(signingKey)

    expect(result.current.user?.id).toBe("bounded-signature-cache-user")
    expect(charCodeAtSpy).toHaveBeenCalled()
    expect(observedIndexes).toHaveLength(validSignature.length * 2)
    expect(observedIndexes).toEqual(
      expect.arrayContaining(Array.from({ length: validSignature.length }, (_, index) => index))
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

  it("keeps cache recovery alive when the decryption diagnostic logger throws", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: "00:00:%%%",
    }
    writeSignedEnvelope(payload)
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation((...args: unknown[]) => {
      if (args[0] === "profile_cache.decryption_failed") {
        throw new Error("diagnostic sink unavailable")
      }
    })

    const { result, unmount } = renderProfile(signingKey)

    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    // The synchronous bootstrap intentionally keeps the encrypted-cache
    // placeholder while async decryption invalidates and clears the payload.
    expect(result.current.user?.id).toBe("-1")
    expect(warningSpy).toHaveBeenCalledWith("profile_cache.decryption_failed")
    unmount()
  })

  it("keeps auth bootstrap alive when the signature diagnostic logger throws", async () => {
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 60_000,
      data: snapshot("sync-verifier-logger-error-user"),
    }
    writeSignedEnvelope(payload)
    vi.spyOn(TextEncoder.prototype, "encode").mockImplementation(() => {
      throw new Error("encoder unavailable")
    })
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation((...args: unknown[]) => {
      if (args[0] === "profile_cache.signature_verification_failed") {
        throw new Error("diagnostic sink unavailable")
      }
    })

    const { result, unmount } = renderProfile(signingKey)

    expect(result.current.user).toBeNull()
    await waitFor(() => expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull())
    expect(warningSpy).toHaveBeenCalledWith("profile_cache.signature_verification_failed")
    unmount()
  })
})
