import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"

type QueueConfig = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

const config = (method = "get"): QueueConfig =>
  ({
    method,
    headers: {},
  }) as QueueConfig

describe("rateLimit interceptor — queue/window closure", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "2")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("releases a queued GET when a concurrent slot is freed", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = config()
    const second = config()
    const third = config()
    const fourth = config()

    await Promise.all([waitForClientQueueSlot(first), waitForClientQueueSlot(second)])
    const thirdWait = waitForClientQueueSlot(third)
    const fourthWait = waitForClientQueueSlot(fourth)
    await Promise.resolve()
    expect(third.__clientRateLimitAcquired).toBeUndefined()
    expect(fourth.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(first)
    await thirdWait
    expect(third.__clientRateLimitAcquired).toBe(true)
    await Promise.resolve()
    expect(fourth.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(second)
    await fourthWait
    expect(fourth.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(third)
    releaseClientQueueSlot(fourth)
  })

  it("waits for the rolling request window before acquiring another slot", async () => {
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = config()
    const second = config()
    const third = config()
    const fourth = config()

    await waitForClientQueueSlot(first)
    releaseClientQueueSlot(first)
    await waitForClientQueueSlot(second)
    releaseClientQueueSlot(second)

    const thirdWait = waitForClientQueueSlot(third)
    const fourthWait = waitForClientQueueSlot(fourth)
    await Promise.resolve()
    expect(third.__clientRateLimitAcquired).toBeUndefined()
    expect(fourth.__clientRateLimitAcquired).toBeUndefined()

    const completedRequest = config()
    completedRequest.__clientRateLimitAcquired = true
    releaseClientQueueSlot(completedRequest)

    await vi.advanceTimersByTimeAsync(60_000)
    await Promise.all([thirdWait, fourthWait])
    expect(third.__clientRateLimitAcquired).toBe(true)
    expect(fourth.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(third)
    releaseClientQueueSlot(fourth)
  })

  it("does not resolve a queued request while all concurrent slots remain busy", async () => {
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = config()
    const second = config()
    const third = config()

    await Promise.all([waitForClientQueueSlot(first), waitForClientQueueSlot(second)])
    const thirdWait = waitForClientQueueSlot(third)
    await Promise.resolve()

    await vi.advanceTimersByTimeAsync(60_000)
    expect(third.__clientRateLimitAcquired).toBeUndefined()

    releaseClientQueueSlot(first)
    await thirdWait
    expect(third.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(second)
    releaseClientQueueSlot(third)
  })

  it("replaces a pending server-rate-limit timer when a later target is scheduled", async () => {
    const { isRateLimited, scheduleRateLimitWindow } = await import("../rateLimit")

    scheduleRateLimitWindow(10_000)
    scheduleRateLimitWindow(20_000)
    expect(isRateLimited()).toBe(true)

    await vi.advanceTimersByTimeAsync(19_999)
    expect(isRateLimited()).toBe(true)
    await vi.advanceTimersByTimeAsync(1)
    expect(isRateLimited()).toBe(false)
  })

  it("unblocks an expired rate-limit window on the browser online event", async () => {
    const { isRateLimited, scheduleRateLimitWindow, waitForRateLimitWindow } =
      await import("../rateLimit")

    scheduleRateLimitWindow(10_000)
    const waiter = waitForRateLimitWindow()
    vi.setSystemTime(Date.now() + 10_000)
    window.dispatchEvent(new Event("online"))

    await waiter
    expect(isRateLimited()).toBe(false)
  })

  it("does not decrement the GET queue for a manually-marked non-GET config", async () => {
    const { releaseClientQueueSlot } = await import("../rateLimit")
    const postConfig = config("post")
    postConfig.__clientRateLimitAcquired = true

    releaseClientQueueSlot(postConfig)

    expect(postConfig.__clientRateLimitAcquired).toBe(false)
  })
})
