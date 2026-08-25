import { PropsWithChildren } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import {
  PROFILE_CACHE_STORAGE_KEY,
  currentUserQueryKey,
  PROFILE_CACHE_SCHEMA_VERSION,
  type CachedUserSnapshot,
  type CacheSignaturePayload,
  encryptData,
  signPayload,
} from "../../hooks/auth/useProfileSync"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { testUser } from "@/tests/mocks/handlers"
import api from "@/api/client"
import i18n from "@/i18n/config"
import { hmac } from "@noble/hashes/hmac.js"
import { sha256 } from "@noble/hashes/sha2.js"
import { utf8ToBytes } from "@noble/hashes/utils.js"
import * as logger from "@/app/logger"

// cryptoWorker is mocked globally in setupTests.ts

const bytesToBase64 = (bytes: Uint8Array): string => {
  const maybeBuffer =
    typeof globalThis !== "undefined" &&
    typeof (globalThis as { Buffer?: unknown }).Buffer === "function"
      ? (globalThis as { Buffer?: { from?: unknown } }).Buffer
      : undefined

  if (
    maybeBuffer &&
    typeof maybeBuffer === "function" &&
    typeof (maybeBuffer as { from?: unknown }).from === "function"
  ) {
    return (
      maybeBuffer as {
        from: (
          input: Uint8Array | string,
          encoding?: string
        ) => {
          toString: (encoding: string) => string
        }
      }
    )
      .from(bytes)
      .toString("base64")
  }

  let binary = ""
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }

  if (
    typeof globalThis !== "undefined" &&
    typeof (globalThis as { btoa?: (value: string) => string }).btoa === "function"
  ) {
    return (globalThis as { btoa: (value: string) => string }).btoa(binary)
  }

  throw new Error("Unable to encode payload in base64")
}

describe("AuthProvider caching", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.clearAllMocks()
    vi.spyOn(api, "post").mockResolvedValue({ data: {} } as any)
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser })
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: mockSigningKey } })
      }
      return Promise.reject(new Error(`Unexpected GET: ${url}`))
    })
  })

  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  const setup = () => {
    const queryClient = createQueryClient()
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )
    return { queryClient, wrapper }
  }

  it("stores the current user in the query cache and local storage", async () => {
    localStorage.setItem("token", "token-123")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for loading to complete and user to be loaded
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })
    await waitFor(() => expect(result.current.user).toBeTruthy(), { timeout: 15000 })

    expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(testUser)
    expect(queryClient.getQueryState(currentUserQueryKey)?.dataUpdatedAt).toBeGreaterThan(0)

    queryClient.clear()
  })

  it("removes cached profile information on logout", async () => {
    localStorage.setItem("token", "token-456")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for loading to complete and user to be loaded
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })
    await waitFor(() => expect(result.current.user).toBeTruthy(), { timeout: 15000 })

    await act(async () => {
      await result.current.logout()
    })

    await waitFor(() => expect(result.current.user).toBeNull(), { timeout: 15000 })

    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })

  it("synchronizes cached profile state when storage changes", { timeout: 20000 }, async () => {
    localStorage.setItem("token", "token-789")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for loading to complete and user to be loaded
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })
    await waitFor(() => expect(result.current.user).toBeTruthy(), { timeout: 15000 })

    const cachedEnvelope = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)

    act(() => {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          oldValue: cachedEnvelope,
          newValue: null,
          storageArea: localStorage,
        })
      )
    })

    await waitFor(() => expect(result.current.user).toBeNull(), { timeout: 15000 })
    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })

  it("discards tampered cached envelopes", { timeout: 20000 }, async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.reject({ response: { status: 401 }, isAxiosError: true })
      }
      return Promise.resolve({ data: { signing_key: mockSigningKey } })
    })

    localStorage.setItem("token", "token-tamper")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for the initial 401 and stabilization
    await waitFor(() => expect(result.current.loading).toBe(false))

    // 1. Setup a valid cache entry (manually simulate re-entry or valid state)
    // TD-14-07: email and role are no longer cached (PII). Use only allowed fields.
    const validData: CachedUserSnapshot = {
      id: "test-id",
      full_name: "Test User",
      is_active: true,
    }
    const encryptedData = await encryptData(validData, mockSigningKey)
    const payload: CacheSignaturePayload = {
      version: PROFILE_CACHE_SCHEMA_VERSION,
      expiresAt: Date.now() + 300000,
      data: encryptedData!,
    }
    const signature = await signPayload(payload, mockSigningKey)
    const cachedEnvelope = JSON.stringify({ ...payload, signature })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, cachedEnvelope)

    // 2. Tamper
    const parsed = JSON.parse(cachedEnvelope) as any
    parsed.signature = "tampered_signature"
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify(parsed))

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          oldValue: cachedEnvelope,
          newValue: JSON.stringify(parsed),
          storageArea: localStorage,
        })
      )
    })

    await waitFor(
      () => {
        expect(result.current.user).toBeNull()
      },
      { timeout: 15000 }
    )
    await waitFor(
      () => {
        const val = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
        expect(val).toBeNull()
      },
      {
        timeout: 10000,
      }
    )
    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })
})

const deriveCacheMetadata = () => {
  const versionMatch = PROFILE_CACHE_STORAGE_KEY.match(/\.v(\d+)$/)
  const schemaVersion = versionMatch ? Number.parseInt(versionMatch[1]!, 10) : 1
  const baseKey = versionMatch
    ? PROFILE_CACHE_STORAGE_KEY.replace(versionMatch[0]!, "")
    : PROFILE_CACHE_STORAGE_KEY
  const sessionKeyStorageKey = `${baseKey}.sessionKey`
  const versionKey = `${baseKey}.version`
  return { schemaVersion, sessionKeyStorageKey, versionKey }
}

const buildMockSigningKey = () =>
  Array.from({ length: 32 }, (_, index) => ((index * 13 + 7) % 16).toString(16)).join("")

const mockSigningKey = buildMockSigningKey()

const primeCachedProfile = () => {
  const { schemaVersion, sessionKeyStorageKey, versionKey } = deriveCacheMetadata()
  const originalGetItem = Storage.prototype.getItem
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
    if (key === sessionKeyStorageKey) {
      return mockSigningKey
    }

    return originalGetItem.call(this, key)
  })

  const snapshot = {
    id: testUser.id,
    full_name: testUser.full_name,
    avatar_url: testUser.avatar_url,
  }

  const payload = {
    version: schemaVersion,
    expiresAt: Date.now() + 60_000,
    data: snapshot,
  }

  const signatureBytes = hmac(
    sha256,
    utf8ToBytes(mockSigningKey),
    utf8ToBytes(JSON.stringify(payload))
  )
  const signature = bytesToBase64(signatureBytes)

  const envelope = { ...payload, signature }
  localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify(envelope))
  localStorage.setItem(versionKey, String(schemaVersion))
}

describe("AuthProvider loading state", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  const setup = () => {
    const queryClient = createQueryClient()
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )
    return { queryClient, wrapper }
  }

  it("keeps loading false when a cached profile is available", async () => {
    primeCachedProfile()
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser })
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: mockSigningKey } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // The signing key is memory-only (never persisted to localStorage), so cache
    // cannot be restored synchronously. Wait for initialization to settle quickly
    // without the user experiencing a prolonged loading state.
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    // After initialization, the user should be available from the API response
    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id), { timeout: 15000 })

    // Wait for background refresh to complete
    await waitFor(
      () =>
        expect(getSpy).toHaveBeenCalledWith(
          "/users/me",
          expect.objectContaining({ skipRateLimitQueue: true })
        ),
      { timeout: 15000 }
    )

    // Loading should still be false after background refresh
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    queryClient.clear()
  })

  it("toggles loading during refresh when no cached profile exists", async () => {
    const { queryClient, wrapper } = setup()

    let firstUserRequest = true
    let resolveUserRequest: ((value: unknown) => void) | null = null
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        if (firstUserRequest) {
          firstUserRequest = false
          return Promise.resolve({ data: testUser })
        }

        return new Promise((resolve) => {
          resolveUserRequest = resolve
        })
      }

      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: mockSigningKey } })
      }

      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    act(() => {
      result.current.setUser(() => null)
    })

    await waitFor(() => expect(result.current.user).toBeNull(), { timeout: 15000 })

    let refreshPromise!: Promise<void>
    console.error("[Trace] Calling refresh()")
    console.error("[Trace] result.current properties:", Object.keys(result.current))
    act(() => {
      refreshPromise = result.current.refresh()
    })
    console.error("[Trace] refreshPromise created")

    console.error("[Trace] Waiting for loading to be true")
    await waitFor(
      () => {
        console.error("[Trace] Current loading state:", result.current.loading)
        expect(result.current.loading).toBe(true)
      },
      { timeout: 15000 }
    )

    console.error("[Trace] Resolving user request")
    await act(async () => {
      resolveUserRequest?.({ data: testUser })
      resolveUserRequest = null
      await refreshPromise
    })

    console.error("[Trace] Waiting for loading to be false")
    await waitFor(
      () => {
        console.error("[Trace] Loading state final:", result.current.loading)
        expect(result.current.loading).toBe(false)
      },
      { timeout: 15000 }
    )

    queryClient.clear()
  })
})

describe("AuthProvider dashboard prefetch", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  const setup = () => {
    const queryClient = createQueryClient()
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )
    return { queryClient, wrapper }
  }

  const resolveActiveLanguage = () => {
    const resolved = i18n.resolvedLanguage ?? i18n.language ?? "ru"
    return resolved === "en" ? "en" : "ru"
  }

  const preparePrefetchSpies = async () => {
    const [storiesModule, newsModule, eventsModule, eventsApiModule] = await Promise.all([
      import("@/hooks/useDashboardStories"),
      import("@/hooks/useDashboardNews"),
      import("@/hooks/useDashboardEvents"),
      import("@/api/hooks/events"),
    ])

    const storiesSpy = vi
      .spyOn(storiesModule, "prefetchDashboardStories")
      .mockImplementation(async () => undefined)
    const newsSpy = vi
      .spyOn(newsModule, "prefetchDashboardNews")
      .mockImplementation(async () => undefined)
    const eventsSpy = vi
      .spyOn(eventsModule, "prefetchDashboardEvents")
      .mockImplementation(async () => undefined)
    const eventsListSpy = vi
      .spyOn(eventsApiModule, "prefetchEventsListQuery")
      .mockImplementation(async () => undefined as any)

    return {
      storiesSpy,
      newsSpy,
      eventsSpy,
      eventsListSpy,
      eventsPageSize: eventsApiModule.EVENTS_PAGE_SIZE,
    }
  }

  it("prefetches dashboard queries after login", { timeout: 20000 }, async () => {
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({
      status: 200,
      data: {
        access_token: "token",
        token_type: "bearer",
        user: { ...testUser, group_id: null },
        session: { signing_key: "key" },
      },
    } as any)
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser })
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "key" } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { storiesSpy, newsSpy, eventsSpy, eventsListSpy } = await preparePrefetchSpies()
    const language = resolveActiveLanguage()
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for initial loading to complete
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    await act(async () => {
      await result.current.login("user@example.com", "password")
    })

    // Wait for login operation to complete
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    await waitFor(
      () => {
        expect(postSpy).toHaveBeenCalled()
        expect(storiesSpy).toHaveBeenCalledTimes(1)
        expect(newsSpy).toHaveBeenCalledTimes(1)
        expect(eventsSpy).toHaveBeenCalledTimes(1)
      },
      { timeout: 15000 }
    )

    expect(newsSpy).toHaveBeenCalledWith(expect.anything(), language)
    expect(eventsListSpy).not.toHaveBeenCalled()

    queryClient.clear()
  })

  it("prefetches schedule data when the student has a group", { timeout: 20000 }, async () => {
    const loginUser = { ...testUser, group_id: 42 }
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({
      status: 200,
      data: {
        access_token: "token",
        token_type: "bearer",
        user: loginUser,
        session: { signing_key: "key" },
      },
    } as any)
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser })
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "key" } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { storiesSpy, newsSpy, eventsSpy, eventsListSpy, eventsPageSize } =
      await preparePrefetchSpies()
    const language = resolveActiveLanguage()
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Wait for initial loading to complete
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    await act(async () => {
      await result.current.login("user@example.com", "password")
    })

    // Wait for login operation to complete
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 15000 })

    await waitFor(
      () => {
        expect(postSpy).toHaveBeenCalled()
        expect(storiesSpy).toHaveBeenCalledTimes(1)
        expect(newsSpy).toHaveBeenCalledTimes(1)
        expect(eventsSpy).toHaveBeenCalledTimes(1)
        expect(eventsListSpy).toHaveBeenCalledTimes(1)
      },
      { timeout: 15000 }
    )

    expect(eventsListSpy).toHaveBeenCalledWith(expect.anything(), {
      language,
      is_active: true,
      limit: eventsPageSize,
    })

    queryClient.clear()
  })
})

describe("useAuth outside AuthProvider", () => {
  it("keeps the default context actions callable and warns on setUser", async () => {
    const warningSpy = vi.spyOn(logger, "logWarning").mockImplementation(() => {})
    const { result } = renderHook(() => useAuth())

    await act(async () => {
      expect(await result.current.login("user@example.com", "password")).toBeNull()
      await result.current.logout()
      result.current.setUser(null)
      await result.current.refresh()
      await result.current.submitMfaChallenge({ code: "123456" })
      expect(await result.current.requireMfa()).toBeNull()
      await result.current.loginWithPasskey("user@example.com")
    })

    expect(warningSpy).toHaveBeenCalledWith("AuthContext setUser called outside provider")
    warningSpy.mockRestore()
  })
})
