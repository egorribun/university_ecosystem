import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetModules()
  localStorage.removeItem(SESSION_GENERATION_KEY)
  vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "100")
  vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
})

afterEach(() => {
  localStorage.removeItem(SESSION_GENERATION_KEY)
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

it("does not retry a 429 before the server's Retry-After window expires", async () => {
  const { default: api } = await import("@/api/client")
  const requests: Array<{ url: string | undefined; params: unknown; at: number }> = []

  api.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    requests.push({ url: config.url, params: config.params, at: Date.now() })
    if (requests.length === 1) {
      throw Object.assign(new Error("Too Many Requests"), {
        config,
        response: {
          status: 429,
          statusText: "Too Many Requests",
          headers: AxiosHeaders.from({ "retry-after": "3" }),
          data: { detail: "Too Many Requests" },
          config,
        },
      })
    }
    return {
      config,
      data: { items: ["recovered"] },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }
  }

  const pending = api.get("/news", { params: { limit: 12 } })
  // Observe an early rejection while preserving it for the final assertion.
  void pending.catch(() => undefined)
  await vi.advanceTimersByTimeAsync(0)
  expect(requests).toHaveLength(1)

  await vi.advanceTimersByTimeAsync(2_999)
  expect(requests).toHaveLength(1)

  await vi.advanceTimersByTimeAsync(1)
  await expect(pending).resolves.toMatchObject({ status: 200, data: { items: ["recovered"] } })
  expect(requests).toHaveLength(2)
  expect(requests[1]).toMatchObject({ url: requests[0]!.url, params: { limit: 12 } })
  expect(requests[1]!.at - requests[0]!.at).toBe(3_000)
})
