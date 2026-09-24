import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"
type QueueConfig = InternalAxiosRequestConfig & { __clientRateLimitAcquired?: boolean }
const makeConfig = (): QueueConfig => ({ method: "get", headers: {} }) as QueueConfig

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "2")
  vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
})
afterEach(() => {
  vi.clearAllTimers()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

/**
 * Rolling-window liveness: capacity freed by an expiring timestamp must wake
 * the next queued request even when no request finishes in the meantime.
 */
it("admits the next waiter when the rolling window frees capacity while a request is still in flight", async () => {
  vi.setSystemTime(0)
  const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
  const a = makeConfig()
  const b = makeConfig()
  await waitForClientQueueSlot(a)
  releaseClientQueueSlot(a)
  vi.setSystemTime(30_000)
  await waitForClientQueueSlot(b)
  releaseClientQueueSlot(b)
  const w1 = makeConfig()
  const w2 = makeConfig()
  void waitForClientQueueSlot(w1)
  void waitForClientQueueSlot(w2)
  await vi.advanceTimersByTimeAsync(30_001) // t = 60_001: a expired
  expect(w1.__clientRateLimitAcquired).toBe(true)
  expect(w2.__clientRateLimitAcquired).toBeUndefined()
  // w1 stays in flight (e.g. a long-running GET). b expires at t = 90_000.
  await vi.advanceTimersByTimeAsync(30_000)
  expect(w2.__clientRateLimitAcquired).toBe(true)
})
