import type { InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type QueueConfig = Omit<InternalAxiosRequestConfig, "signal"> & {
  __clientRateLimitAcquired?: boolean
}

const makeConfig = (method = "get"): QueueConfig => ({ method, headers: {} }) as QueueConfig

const flushMicrotasks = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe("rateLimit release gating", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("does not wake a queued GET when releasing an acquired non-GET marker", async () => {
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const active = makeConfig()
    const queued = makeConfig()

    await waitForClientQueueSlot(active)
    const queuedWait = waitForClientQueueSlot(queued)
    await flushMicrotasks()

    const post = makeConfig("post")
    post.__clientRateLimitAcquired = true
    releaseClientQueueSlot(post)
    await flushMicrotasks()

    expect(queued.__clientRateLimitAcquired).toBeUndefined()
    let settled = false
    void queuedWait.then(() => {
      settled = true
    })
    await flushMicrotasks()
    expect(settled).toBe(false)

    releaseClientQueueSlot(active)
    await queuedWait
    expect(queued.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(queued)
  })
})
