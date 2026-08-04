import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

import { useSessionCrypto } from "./useSessionCrypto"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

// ---------------------------------------------------------------------------
// useSessionCrypto.branches — drives the stateful hook (the existing
// useSessionCrypto.test.ts only pins the pure helpers). cryptoWorker.pbkdf2
// is the global mock from setupTests.ts (resolves "mock_pbkdf2"); @/api/client
// is mocked here so the signing-key fetch path never hits MSW.
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn((..._a: unknown[]) => Promise.resolve({ data: { signing_key: "sk-1" } })),
}))

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return {
    ...actual,
    default: { get: mocks.apiGet },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiGet.mockResolvedValue({ data: { signing_key: "sk-1" } })
})

afterEach(() => {
  // Restore navigator.serviceWorker if a test swapped it.
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// ensureSessionSigningKey success + dedup — lines 293-300
// ---------------------------------------------------------------------------

describe("ensureSessionSigningKey", () => {
  it("fetches the key, stores it, and resets the retry counter (lines 301-309)", async () => {
    const { result } = renderHook(() => useSessionCrypto())
    let key: string | null = null
    await act(async () => {
      key = await result.current.ensureSessionSigningKey()
    })
    expect(key).toBe("sk-1")
    expect(mocks.apiGet).toHaveBeenCalledWith(
      "/auth/session/signing-key",
      expect.objectContaining({ skipRateLimitQueue: true })
    )
    expect(result.current.sessionSigningKeyRef.current).toBe("sk-1")
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)
  })

  it("returns the cached ref without re-fetching (lines 294-296)", async () => {
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await result.current.updateSessionSigningKey("cached-key")
    })
    let key: string | null = null
    await act(async () => {
      key = await result.current.ensureSessionSigningKey()
    })
    expect(key).toBe("cached-key")
    expect(mocks.apiGet).not.toHaveBeenCalled()
  })

  it("deduplicates concurrent callers via the in-flight promise (lines 298-300)", async () => {
    let resolveFetch: (v: { data: { signing_key: string } }) => void = () => {}
    mocks.apiGet.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve
        })
    )
    const { result } = renderHook(() => useSessionCrypto())
    let a: Promise<string | null> | undefined
    let b: Promise<string | null> | undefined
    act(() => {
      a = result.current.ensureSessionSigningKey()
      b = result.current.ensureSessionSigningKey()
    })
    // Both calls share the SAME in-flight promise → fetch invoked exactly once.
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolveFetch({ data: { signing_key: "sk-dedup" } })
      await Promise.all([a, b])
    })
    await expect(a).resolves.toBe("sk-dedup")
    await expect(b).resolves.toBe("sk-dedup")
  })
})

// ---------------------------------------------------------------------------
// ensureSessionSigningKey failure → retry counter + backoff + event
// — lines 311-342
// ---------------------------------------------------------------------------

describe("ensureSessionSigningKey failure path", () => {
  it("increments the retry counter on a single failure (lines 312-313)", async () => {
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const { result } = renderHook(() => useSessionCrypto())
    let key: string | null = "x"
    await act(async () => {
      key = await result.current.ensureSessionSigningKey()
    })
    expect(key).toBeNull()
    expect(result.current.signingKeyRetryCountRef.current).toBe(1)
  })

  it("enters backoff + dispatches the crypto-failed event on the 3rd failure (lines 314-342)", async () => {
    vi.useFakeTimers()
    const dispatch = vi.spyOn(window, "dispatchEvent")
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const { result } = renderHook(() => useSessionCrypto())

    // Three consecutive failures trip MAX_SIGNING_KEY_RETRIES (3).
    await act(async () => {
      await result.current.ensureSessionSigningKey()
    })
    await act(async () => {
      await result.current.ensureSessionSigningKey()
    })
    await act(async () => {
      await result.current.ensureSessionSigningKey()
    })

    expect(result.current.signingKeyRetryCountRef.current).toBe(3)
    const events = dispatch.mock.calls.map((c) => c[0])
    const cryptoFailed = events.find(
      (e) => e instanceof CustomEvent && e.type === "auth:session-crypto-failed"
    ) as CustomEvent | undefined
    expect(cryptoFailed).toBeDefined()
    expect((cryptoFailed!.detail as { reason: string }).reason).toBe("max_retries_exceeded")

    // The backoff setTimeout resets the retry counter back to 0 when it fires.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)

    dispatch.mockRestore()
    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// sendServiceWorkerMessage — lines 219-256 (via sendSessionCacheUpdate)
// ---------------------------------------------------------------------------

describe("sendServiceWorkerMessage", () => {
  it("posts directly to the controller when one is present (lines 239-242)", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: { postMessage },
        ready: undefined,
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-ctrl", { force: true, purge: true })
    })
    // CLEAR_API_CACHE (purge) + SET_API_SESSION_CACHE_KEY messages.
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE })
    )
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY })
    )
  })

  it("falls back to container.ready.active when no controller (lines 244-249)", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: null,
        ready: Promise.resolve({ active: { postMessage } }),
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-ready", { force: true })
    })
    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY })
      )
    )
  })

  it("does not post when the ready registration has no active worker", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: null,
        ready: Promise.resolve({ active: null }),
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-no-active", { force: true })
      await Promise.resolve()
    })

    expect(postMessage).not.toHaveBeenCalled()
  })

  it("returns safely when navigator is unavailable", async () => {
    vi.stubGlobal("navigator", undefined)
    const { result } = renderHook(() => useSessionCrypto())
    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-no-navigator", { force: true })
      })
    ).resolves.not.toThrow()
  })

  it("returns early when navigator.serviceWorker is absent (lines 223-225)", async () => {
    vi.stubGlobal("navigator", {})
    const { result } = renderHook(() => useSessionCrypto())
    // No serviceWorker container → the message dispatch is a no-op; the call
    // should still resolve without throwing.
    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-none", { force: true })
      })
    ).resolves.not.toThrow()
  })

  it("swallows controller postMessage failures", async () => {
    const postMessage = vi.fn(() => {
      throw new Error("worker stopped")
    })
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())

    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-throw", { force: true })
      })
    ).resolves.not.toThrow()
    expect(postMessage).toHaveBeenCalled()
  })

  it("swallows service-worker readiness failures", async () => {
    const ready = Promise.reject(new Error("registration failed"))
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: null, ready },
    })
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-ready-failure", { force: true })
      await Promise.resolve()
      await Promise.resolve()
    })
  })

  it("skips re-sending when the session hash is unchanged + not forced (lines 264-265)", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())
    // First send establishes sessionCacheHashRef.
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-same", { force: true })
    })
    postMessage.mockClear()
    // Second send with the SAME key (mock pbkdf2 is constant) + no force → early return.
    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-same")
    })
    expect(postMessage).not.toHaveBeenCalled()
  })

  it("clears an existing backoff timer before scheduling the next retry window", async () => {
    vi.useFakeTimers()
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })

    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
    vi.runAllTimers()
    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// unmount cleanup clears the backoff timer — lines 367-373
// ---------------------------------------------------------------------------

describe("unmount cleanup", () => {
  it("clears a pending backoff timer on unmount (lines 369-372)", async () => {
    vi.useFakeTimers()
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    const { result, unmount } = renderHook(() => useSessionCrypto())

    // Trip the backoff so signingKeyBackoffTimerRef holds a live timer id.
    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })

    clearSpy.mockClear()
    act(() => {
      unmount()
    })
    // Cleanup effect cancels the live backoff timer.
    expect(clearSpy).toHaveBeenCalled()

    clearSpy.mockRestore()
    vi.useRealTimers()
  })
})
