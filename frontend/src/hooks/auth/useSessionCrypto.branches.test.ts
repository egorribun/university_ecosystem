import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

import { useSessionCrypto } from "./useSessionCrypto"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import {
  captureSessionEpoch,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { cryptoWorker } from "@/utils/cryptoWorker"
import { expectConsoleWarning } from "@/tests/strictConsole"

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
  vi.restoreAllMocks()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

// ---------------------------------------------------------------------------
// ensureSessionSigningKey success + dedup — lines 293-300
// ---------------------------------------------------------------------------

describe("ensureSessionSigningKey", () => {
  it("answers a restarted worker without a controllerchange and keeps its session scope", async () => {
    const listeners = new Map<string, (event: MessageEvent) => void>()
    const controller = { postMessage: vi.fn() }
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        controller,
        addEventListener: (type: string, callback: (event: MessageEvent) => void) =>
          listeners.set(type, callback),
        removeEventListener: (type: string) => listeners.delete(type),
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey("live-key"))
    const update = controller.postMessage.mock.calls
      .map(([value]) => value)
      .find((value) => value.sessionHash === "mock_pbkdf2")
    expect(result.current.isCurrentSigningSession()).toBe(true)
    const reply = vi.fn()
    listeners.get("message")!({
      source: controller,
      data: { type: SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY },
      ports: [{ postMessage: reply }],
    } as unknown as MessageEvent)
    expect(reply).toHaveBeenCalledWith({
      sessionHash: "mock_pbkdf2",
      sessionScope: update.sessionScope,
    })
    await act(() => result.current.updateSessionSigningKey(null))
    listeners.get("message")!({
      source: controller,
      data: { type: SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY },
      ports: [{ postMessage: reply }],
    } as unknown as MessageEvent)
    expect(reply).toHaveBeenLastCalledWith({ sessionHash: null, sessionScope: null })
    expect(result.current.isCurrentSigningSession()).toBe(false)
  })

  it("discards a signing-key fetch that settles after local session expiry", async () => {
    let resolveFetch!: (value: { data: { signing_key: string } }) => void
    mocks.apiGet.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve
        })
    )
    const { result } = renderHook(() => useSessionCrypto())
    const pending = result.current.ensureSessionSigningKey()
    await act(() => result.current.updateSessionSigningKey(null))
    await act(async () => {
      resolveFetch({ data: { signing_key: "old-account-secret" } })
      await pending
    })
    await expect(pending).resolves.toBeNull()
    expect(result.current.sessionSigningKeyRef.current).toBeNull()
  })

  it("discards a successful signing-key fetch from a previous browser generation", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", { serviceWorker: { controller: { postMessage } } })
    let resolveRequest!: (value: { data: { signing_key: string } }) => void
    const response = new Promise<{ data: { signing_key: string } }>((resolve) => {
      resolveRequest = resolve
    })
    mocks.apiGet.mockReturnValueOnce(response)
    const { result } = renderHook(() => useSessionCrypto())
    const pending = result.current.ensureSessionSigningKey()
    try {
      const requestGeneration = getBrowserSessionGeneration()
      rotateBrowserSession()
      const currentGeneration = getBrowserSessionGeneration()
      expect(currentGeneration).not.toBe(requestGeneration)

      await act(async () => {
        resolveRequest({ data: { signing_key: "previous-generation-key" } })
        await expect(pending).resolves.toBeNull()
      })
      expect(result.current.sessionSigningKey).toBeNull()
      expect(result.current.sessionSigningKeyRef.current).toBeNull()
      expect(result.current.isCurrentSigningSession()).toBe(false)
      expect(getBrowserSessionGeneration()).toBe(currentGeneration)
      expect(cryptoWorker.pbkdf2).not.toHaveBeenCalled()
      expect(postMessage).not.toHaveBeenCalled()

      mocks.apiGet.mockResolvedValueOnce({ data: { signing_key: "current-generation-key" } })
      await act(async () => {
        await expect(result.current.ensureSessionSigningKey()).resolves.toBe(
          "current-generation-key"
        )
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(2)
      expect(result.current.sessionSigningKey).toBe("current-generation-key")
      expect(result.current.sessionSigningKeyRef.current).toBe("current-generation-key")
      expect(result.current.isCurrentSigningSession()).toBe(true)
      expect(getBrowserSessionGeneration()).toBe(currentGeneration)
      expect(cryptoWorker.pbkdf2).toHaveBeenCalledExactlyOnceWith({
        value: "current-generation-key",
        salt: "ecosystem.session.id.salt.v1",
        keySize: 256,
        iterations: 100000,
      })
      expect(postMessage.mock.calls.map(([message]) => message)).toEqual([
        { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE },
        {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: "mock_pbkdf2",
          sessionScope: `mock_pbkdf2:${currentGeneration}`,
        },
      ])
    } finally {
      await act(async () => {
        resolveRequest({ data: { signing_key: "previous-generation-key" } })
        await Promise.allSettled([response, pending])
      })
    }
  })

  it("does not send an old namespace after logout overtakes hashing", async () => {
    const postMessage = vi.fn()
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { controller: { postMessage } },
    })
    let finishHash!: (value: string) => void
    vi.mocked(cryptoWorker.pbkdf2).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishHash = resolve
        })
    )
    const { result } = renderHook(() => useSessionCrypto())
    let pending!: Promise<void>
    act(() => {
      pending = result.current.updateSessionSigningKey("old-key")
    })
    await act(() => result.current.updateSessionSigningKey(null))
    await act(async () => {
      finishHash("old-hash")
      await pending
    })
    expect(postMessage).not.toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "old-hash",
      sessionScope: expect.any(String),
    })
    expect(postMessage).toHaveBeenCalledWith({ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE })
  })

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

  it.each([false, true])(
    "counts an owned cache-key derivation failure (synchronous: %s)",
    async (synchronous) => {
      vi.mocked(cryptoWorker.pbkdf2).mockImplementationOnce(() => {
        if (synchronous) throw new Error("worker unavailable")
        return Promise.reject(new Error("worker unavailable"))
      })
      const { result } = renderHook(() => useSessionCrypto())

      await act(async () => {
        await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
      })
      expect(result.current.signingKeyRetryCountRef.current).toBe(1)
      expect(result.current.sessionSigningKeyRef.current).toBe("sk-1")
      expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
    }
  )

  it("enters backoff + dispatches the crypto-failed event on the 3rd failure (lines 314-342)", async () => {
    vi.useFakeTimers()
    const dispatch = vi.spyOn(window, "dispatchEvent")
    const failure = new Error("503")
    mocks.apiGet.mockRejectedValue(failure)
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
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
    expect(warningSpy).toHaveBeenCalledWith(
      "[SessionCrypto] Max retries reached for signing key fetch",
      { err: failure }
    )
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
    warningSpy.mockRestore()
    vi.useRealTimers()
  })

  it("clears the in-flight promise when failure notification throws", async () => {
    vi.useFakeTimers()
    mocks.apiGet.mockRejectedValue(new Error("503"))
    vi.spyOn(window, "dispatchEvent").mockImplementationOnce(() => {
      throw new Error("event unavailable")
    })
    const { result } = renderHook(() => useSessionCrypto())

    await expectConsoleWarning(
      "[SessionCrypto] Max retries reached for signing key fetch",
      async () => {
        await act(async () => {
          await result.current.ensureSessionSigningKey()
          await result.current.ensureSessionSigningKey()
          await expect(result.current.ensureSessionSigningKey()).rejects.toThrow(
            "event unavailable"
          )
        })
      }
    )

    expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
    vi.runAllTimers()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("opens the retry circuit without development logging in production", async () => {
    vi.stubEnv("DEV", false)
    vi.useFakeTimers()
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })

    expect(result.current.signingKeyRetryCountRef.current).toBe(3)
    vi.runAllTimers()
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
    // Keep the strict console guard active for the normal path, but capture a
    // diagnostic if a mutant attempts to call postMessage on the null active
    // worker.  The assertion below must fail that mutant without converting
    // its expected negative-path probe into an out-of-test runtime error.
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
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
    expect(warningSpy).not.toHaveBeenCalled()
    warningSpy.mockRestore()
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
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { result } = renderHook(() => useSessionCrypto())
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })

    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-throw", { force: true })
      })
    ).resolves.not.toThrow()
    expect(postMessage).toHaveBeenCalled()
    expect(warningSpy).toHaveBeenCalledWith("Failed to post message to service worker", {
      error: expect.any(Error),
    })
    warningSpy.mockRestore()
  })

  it("swallows controller failures without development logging in production", async () => {
    vi.stubEnv("DEV", false)
    const postMessage = vi.fn(() => {
      throw new Error("worker stopped")
    })
    const { result } = renderHook(() => useSessionCrypto())
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: undefined },
    })

    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-production", { force: true })
      })
    ).resolves.not.toThrow()
  })

  it("swallows service-worker readiness failures", async () => {
    const ready = Promise.reject(new Error("registration failed"))
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { result } = renderHook(() => useSessionCrypto())
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: null, ready },
    })

    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-ready-failure", { force: true })
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(warningSpy).toHaveBeenCalledWith("Failed to deliver message to service worker", {
      error: expect.any(Error),
    })
    warningSpy.mockRestore()
  })

  it("swallows readiness failures without development logging in production", async () => {
    vi.stubEnv("DEV", false)
    const ready = Promise.reject(new Error("registration failed"))
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { result } = renderHook(() => useSessionCrypto())
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: null, ready },
    })

    await act(async () => {
      await result.current.sendSessionCacheUpdate("sk-ready-production", { force: true })
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(warningSpy).not.toHaveBeenCalled()
    warningSpy.mockRestore()
  })

  it("does not dispatch when the service-worker readiness handle is absent", async () => {
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: null, ready: undefined },
    })
    const { result } = renderHook(() => useSessionCrypto())

    await expect(
      act(async () => {
        await result.current.sendSessionCacheUpdate("sk-no-ready", { force: true })
      })
    ).resolves.not.toThrow()
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

  it("deduplicates concurrent requests when the backoff window expires", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4999)
      await expect(
        Promise.all([
          result.current.ensureSessionSigningKey(),
          result.current.ensureSessionSigningKey(),
        ])
      ).resolves.toEqual([null, null])
    })
    expect(mocks.apiGet).toHaveBeenCalledTimes(3)

    let resolveRequest!: (value: { data: { signing_key: string } }) => void
    const response = new Promise<{ data: { signing_key: string } }>((resolve) => {
      resolveRequest = resolve
    })
    mocks.apiGet.mockReturnValue(response)
    const pending: Promise<string | null>[] = []
    try {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1)
        pending.push(result.current.ensureSessionSigningKey())
        pending.push(result.current.ensureSessionSigningKey())
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(4)
      await act(async () => {
        resolveRequest({ data: { signing_key: "recovered-key" } })
        await expect(Promise.all(pending)).resolves.toEqual(["recovered-key", "recovered-key"])
      })
    } finally {
      await act(async () => {
        resolveRequest({ data: { signing_key: "recovered-key" } })
        await Promise.allSettled(pending)
      })
    }
  })
})

// ---------------------------------------------------------------------------
// unmount cleanup clears the backoff timer — lines 367-373
// ---------------------------------------------------------------------------

describe("unmount cleanup", () => {
  it("does not clear a timer when no backoff is pending", () => {
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    const { unmount } = renderHook(() => useSessionCrypto())

    clearSpy.mockClear()
    act(() => {
      unmount()
    })

    expect(clearSpy).not.toHaveBeenCalled()
    clearSpy.mockRestore()
    vi.useRealTimers()
  })

  it("clears a pending backoff timer on unmount (lines 369-372)", async () => {
    vi.useFakeTimers()
    mocks.apiGet.mockRejectedValue(new Error("503"))
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    const { result, unmount } = renderHook(() => useSessionCrypto())

    // Trip the backoff so signingKeyBackoffTimerRef holds a live timer id.
    await act(async () => {
      await result.current.ensureSessionSigningKey()
      await result.current.ensureSessionSigningKey()
    })
    await expectConsoleWarning(
      "[SessionCrypto] Max retries reached for signing key fetch",
      async () => {
        await act(async () => {
          await result.current.ensureSessionSigningKey()
        })
      }
    )

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

describe("signing key handoff ownership", () => {
  it("rejects stale cache synchronization until an explicit key update", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", { serviceWorker: { controller: { postMessage } } })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.sendSessionCacheUpdate("old-cache-key"))
    postMessage.mockClear()
    vi.mocked(cryptoWorker.pbkdf2).mockClear()

    rotateBrowserSession()
    await act(() => result.current.sendSessionCacheUpdate("old-cache-key", { force: true }))
    expect(cryptoWorker.pbkdf2).not.toHaveBeenCalled()
    expect(postMessage).not.toHaveBeenCalled()

    await act(() => result.current.updateSessionSigningKey("new-session-key"))
    expect(result.current.isCurrentSigningSession()).toBe(true)
    expect(postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "mock_pbkdf2",
      sessionScope: `mock_pbkdf2:${getBrowserSessionGeneration()}`,
    })
    expect(mocks.apiGet).not.toHaveBeenCalled()
  })

  it("rotates its browser generation on an explicit A-to-B key replacement", async () => {
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey("key-a"))
    const firstGeneration = getBrowserSessionGeneration()
    expect(firstGeneration).not.toBeNull()
    expect(result.current.isCurrentSigningSession()).toBe(true)

    await act(() => result.current.updateSessionSigningKey("key-b"))
    expect(getBrowserSessionGeneration()).not.toBeNull()
    expect(getBrowserSessionGeneration()).not.toBe(firstGeneration)
    expect(result.current.isCurrentSigningSession()).toBe(true)
    expect(result.current.sessionSigningKey).toBe("key-b")
    await expect(result.current.ensureSessionSigningKey()).resolves.toBe("key-b")
    expect(mocks.apiGet).not.toHaveBeenCalled()
  })

  it("preserves its browser generation when the same signing key is installed again", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", { serviceWorker: { controller: { postMessage } } })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey("same-session-key"))
    const generation = getBrowserSessionGeneration()
    expect(result.current.isCurrentSigningSession()).toBe(true)
    postMessage.mockClear()

    await act(() => result.current.updateSessionSigningKey("same-session-key"))
    expect(getBrowserSessionGeneration()).toBe(generation)
    expect(result.current.isCurrentSigningSession()).toBe(true)
    await expect(result.current.ensureSessionSigningKey()).resolves.toBe("same-session-key")
    expect(mocks.apiGet).not.toHaveBeenCalled()
    expect(postMessage.mock.calls.map(([message]) => message)).toEqual([
      { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE },
      {
        type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
        sessionHash: "mock_pbkdf2",
        sessionScope: `mock_pbkdf2:${generation}`,
      },
    ])
  })

  it("preserves a foreign browser generation when clearing a stale signing key", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", { serviceWorker: { controller: { postMessage } } })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey("previous-session-key"))
    const previousGeneration = getBrowserSessionGeneration()
    rotateBrowserSession()
    const foreignGeneration = getBrowserSessionGeneration()
    expect(foreignGeneration).not.toBe(previousGeneration)
    expect(result.current.isCurrentSigningSession()).toBe(false)
    postMessage.mockClear()

    await act(() => result.current.updateSessionSigningKey(null))
    expect(getBrowserSessionGeneration()).toBe(foreignGeneration)
    expect(result.current.sessionSigningKey).toBeNull()
    expect(result.current.isCurrentSigningSession()).toBe(false)
    expect(postMessage.mock.calls.map(([message]) => message)).toEqual([
      { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE },
      { type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY, sessionHash: undefined },
    ])

    await act(() => result.current.updateSessionSigningKey("current-session-key"))
    expect(getBrowserSessionGeneration()).toBe(foreignGeneration)
    expect(result.current.isCurrentSigningSession()).toBe(true)
    await expect(result.current.ensureSessionSigningKey()).resolves.toBe("current-session-key")
    expect(mocks.apiGet).not.toHaveBeenCalled()
    expect(postMessage).toHaveBeenLastCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "mock_pbkdf2",
      sessionScope: `mock_pbkdf2:${foreignGeneration}`,
    })
  })

  it("invalidates captured session work before the first signing key finishes hashing", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", { serviceWorker: { controller: { postMessage } } })
    rotateBrowserSession()
    const generation = getBrowserSessionGeneration()
    const isPriorWorkCurrent = captureSessionEpoch()
    expect(isPriorWorkCurrent()).toBe(true)
    let resolveHash!: (value: string) => void
    const hash = new Promise<string>((resolve) => {
      resolveHash = resolve
    })
    vi.mocked(cryptoWorker.pbkdf2).mockReturnValueOnce(hash)
    const { result } = renderHook(() => useSessionCrypto())
    let pending: Promise<void> | undefined
    try {
      act(() => {
        pending = result.current.updateSessionSigningKey("new-session-key")
      })
      expect(result.current.sessionSigningKey).toBe("new-session-key")
      expect(getBrowserSessionGeneration()).toBe(generation)
      expect(isPriorWorkCurrent()).toBe(false)
      expect(result.current.isCurrentSigningSession()).toBe(false)
      expect(postMessage.mock.calls.map(([message]) => message)).toEqual([
        { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE },
      ])

      await act(async () => {
        resolveHash("new-session-hash")
        await pending
      })
      expect(result.current.isCurrentSigningSession()).toBe(true)
      expect(captureSessionEpoch()()).toBe(true)
      expect(postMessage).toHaveBeenLastCalledWith({
        type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
        sessionHash: "new-session-hash",
        sessionScope: `new-session-hash:${generation}`,
      })
    } finally {
      await act(async () => {
        resolveHash("new-session-hash")
        await Promise.allSettled([hash, ...(pending ? [pending] : [])])
      })
    }
  })

  it("counts an owned derivation failure when ensure rotates a cache-only identity", async () => {
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.sendSessionCacheUpdate("old-cache-key"))
    const cacheGeneration = getBrowserSessionGeneration()
    expect(cacheGeneration).not.toBeNull()
    expect(result.current.sessionSigningKey).toBeNull()

    mocks.apiGet.mockResolvedValue({ data: { signing_key: "fetched-key" } })
    vi.mocked(cryptoWorker.pbkdf2).mockRejectedValueOnce(new Error("worker unavailable"))
    await act(async () => {
      await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
    })

    expect(getBrowserSessionGeneration()).not.toBeNull()
    expect(getBrowserSessionGeneration()).not.toBe(cacheGeneration)
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    expect(result.current.sessionSigningKey).toBe("fetched-key")
    expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
    expect(result.current.signingKeyRetryCountRef.current).toBe(1)
  })

  it("does not adopt a foreign generation rotated synchronously by derivation", async () => {
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.sendSessionCacheUpdate("old-cache-key"))
    const cacheGeneration = getBrowserSessionGeneration()
    let installedGeneration: string | null = null
    vi.mocked(cryptoWorker.pbkdf2).mockImplementationOnce(() => {
      installedGeneration = getBrowserSessionGeneration()
      rotateBrowserSession()
      throw new Error("foreign session overtook derivation")
    })

    await act(async () => {
      await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
    })

    expect(installedGeneration).not.toBeNull()
    expect(installedGeneration).not.toBe(cacheGeneration)
    expect(getBrowserSessionGeneration()).not.toBe(installedGeneration)
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
    expect(result.current.signingKeyRetryCountRef.current).toBe(0)
  })

  it("counts synchronous network failures while the request still owns the session", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    mocks.apiGet.mockImplementation(() => {
      throw new Error("network unavailable")
    })
    const { result } = renderHook(() => useSessionCrypto())

    await act(async () => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
      }
    })
    expect(mocks.apiGet).toHaveBeenCalledTimes(3)
    expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
    expect(dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "auth:session-crypto-failed",
        detail: { reason: "max_retries_exceeded", backoffMs: 5000 },
      })
    )
    await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
    expect(mocks.apiGet).toHaveBeenCalledTimes(3)
  })

  it("blocks failure-event reentry before a synchronous request assigns its promise", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    mocks.apiGet.mockImplementation(() => {
      throw new Error("network unavailable")
    })
    const { result } = renderHook(() => useSessionCrypto())
    const reentered: Promise<string | null>[] = []
    const onFailure = () => {
      reentered.push(result.current.ensureSessionSigningKey())
    }
    window.addEventListener("auth:session-crypto-failed", onFailure, { once: true })
    try {
      await act(async () => {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
        }
        await expect(Promise.all(reentered)).resolves.toEqual([null])
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(3)

      mocks.apiGet.mockResolvedValue({ data: { signing_key: "recovered-key" } })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
        await expect(result.current.ensureSessionSigningKey()).resolves.toBe("recovered-key")
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(4)
    } finally {
      window.removeEventListener("auth:session-crypto-failed", onFailure)
      await act(async () => {
        await Promise.allSettled(reentered)
      })
    }
  })

  it("preserves a request started by a synchronous failure listener after session clear", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    mocks.apiGet.mockImplementation(() => {
      throw new Error("network unavailable")
    })
    let rejectRequest!: (error: Error) => void
    const response = new Promise<{ data: { signing_key: string } }>((_resolve, reject) => {
      rejectRequest = reject
    })
    const { result } = renderHook(() => useSessionCrypto())
    const pending: Promise<string | null>[] = []
    const updates: Promise<void>[] = []
    const onFailure = () => {
      updates.push(result.current.updateSessionSigningKey(null))
      mocks.apiGet.mockReturnValueOnce(response)
      pending.push(result.current.ensureSessionSigningKey())
    }
    window.addEventListener("auth:session-crypto-failed", onFailure, { once: true })
    try {
      await act(async () => {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
        }
        for (let caller = 0; caller < 3; caller += 1) {
          pending.push(result.current.ensureSessionSigningKey())
          await Promise.resolve()
          await Promise.resolve()
        }
        rejectRequest(new Error("current request failed"))
        await Promise.all(pending)
      })
      const backoffDelays = dispatchEvent.mock.calls
        .map(([event]) => event)
        .filter((event): event is CustomEvent => event.type === "auth:session-crypto-failed")
        .map((event) => (event.detail as { backoffMs: number }).backoffMs)
      expect({ requests: mocks.apiGet.mock.calls.length, backoffDelays }).toEqual({
        requests: 4,
        backoffDelays: [5000],
      })
    } finally {
      window.removeEventListener("auth:session-crypto-failed", onFailure)
      await act(async () => {
        rejectRequest(new Error("request cleanup"))
        await Promise.allSettled([response, ...pending, ...updates])
      })
    }
  })

  it("does not share a request overtaken by a generation change during dispatch", async () => {
    let resolveRequest!: (value: { data: { signing_key: string } }) => void
    const response = new Promise<{ data: { signing_key: string } }>((resolve) => {
      resolveRequest = resolve
    })
    mocks.apiGet.mockImplementationOnce(() => {
      rotateBrowserSession()
      return response
    })
    const { result } = renderHook(() => useSessionCrypto())
    const pending: Promise<string | null>[] = []
    try {
      await act(async () => {
        pending.push(result.current.ensureSessionSigningKey())
        pending.push(result.current.ensureSessionSigningKey())
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(2)
      await act(async () => {
        resolveRequest({ data: { signing_key: "obsolete-key" } })
        await expect(Promise.all(pending)).resolves.toEqual([null, "sk-1"])
      })
      expect(result.current.sessionSigningKey).toBe("sk-1")
    } finally {
      await act(async () => {
        resolveRequest({ data: { signing_key: "obsolete-key" } })
        await Promise.allSettled([response, ...pending])
      })
    }
  })

  it.each(["key replacement", "browser generation rotation"])(
    "ignores cache-key derivation rejection after %s during hashing",
    async (transition) => {
      vi.stubEnv("DEV", false)
      const dispatchEvent = vi.spyOn(window, "dispatchEvent")
      let rejectHash!: (error: Error) => void
      const hash = new Promise<string>((_resolve, reject) => {
        rejectHash = reject
      })
      vi.mocked(cryptoWorker.pbkdf2).mockReturnValueOnce(hash)
      const { result } = renderHook(() => useSessionCrypto())
      let pending: Promise<string | null> | undefined
      try {
        await act(async () => {
          pending = result.current.ensureSessionSigningKey()
          await Promise.resolve()
        })
        expect(result.current.sessionSigningKey).toBe("sk-1")
        if (transition === "key replacement") {
          await act(() => result.current.updateSessionSigningKey("replacement-key"))
        } else {
          rotateBrowserSession()
        }
        await act(async () => {
          rejectHash(new Error("obsolete derivation failed"))
          await expect(pending).resolves.toBeNull()
        })
        expect(result.current.sessionSigningKey).toBe(
          transition === "key replacement" ? "replacement-key" : "sk-1"
        )
        expect(mocks.apiGet).toHaveBeenCalledTimes(1)
        expect(result.current.sessionSigningKeyPromiseRef.current).toBeNull()
        expect(result.current.signingKeyRetryCountRef.current).toBe(0)
        expect(dispatchEvent.mock.calls.map(([event]) => event.type)).not.toContain(
          "auth:session-crypto-failed"
        )
      } finally {
        await act(async () => {
          rejectHash(new Error("obsolete derivation cleanup"))
          await Promise.allSettled([hash, ...(pending ? [pending] : [])])
        })
      }
    }
  )

  it("does not open backoff when obsolete requests reject after a key replacement", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    const rejectRequests: Array<(error: Error) => void> = []
    mocks.apiGet.mockImplementation(
      () => new Promise((_resolve, reject) => rejectRequests.push(reject))
    )
    const { result } = renderHook(() => useSessionCrypto())
    const pending: Promise<string | null>[] = []
    try {
      await act(async () => {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          pending.push(result.current.ensureSessionSigningKey())
          await result.current.updateSessionSigningKey(null)
        }
        await result.current.updateSessionSigningKey("replacement-key")
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(3)

      await act(async () => {
        for (const reject of rejectRequests) reject(new Error("obsolete request failed"))
        await expect(Promise.all(pending)).resolves.toEqual([null, null, null])
      })
      await expect(result.current.ensureSessionSigningKey()).resolves.toBe("replacement-key")
      expect(result.current.sessionSigningKey).toBe("replacement-key")
      expect(mocks.apiGet).toHaveBeenCalledTimes(3)
      expect(dispatchEvent.mock.calls.map(([event]) => event.type)).not.toContain(
        "auth:session-crypto-failed"
      )
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      await act(async () => {
        for (const reject of rejectRequests) reject(new Error("obsolete request cleanup"))
        await Promise.allSettled(pending)
      })
    }
  })

  it("does not count a rejected request from a previous browser generation", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    const dispatchEvent = vi.spyOn(window, "dispatchEvent")
    let rejectRequest!: (error: Error) => void
    const response = new Promise<{ data: { signing_key: string } }>((_resolve, reject) => {
      rejectRequest = reject
    })
    mocks.apiGet.mockReturnValueOnce(response)
    const { result } = renderHook(() => useSessionCrypto())
    const pending = result.current.ensureSessionSigningKey()
    try {
      rotateBrowserSession()
      await act(async () => {
        rejectRequest(new Error("previous generation failed"))
        await expect(pending).resolves.toBeNull()
      })

      mocks.apiGet.mockRejectedValue(new Error("current generation failed"))
      await act(async () => {
        await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
        await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(3)
      expect(dispatchEvent.mock.calls.map(([event]) => event.type)).not.toContain(
        "auth:session-crypto-failed"
      )

      await act(async () => {
        await expect(result.current.ensureSessionSigningKey()).resolves.toBeNull()
      })
      expect(mocks.apiGet).toHaveBeenCalledTimes(4)
      expect(dispatchEvent).toHaveBeenLastCalledWith(
        expect.objectContaining({
          type: "auth:session-crypto-failed",
          detail: { reason: "max_retries_exceeded", backoffMs: 5000 },
        })
      )
    } finally {
      await act(async () => {
        rejectRequest(new Error("previous generation cleanup"))
        await Promise.allSettled([response, pending])
      })
    }
  })

  it("does not accept a rejected key lookup after the session was cleared", async () => {
    let reject!: (error: Error) => void
    mocks.apiGet.mockImplementationOnce(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail
        })
    )
    const { result } = renderHook(() => useSessionCrypto())
    const pending = result.current.ensureSessionSigningKey()
    await act(() => result.current.updateSessionSigningKey(null))
    reject(new Error("old session rejected"))
    await expect(pending).resolves.toBeNull()
    expect(result.current.sessionSigningKeyRef.current).toBeNull()
  })

  it("does not return an old fetched key after an explicit replacement during hashing", async () => {
    const replacementKey = crypto.randomUUID()
    let release!: (hash: string) => void
    vi.mocked(cryptoWorker.pbkdf2).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve
        })
    )
    const { result } = renderHook(() => useSessionCrypto())
    const pending = result.current.ensureSessionSigningKey()
    await waitFor(() => expect(release).toBeDefined())
    await act(() => result.current.updateSessionSigningKey(replacementKey))
    await act(async () => {
      release("old-hash")
      await pending
    })
    await expect(pending).resolves.toBeNull()
    expect(result.current.sessionSigningKeyRef.current).toBe(replacementKey)
  })

  it("does not announce a private namespace when origin storage cannot establish it", async () => {
    const controller = { postMessage: vi.fn() }
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { controller } })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage denied")
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey(crypto.randomUUID()))
    expect(result.current.isCurrentSigningSession()).toBe(false)
    expect(
      controller.postMessage.mock.calls
        .map(([message]) => message)
        .some((message) => message.sessionHash)
    ).toBe(false)
  })

  it("ignores foreign workers and unrelated messages before answering its controller", async () => {
    const listeners = new Map<string, (event: MessageEvent) => void>()
    const controller = { postMessage: vi.fn() }
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        controller,
        addEventListener: (type: string, callback: (event: MessageEvent) => void) =>
          listeners.set(type, callback),
        removeEventListener: (type: string) => listeners.delete(type),
      },
    })
    const { result } = renderHook(() => useSessionCrypto())
    await act(() => result.current.updateSessionSigningKey(crypto.randomUUID()))
    const reply = vi.fn()
    const event = {
      source: controller,
      data: { type: SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY },
      ports: [{ postMessage: reply }],
    }
    listeners.get("message")!({ ...event, source: {} } as unknown as MessageEvent)
    listeners.get("message")!({ ...event, data: { type: "unrelated" } } as unknown as MessageEvent)
    expect(reply).not.toHaveBeenCalled()
    listeners.get("message")!(event as unknown as MessageEvent)
    expect(reply).toHaveBeenCalledWith(expect.objectContaining({ sessionHash: "mock_pbkdf2" }))
  })
})
