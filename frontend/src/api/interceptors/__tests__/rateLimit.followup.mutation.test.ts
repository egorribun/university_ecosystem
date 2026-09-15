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

describe("rate-limit follow-up mutation contracts", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "90")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("drops an entirely expired timestamp prefix before admitting a new request", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "1")
    vi.setSystemTime(1_000_000)
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = makeConfig()
    const second = makeConfig()

    await waitForClientQueueSlot(first)
    releaseClientQueueSlot(first)
    vi.setSystemTime(1_060_001)

    await waitForClientQueueSlot(second)
    expect(second.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(second)
  })

  it("schedules a positive rolling-window delay from the oldest timestamp", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "1")
    vi.setSystemTime(1_000_000)
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const first = makeConfig()
    const controller = new AbortController()
    const queued = makeConfig("get", controller.signal)

    await waitForClientQueueSlot(first)
    releaseClientQueueSlot(first)
    vi.setSystemTime(1_000_001)

    const timeoutSpy = vi.spyOn(globalThis, "setTimeout")
    const pending = waitForClientQueueSlot(queued)
    await flushMicrotasks()

    expect(timeoutSpy.mock.calls.at(-1)?.[1]).toBe(59_999)
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: "AbortError" })
  })

  it("rejects a queued waiter promptly when its signal aborts", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const active = makeConfig()
    const controller = new AbortController()
    const queued = makeConfig("get", controller.signal)

    await waitForClientQueueSlot(active)
    const pending = waitForClientQueueSlot(queued)
    await flushMicrotasks()

    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: "AbortError" })
    releaseClientQueueSlot(active)
  })

  it("does not discard a later waiter when a granted waiter aborts in the race window", async () => {
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "1")
    const { releaseClientQueueSlot, waitForClientQueueSlot } = await import("../rateLimit")
    const active = makeConfig()
    const grantedController = new AbortController()
    const nextController = new AbortController()
    const granted = makeConfig("get", grantedController.signal)
    const next = makeConfig("get", nextController.signal)

    await waitForClientQueueSlot(active)
    const grantedWait = waitForClientQueueSlot(granted)
    let nextSettled = false
    const nextWait = waitForClientQueueSlot(next).then(() => {
      nextSettled = true
    })
    await flushMicrotasks()

    releaseClientQueueSlot(active)
    grantedController.abort()
    await expect(grantedWait).rejects.toMatchObject({ name: "AbortError" })

    for (let index = 0; index < 20 && !nextSettled; index += 1) {
      await Promise.resolve()
    }

    expect(nextSettled).toBe(true)
    if (next.__clientRateLimitAcquired) {
      releaseClientQueueSlot(next)
    } else {
      nextController.abort()
      await expect(nextWait).rejects.toMatchObject({ name: "AbortError" })
    }
  })

  it("keeps the original abort message for a pre-aborted server-window waiter", async () => {
    const { scheduleRateLimitWindow, waitForRateLimitWindow } = await import("../rateLimit")
    const controller = new AbortController()

    scheduleRateLimitWindow(10_000)
    controller.abort()

    await expect(waitForRateLimitWindow(controller.signal)).rejects.toMatchObject({
      name: "AbortError",
      message: "Aborted",
    })
  })

  it("does not clear an active server window when the browser comes back online", async () => {
    const { isRateLimited, scheduleRateLimitWindow, waitForRateLimitWindow } =
      await import("../rateLimit")
    scheduleRateLimitWindow(10_000)
    let settled = false
    const waiter = waitForRateLimitWindow().then(() => {
      settled = true
    })

    window.dispatchEvent(new Event("online"))
    await flushMicrotasks()

    expect(isRateLimited()).toBe(true)
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(10_000)
    await waiter
    expect(settled).toBe(true)
  })

  it("does not run expired-window cleanup when no server window is active", async () => {
    const { isRateLimited } = await import("../rateLimit")
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")

    window.dispatchEvent(new Event("online"))

    expect(clearTimeoutSpy).not.toHaveBeenCalled()
    expect(isRateLimited()).toBe(false)
  })
})
