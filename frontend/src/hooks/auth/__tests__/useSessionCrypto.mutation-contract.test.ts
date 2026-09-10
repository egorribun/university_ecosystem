import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import { cryptoWorker } from "@/utils/cryptoWorker"
import {
  clearLegacySessionSigningKey,
  hashSessionIdentifier,
  isSessionCryptoBrowserRuntime,
  signSnapshot,
  useSessionCrypto,
} from "@/hooks/auth/useSessionCrypto"

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn((..._args: unknown[]) => Promise.resolve({ data: { signing_key: "sk-1" } })),
}))

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return { ...actual, default: { get: mocks.apiGet } }
})

describe("useSessionCrypto mutation contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.apiGet.mockResolvedValue({ data: { signing_key: "sk-1" } })
    vi.mocked(cryptoWorker.pbkdf2).mockResolvedValue("mock_pbkdf2")
    vi.mocked(cryptoWorker.scrypt).mockResolvedValue(Uint8Array.of(1, 2, 3))
    vi.mocked(cryptoWorker.hmacSha256).mockResolvedValue("mock_hmac")
  })

  afterEach(() => {
    vi.useRealTimers()
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
      expect(isSessionCryptoBrowserRuntime()).toBe(false)
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("clears the legacy session signing key through the explicit cleanup contract", () => {
    const removeItem = vi.fn()
    vi.stubGlobal("sessionStorage", { removeItem })

    clearLegacySessionSigningKey()

    expect(removeItem).toHaveBeenCalledWith("ecosystem.profile.cache.sessionKey")
  })

  it("swallows legacy session signing-key cleanup failures", () => {
    const removeItem = vi.fn(() => {
      throw new Error("storage unavailable")
    })
    vi.stubGlobal("sessionStorage", { removeItem })

    expect(() => clearLegacySessionSigningKey()).not.toThrow()
    expect(removeItem).toHaveBeenCalledWith("ecosystem.profile.cache.sessionKey")
  })

  it("passes the complete fixed PBKDF2 namespace contract to the worker", async () => {
    await expect(hashSessionIdentifier("session-abc")).resolves.toBe("mock_pbkdf2")

    expect(cryptoWorker.pbkdf2).toHaveBeenCalledWith({
      value: "session-abc",
      salt: "ecosystem.session.id.salt.v1",
      keySize: 256,
      iterations: 100000,
    })
  })

  it("hashes every sensitive string field with the user-scoped scrypt contract", async () => {
    const scrypt = vi.mocked(cryptoWorker.scrypt)
    const hmac = vi.mocked(cryptoWorker.hmacSha256)

    await expect(
      signSnapshot(
        {
          mfa_required: "true",
          nested: {
            mfa_default_method: "totp",
            mfa_last_verified_at: "2026-09-10T00:00:00Z",
            plain: "kept",
          },
        },
        "session-key",
        "user-salt"
      )
    ).resolves.toBe("mock_hmac")

    expect(scrypt).toHaveBeenCalledTimes(3)
    const expectedPasswords = ["true", "totp", "2026-09-10T00:00:00Z"]
    for (const [index, call] of scrypt.mock.calls.entries()) {
      const options = call[0]
      expect(options).toMatchObject({ N: 16384, r: 8, p: 1, dkLen: 32 })
      expect(Array.from(options!.password)).toEqual(
        Array.from(new TextEncoder().encode(expectedPasswords[index]!))
      )
      expect(Array.from(options!.salt)).toEqual(
        Array.from(new TextEncoder().encode("ecosystem.sensitive.field.salt.v2:user-salt"))
      )
    }

    expect(hmac).toHaveBeenCalledWith({
      json: JSON.stringify({
        mfa_required: "010203",
        nested: {
          mfa_default_method: "010203",
          mfa_last_verified_at: "010203",
          plain: "kept",
        },
      }),
      key: "session-key",
    })
  })

  it("does not hash non-string sensitive values and preserves scalar/array shape", async () => {
    const scrypt = vi.mocked(cryptoWorker.scrypt)
    const hmac = vi.mocked(cryptoWorker.hmacSha256)

    await signSnapshot(
      [
        { mfa_required: true, value: null },
        { mfa_default_method: null, value: 0 },
        { mfa_last_verified_at: undefined, value: "ok" },
      ],
      "session-key",
      "user-salt"
    )

    expect(scrypt).not.toHaveBeenCalled()
    expect(hmac).toHaveBeenCalledWith({
      json: JSON.stringify([
        { mfa_required: true, value: null },
        { mfa_default_method: null, value: 0 },
        { value: "ok" },
      ]),
      key: "session-key",
    })
  })

  it("preserves a scalar root payload before signing", async () => {
    const hmac = vi.mocked(cryptoWorker.hmacSha256)

    await signSnapshot("plain string", "session-key", "user-salt")
    await signSnapshot(42, "session-key", "user-salt")
    await signSnapshot(null, "session-key", "user-salt")

    expect(hmac.mock.calls.slice(-3)).toEqual([
      [{ json: JSON.stringify("plain string"), key: "session-key" }],
      [{ json: JSON.stringify(42), key: "session-key" }],
      [{ json: JSON.stringify(null), key: "session-key" }],
    ])
  })

  it("sends one purge and one keyed cache message with an exact session hash", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.sendSessionCacheUpdate("session-key", { purge: true, force: true })
    })

    expect(postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE,
    })
    expect(postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "mock_pbkdf2",
    })
  })

  it("clears the cache and sends an explicit undefined key when the session is removed", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await Promise.resolve()
    })
    postMessage.mockClear()

    await act(async () => {
      await result.current.sendSessionCacheUpdate(null, { purge: true, force: true })
    })

    expect(postMessage.mock.calls).toEqual([
      [{ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE }],
      [{ type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY, sessionHash: undefined }],
    ])
  })

  it("does not assume a service-worker ready registration or a callable then property", async () => {
    const postMessage = vi.fn()
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: null,
        ready: Promise.resolve(undefined),
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-no-registration", { force: true })
      await Promise.resolve()
    })
    expect(postMessage).not.toHaveBeenCalled()

    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: null,
        ready: { then: "not-a-function" },
      },
    })
    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-non-callable-ready", { force: true })
      })
    ).resolves.not.toThrow()
    // A missing registration is a normal startup race, not a delivery error.
    // This assertion keeps the optional registration guard observable: removing
    // `registration?.active` would dereference undefined and reach the catch
    // warning instead of remaining a no-op.
    expect(warningSpy).not.toHaveBeenCalled()
    warningSpy.mockRestore()
  })

  it("deduplicates an unchanged cache hash unless force is requested", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.sendSessionCacheUpdate("session-key", { force: true })
    })
    postMessage.mockClear()

    await act(async () => {
      await result.current.sendSessionCacheUpdate("session-key")
    })
    expect(postMessage).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.sendSessionCacheUpdate("session-key", { force: true })
    })
    expect(postMessage).toHaveBeenCalledTimes(1)
  })

  it("does not synchronize the service worker from an SSR-like runtime", async () => {
    const originalWindow = globalThis.window
    const pbkdf2 = vi.mocked(cryptoWorker.pbkdf2)
    const postMessage = vi.fn()
    vi.stubGlobal("window", { document: globalThis.document })
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })

    try {
      renderHook(() => useSessionCrypto())
      await act(async () => {
        await Promise.resolve()
      })
      expect(pbkdf2).not.toHaveBeenCalled()
      expect(postMessage).not.toHaveBeenCalled()
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("publishes the first exponential backoff delay and resets after its deadline", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    mocks.apiGet.mockRejectedValue(new Error("service unavailable"))
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })

    const failureEvent = dispatchEvent.mock.calls
      .map(([event]) => event)
      .find((event): event is CustomEvent => event instanceof CustomEvent)
    expect(failureEvent?.type).toBe("auth:session-crypto-failed")
    expect(failureEvent?.detail).toEqual({ reason: "max_retries_exceeded", backoffMs: 5000 })
    expect(result.current.signingKeyRetryCountRef.current).toBe(3)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)
  })

  it("doubles backoff on repeated circuit openings and caps it at one minute", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    mocks.apiGet.mockRejectedValue(new Error("service unavailable"))
    const { result } = renderHook(() => useSessionCrypto())

    // Each call is a fresh request after the previous promise settles. The
    // fourth and later failures deliberately exercise the circuit-open path
    // again, so the delay contract is observable without waiting in real time.
    await act(async () => {
      for (let attempt = 0; attempt < 9; attempt += 1) {
        await result.current.ensureSessionSigningKey()
      }
    })

    const delays = dispatchEvent.mock.calls
      .map(([event]) => event)
      .filter((event): event is CustomEvent => event instanceof CustomEvent)
      .map((event) => (event.detail as { backoffMs?: number }).backoffMs)
    expect(delays).toEqual([5_000, 10_000, 20_000, 40_000, 60_000, 60_000, 60_000])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)
  })

  it("resets the retry circuit on an explicit key update", async () => {
    mocks.apiGet.mockRejectedValueOnce(new Error("service unavailable"))
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.ensureSessionSigningKey()
    })
    expect(result.current.signingKeyRetryCountRef.current).toBe(1)

    await act(async () => {
      await result.current.updateSessionSigningKey("manual-key")
    })
    expect(result.current.sessionSigningKeyRef.current).toBe("manual-key")
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)
  })
})
