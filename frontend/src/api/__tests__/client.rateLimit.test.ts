import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import type { AxiosResponse } from "axios"

describe("API client rate limit queue", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
    vi.unstubAllEnvs()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "3")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "2")
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("queues rapid navigation bursts to avoid 429 responses", async () => {
    const { default: api } = await import("@/api/client")

    const startTimes: number[] = []
    let inFlight = 0
    let peakInFlight = 0

    const adapter = vi.fn(async (config): Promise<AxiosResponse<{ ok: boolean }>> => {
      inFlight += 1
      peakInFlight = Math.max(peakInFlight, inFlight)
      startTimes.push(Date.now())

      await new Promise((resolve) => setTimeout(resolve, 100))

      inFlight -= 1
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: {},
        request: {},
      }
    })

    api.defaults.adapter = adapter

    const pending = Array.from({ length: 5 }, () => api.get("/news"))

    await vi.advanceTimersByTimeAsync(100)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(100)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(60_000)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(200)
    await Promise.resolve()

    await Promise.all(pending)

    expect(adapter).toHaveBeenCalledTimes(5)
    expect(peakInFlight).toBeLessThanOrEqual(2)
    expect(peakInFlight).toBe(2)
    expect(startTimes.length).toBe(5)
    const baseline = startTimes[0] ?? 0
    const relativeTimes = startTimes.map((time) => time - baseline)

    expect(Math.max(...relativeTimes.slice(0, 3))).toBeLessThan(60_000)
    expect(relativeTimes[3]!).toBeGreaterThanOrEqual(60_000)
    expect(relativeTimes[4]!).toBeGreaterThanOrEqual(60_000)
    expect(relativeTimes[3]! - relativeTimes[2]!).toBeGreaterThanOrEqual(59_500)
  })

  it("does not queue SSR requests in the browser-only rate limiter", async () => {
    vi.stubGlobal("window", undefined)

    const { default: api } = await import("@/api/client")
    const adapter = vi.fn(async (config): Promise<AxiosResponse<{ ok: boolean }>> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: {},
      request: {},
    }))
    api.defaults.adapter = adapter

    const requests = Array.from({ length: 5 }, () => api.get("/news"))

    await vi.advanceTimersByTimeAsync(0)

    expect(adapter).toHaveBeenCalledTimes(5)
    await Promise.all(requests)
  })
})
