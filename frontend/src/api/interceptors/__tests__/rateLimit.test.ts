import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"

import {
  RATE_LIMIT_DEFAULT_DELAY_MS,
  RATE_LIMIT_MAX_RETRY,
  isRateLimited,
  releaseClientQueueSlot,
  scheduleRateLimitWindow,
  waitForClientQueueSlot,
  waitForRateLimitWindow,
} from "../rateLimit"

type Cfg = InternalAxiosRequestConfig & {
  __clientRateLimitAcquired?: boolean
  signal?: AbortSignal
}

const makeConfig = (method = "get", signal?: AbortSignal): Cfg =>
  ({ method, signal, headers: {} }) as Cfg

describe("rateLimit interceptor — constants", () => {
  it("exposes the documented default delay + max retry", () => {
    expect(RATE_LIMIT_DEFAULT_DELAY_MS).toBe(2000)
    expect(RATE_LIMIT_MAX_RETRY).toBe(2)
  })
})

describe("rateLimit interceptor — client queue slot acquire/release", () => {
  it("acquires a slot for GET and marks the config as acquired", async () => {
    const config = makeConfig("get")
    await waitForClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBe(false)
  })

  it("uppercase GET is throttled (method normalized to lowercase)", async () => {
    const config = makeConfig("GET")
    await waitForClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(config)
  })

  it("does NOT throttle non-GET methods (POST passes through without acquiring)", async () => {
    const config = makeConfig("post")
    await waitForClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBeUndefined()
    // release is a no-op when nothing was acquired
    releaseClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBeUndefined()
  })

  it("defaults method to get when missing on config", async () => {
    const config = { headers: {} } as Cfg
    await waitForClientQueueSlot(config)
    expect(config.__clientRateLimitAcquired).toBe(true)
    releaseClientQueueSlot(config)
  })

  it("release with no config is a safe no-op", () => {
    expect(() => releaseClientQueueSlot()).not.toThrow()
  })

  it("release without the acquired flag is a no-op", () => {
    const config = makeConfig("get")
    expect(config.__clientRateLimitAcquired).toBeUndefined()
    expect(() => releaseClientQueueSlot(config)).not.toThrow()
    expect(config.__clientRateLimitAcquired).toBeUndefined()
  })

  it("throws synchronously when the config signal is already aborted before acquire", async () => {
    const controller = new AbortController()
    controller.abort()
    const config = makeConfig("get", controller.signal)
    await expect(waitForClientQueueSlot(config)).rejects.toBeInstanceOf(DOMException)
    expect(config.__clientRateLimitAcquired).toBeUndefined()
  })

  it("throws the abort reason when it is an Error instance", async () => {
    const controller = new AbortController()
    const reason = new Error("user navigated away")
    controller.abort(reason)
    const config = makeConfig("get", controller.signal)
    await expect(waitForClientQueueSlot(config)).rejects.toBe(reason)
  })
})

describe("rateLimit interceptor — rate-limit window scheduling", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(async () => {
    // Drain any pending rate-limit window so module-level state doesn't leak
    // into the next test (the module has no public reset hook).
    await vi.runAllTimersAsync()
    vi.useRealTimers()
  })

  it("isRateLimited is false before any window is scheduled", () => {
    expect(isRateLimited()).toBe(false)
  })

  it("waitForRateLimitWindow resolves immediately when no window is active", async () => {
    await expect(waitForRateLimitWindow()).resolves.toBeUndefined()
  })

  it("scheduleRateLimitWindow opens a window and clears it after the delay elapses", async () => {
    scheduleRateLimitWindow(5_000)
    expect(isRateLimited()).toBe(true)

    let resolved = false
    const waitPromise = waitForRateLimitWindow().then(() => {
      resolved = true
    })

    // window still active — the wait should not have resolved yet
    await vi.advanceTimersByTimeAsync(1_000)
    expect(resolved).toBe(false)
    expect(isRateLimited()).toBe(true)

    // fast-forward past the window — the scheduled timer fires + drains waiters
    await vi.advanceTimersByTimeAsync(5_000)
    await waitPromise
    expect(resolved).toBe(true)
    expect(isRateLimited()).toBe(false)
  })

  it("does not reschedule when a later window target is requested while one is pending", () => {
    scheduleRateLimitWindow(10_000)
    expect(isRateLimited()).toBe(true)
    // A shorter/earlier delay should keep blocking — request a later one (<= reset),
    // covering the early-return branch that avoids extending the active window.
    scheduleRateLimitWindow(5_000)
    expect(isRateLimited()).toBe(true)
  })

  it("treats a negative delay as zero (window already expired)", () => {
    scheduleRateLimitWindow(-1_000)
    expect(isRateLimited()).toBe(false)
  })

  it("waitForRateLimitWindow rejects when the signal is already aborted", async () => {
    scheduleRateLimitWindow(10_000)
    const controller = new AbortController()
    controller.abort()
    await expect(waitForRateLimitWindow(controller.signal)).rejects.toBeInstanceOf(DOMException)
  })

  it("waitForRateLimitWindow rejects mid-wait when the signal aborts", async () => {
    scheduleRateLimitWindow(10_000)
    const controller = new AbortController()
    const rejection = expect(waitForRateLimitWindow(controller.signal)).rejects.toBeInstanceOf(
      DOMException
    )
    controller.abort()
    await rejection
  })
})
