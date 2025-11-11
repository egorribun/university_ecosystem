import { PropsWithChildren } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import {
  AuthProvider,
  PROFILE_CACHE_STORAGE_KEY,
  currentUserQueryKey,
  useAuth,
} from "@/contexts/AuthContext"
import { testUser } from "@/tests/mocks/handlers"
import api from "@/api/client"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"
import { utf8ToBytes } from "@noble/hashes/utils"

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
    vi.spyOn(api, "post").mockResolvedValue({ data: {} } as any)
  })

  afterEach(() => {
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

    await waitFor(() => expect(result.current.user).toBeTruthy())

    expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(testUser)
    expect(queryClient.getQueryState(currentUserQueryKey)?.dataUpdatedAt).toBeGreaterThan(0)

    queryClient.clear()
  })

  it("removes cached profile information on logout", async () => {
    localStorage.setItem("token", "token-456")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

    await act(async () => {
      await result.current.logout()
    })

    await waitFor(() => expect(result.current.user).toBeNull())

    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })

  it("synchronizes cached profile state when storage changes", async () => {
    localStorage.setItem("token", "token-789")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

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

    await waitFor(() => expect(result.current.user).toBeNull())
    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })

  it("discards tampered cached envelopes", async () => {
    localStorage.setItem("token", "token-tamper")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

    const cachedEnvelope = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    expect(cachedEnvelope).toBeTruthy()
    const parsed = JSON.parse(cachedEnvelope!)
    parsed.data.full_name = "Forged Name"
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

    await waitFor(() => expect(result.current.user).toBeNull())
    expect(localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)).toBeNull()
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

const primeCachedProfile = () => {
  const { schemaVersion, sessionKeyStorageKey, versionKey } = deriveCacheMetadata()
  const signingKey = "cached-session-key"
  const originalGetItem = Storage.prototype.getItem
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
    if (key === sessionKeyStorageKey) {
      return signingKey
    }

    return originalGetItem.call(this, key)
  })

  const snapshot = {
    id: testUser.id,
    full_name: testUser.full_name,
    avatar_url: testUser.avatar_url,
    mfa_required: testUser.mfa_required,
    mfa_default_method: testUser.mfa_default_method,
    mfa_last_verified_at: testUser.mfa_last_verified_at,
    mfa_recovery_codes_generated_at: testUser.mfa_recovery_codes_generated_at,
  }

  const payload = {
    version: schemaVersion,
    expiresAt: Date.now() + 60_000,
    data: snapshot,
  }

  const signatureBytes = hmac(
    sha256,
    utf8ToBytes(signingKey),
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
  })

  afterEach(() => {
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
        return Promise.resolve({ data: { signing_key: "cached-session-key" } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.loading).toBe(false)
    expect(result.current.user?.id).toBe(testUser.id)

    await waitFor(() =>
      expect(getSpy).toHaveBeenCalledWith(
        "/users/me",
        expect.objectContaining({ skipRateLimitQueue: true })
      )
    )

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
        return Promise.resolve({ data: { signing_key: "fresh-session-key" } })
      }

      throw new Error(`Unexpected url: ${url}`)
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.setUser(() => null)
    })

    await waitFor(() => expect(result.current.user).toBeNull())

    let refreshPromise!: Promise<void>
    await act(async () => {
      refreshPromise = result.current.refresh()
    })

    await waitFor(() => expect(result.current.loading).toBe(true))

    await act(async () => {
      resolveUserRequest?.({ data: testUser })
      resolveUserRequest = null
      await refreshPromise
    })

    expect(result.current.loading).toBe(false)

    queryClient.clear()
  })
})
