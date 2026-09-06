import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"

type QueueConfig = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

const makeConfig = (method = "get", signal?: AbortSignal): QueueConfig =>
  ({ method, headers: {}, signal }) as QueueConfig

const flushMicrotasks = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

/**
 * The interceptor keeps its counters at module scope and reads its limits at
 * import time.  Loading a fresh module per test makes each contract describe a
 * single, deterministic limiter instance instead of relying on private reset
 * hooks or leaking queue state between tests.
 */
describe("rateLimit mutation contracts", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "20")
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it.each([
    ["zero", "0"],
    ["non-numeric", "not-a-number"],
  ])("falls back to a positive request limit for %s configuration", async (_label, value) => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", value)
    const { waitForClientQueueSlot, releaseClientQueueSlot } = await import("../rateLimit")
    const request = makeConfig()

    // A zero/NaN limit would queue the very first request forever.  Inspect
    // the marker after a bounded microtask flush so a broken configuration
    // fails fast instead of turning into a mutation-test timeout.
    void waitForClientQueueSlot(request)
    await flushMicrotasks()

    expect(request.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(request)
  })

  it("keeps an explicit decimal parser radix for prefixed values", async () => {
    // Number.parseInt("0x10", 10) is zero and therefore uses the documented
    // fallback.  Omitting the radix would parse it as hexadecimal (16), which
    // would unexpectedly throttle the seventeenth request.
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "0x10")
    const { waitForClientQueueSlot, releaseClientQueueSlot } = await import("../rateLimit")
    const requests = Array.from({ length: 17 }, () => makeConfig())

    for (const request of requests.slice(0, 16)) {
      await waitForClientQueueSlot(request)
    }

    void waitForClientQueueSlot(requests[16]!)
    await flushMicrotasks()

    expect(requests[16]!.__clientRateLimitAcquired).toBe(true)
    for (const request of requests) {
      releaseClientQueueSlot(request)
    }
  })

  it("preserves the default abort message for primitive reasons", async () => {
    const { waitForClientQueueSlot } = await import("../rateLimit")
    const controller = new AbortController()
    controller.abort("navigation cancelled")

    await expect(
      waitForClientQueueSlot(makeConfig("get", controller.signal))
    ).rejects.toMatchObject({
      name: "AbortError",
      message: "Aborted",
    })
  })

  it("keeps an active window waiter pending when no signal is provided", async () => {
    const { scheduleRateLimitWindow, waitForRateLimitWindow } = await import("../rateLimit")

    scheduleRateLimitWindow(10_000)
    let settled = false
    const waiter = waitForRateLimitWindow().then(() => {
      settled = true
    })
    await flushMicrotasks()

    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(10_000)
    await waiter
    expect(settled).toBe(true)
  })

  it("registers the abort listener with the canonical event and once option", async () => {
    const { scheduleRateLimitWindow, waitForRateLimitWindow } = await import("../rateLimit")
    const controller = new AbortController()
    const addEventListenerSpy = vi.spyOn(controller.signal, "addEventListener")

    scheduleRateLimitWindow(10_000)
    const waiter = waitForRateLimitWindow(controller.signal)

    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "abort",
      expect.any(Function),
      expect.objectContaining({ once: true })
    )

    controller.abort()
    await expect(waiter).rejects.toMatchObject({ name: "AbortError", message: "Aborted" })
  })

  it("does not replace an equal server-window target", async () => {
    const { isRateLimited, scheduleRateLimitWindow } = await import("../rateLimit")
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout")

    scheduleRateLimitWindow(10_000)
    scheduleRateLimitWindow(10_000)

    expect(isRateLimited()).toBe(true)
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1)
  })

  it("returns immediately at the exact server-window expiry boundary", async () => {
    const { scheduleRateLimitWindow, waitForRateLimitWindow } = await import("../rateLimit")

    scheduleRateLimitWindow(10_000)
    vi.setSystemTime(Date.now() + 10_000)

    let settledAtBoundary = false
    void waitForRateLimitWindow().then(() => {
      settledAtBoundary = true
    })
    await flushMicrotasks()

    expect(settledAtBoundary).toBe(true)
  })

  it("does not decrement a queue counter for a phantom acquired marker", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const phantom = makeConfig()
    phantom.__clientRateLimitAcquired = true
    releaseClientQueueSlot(phantom)

    const first = makeConfig()
    const second = makeConfig()
    const third = makeConfig()
    await waitForClientQueueSlot(first)
    await waitForClientQueueSlot(second)
    const thirdWait = waitForClientQueueSlot(third)
    const acquiredImmediately = await Promise.race([
      thirdWait.then(() => true),
      Promise.resolve(false),
    ])

    expect(acquiredImmediately).toBe(false)
    releaseClientQueueSlot(first)
    await thirdWait
    expect(third.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(second)
    releaseClientQueueSlot(third)
  })

  it("does not release a GET queue slot for an acquired non-GET request", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = makeConfig("get")
    const queued = makeConfig("get")
    const post = makeConfig("post")

    await waitForClientQueueSlot(first)
    const queuedWait = waitForClientQueueSlot(queued)
    await flushMicrotasks()
    expect(queued.__clientRateLimitAcquired).toBeUndefined()

    post.__clientRateLimitAcquired = true
    releaseClientQueueSlot(post)
    await flushMicrotasks()
    expect(queued.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(first)
    await queuedWait
    expect(queued.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(queued)
  })

  it("drains an expired online window safely when no waiters are queued", async () => {
    const { isRateLimited, scheduleRateLimitWindow } = await import("../rateLimit")

    scheduleRateLimitWindow(10_000)
    vi.setSystemTime(Date.now() + 10_001)

    expect(() => window.dispatchEvent(new Event("online"))).not.toThrow()
    expect(isRateLimited()).toBe(false)
  })

  it("keeps parser and timer arithmetic explicit at their boundaries", async () => {
    const { getClientQueueResetDelay, parsePositiveInteger } = await import("../rateLimit")

    expect(parsePositiveInteger(undefined, 90)).toBe(90)
    expect(parsePositiveInteger(null, 90)).toBe(90)
    expect(parsePositiveInteger("12", 90)).toBe(12)
    expect(parsePositiveInteger("0", 90)).toBe(90)
    expect(getClientQueueResetDelay(10_000, 9_000)).toBe(1_000)
    expect(getClientQueueResetDelay(9_000, 10_000)).toBe(0)
  })

  it("does not over-admit at the exact concurrency boundary", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = makeConfig()
    const second = makeConfig()
    const third = makeConfig()

    await waitForClientQueueSlot(first)
    await waitForClientQueueSlot(second)
    let settled = false
    const thirdWait = waitForClientQueueSlot(third).then(() => {
      settled = true
    })
    await flushMicrotasks()
    expect(settled).toBe(false)
    expect(third.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(first)
    await thirdWait
    expect(third.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(second)
    releaseClientQueueSlot(third)
  })

  it("removes an aborted queued waiter and wakes the next request", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const active = makeConfig()
    const firstController = new AbortController()
    const first = makeConfig("get", firstController.signal)
    const second = makeConfig()

    await waitForClientQueueSlot(active)
    const firstWait = waitForClientQueueSlot(first)
    const secondWait = waitForClientQueueSlot(second)
    await flushMicrotasks()

    firstController.abort()
    await expect(firstWait).rejects.toMatchObject({ name: "AbortError" })
    expect(second.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(active)
    await secondWait
    expect(second.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(second)
  })

  it("is safe when releasing the final slot without queued waiters", async () => {
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const request = makeConfig()
    await waitForClientQueueSlot(request)
    expect(() => releaseClientQueueSlot(request)).not.toThrow()
    expect(request.__clientRateLimitAcquired).toBe(false)
  })
})
