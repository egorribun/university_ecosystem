import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"

import api, { resetEtagCache } from "../client"
import { registerSigningKeyAccessor, responseCache } from "../interceptors/etagCache"
import { testEvents } from "@/tests/mocks/handlers"

const ETAG_KEY = "events:retry"
const ETAG = '"etag-123"'
const SIGNING_KEY = "fixture-".repeat(4)
const originalAdapter = api.defaults.adapter

const make429 = (config: InternalAxiosRequestConfig) =>
  Object.assign(new Error("Too Many Requests"), {
    config,
    response: {
      status: 429,
      statusText: "Too Many Requests",
      headers: AxiosHeaders.from({ "retry-after": "1" }),
      data: { detail: "slow down" },
      config,
    },
  })

describe("API ETag retry behavior", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetEtagCache()
    registerSigningKeyAccessor(() => SIGNING_KEY)
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
    resetEtagCache()
    registerSigningKeyAccessor(() => null)
    vi.useRealTimers()
  })

  it("restores the signed body when a retryable 429 is followed by a matching 304", async () => {
    const page = {
      items: testEvents.slice(0, 1),
      total: 1,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    }
    const seenConditions: Array<string | null> = []
    let calls = 0
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      calls += 1
      const condition = AxiosHeaders.from(config.headers).get("if-none-match")
      seenConditions.push(typeof condition === "string" ? condition : null)

      if (calls === 1) {
        return {
          config,
          data: page,
          headers: AxiosHeaders.from({ etag: ETAG, "content-type": "application/json" }),
          status: 200,
          statusText: "OK",
        }
      }
      if (calls === 2) throw make429(config)
      return {
        config,
        data: null,
        headers: AxiosHeaders.from({ etag: ETAG }),
        status: 304,
        statusText: "Not Modified",
      }
    }

    const config = {
      etagCacheKey: ETAG_KEY,
      validateStatus: (status: number) => status === 304 || (status >= 200 && status < 300),
    }
    const seeded = await api.get("/events", config as never)
    expect(seeded.status).toBe(200)
    expect(responseCache.get(ETAG_KEY)?.data).toEqual(page)

    const pending = api.get("/events", config as never)
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(1_000)
    await vi.advanceTimersByTimeAsync(0)

    const retried = await pending
    expect(calls).toBe(3)
    expect(seenConditions).toEqual([null, ETAG, ETAG])
    expect(retried).toMatchObject({ status: 200, data: page })
  })
})
