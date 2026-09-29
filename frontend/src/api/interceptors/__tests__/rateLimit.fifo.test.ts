import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"

type QueueConfig = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

const makeConfig = (method = "get"): QueueConfig => ({ method, headers: {} }) as QueueConfig

/** Settle every queued microtask without advancing fake time. */
const settle = () => vi.advanceTimersByTimeAsync(0)

/** Queue requests and record the order in which they are admitted. */
const queueRequests = (
  waitForClientQueueSlot: (config: QueueConfig) => Promise<void>,
  count: number
) => {
  const requests = Array.from({ length: count }, () => makeConfig())
  const admitted: number[] = []
  requests.forEach((request, index) => {
    void waitForClientQueueSlot(request).then(() => admitted.push(index))
  })
  return { requests, admitted }
}

describe("rateLimit queue ordering", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("serves concurrency-blocked requests in arrival order", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const [first, second] = [makeConfig(), makeConfig()]
    await waitForClientQueueSlot(first)
    await waitForClientQueueSlot(second)
    const { admitted } = queueRequests(waitForClientQueueSlot, 4)
    await settle()
    expect(admitted).toStrictEqual([])

    releaseClientQueueSlot(first)
    await settle()
    expect(admitted).toStrictEqual([0])

    releaseClientQueueSlot(second)
    await settle()
    expect(admitted).toStrictEqual([0, 1])
  })

  it("serves window-blocked requests in arrival order as the rolling window expires", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "3")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const early = makeConfig()
    await waitForClientQueueSlot(early)
    releaseClientQueueSlot(early)
    vi.setSystemTime(30_000)
    for (const request of [makeConfig(), makeConfig()]) {
      await waitForClientQueueSlot(request)
      releaseClientQueueSlot(request)
    }

    const { requests, admitted } = queueRequests(waitForClientQueueSlot, 6)
    await settle()
    expect(admitted).toStrictEqual([])

    // t = 60 s: only the first timestamp has expired -> exactly one grant.
    await vi.advanceTimersByTimeAsync(30_000)
    expect(admitted).toStrictEqual([0])
    releaseClientQueueSlot(requests[0])

    // t = 90 s: the two 30 s timestamps expire -> the next two in line.
    await vi.advanceTimersByTimeAsync(30_000)
    expect(admitted).toStrictEqual([0, 1, 2])
  })

  it("does not free a GET slot when an acquired non-GET marker is released", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const active = makeConfig()
    const queued = makeConfig()
    await waitForClientQueueSlot(active)
    void waitForClientQueueSlot(queued)
    await settle()

    const post = makeConfig("post")
    post.__clientRateLimitAcquired = true
    releaseClientQueueSlot(post)
    await settle()

    expect(post.__clientRateLimitAcquired).toBe(false)
    expect(queued.__clientRateLimitAcquired).toBeUndefined()
    releaseClientQueueSlot(active)
    await settle()
    expect(queued.__clientRateLimitAcquired).toBe(true)
  })
})
