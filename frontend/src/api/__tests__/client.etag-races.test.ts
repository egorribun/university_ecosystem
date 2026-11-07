import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders, type AxiosResponse } from "axios"

import api, { isAbortError, resetEtagCache } from "../client"
import {
  clearCachesOnLogout,
  etagCache,
  registerSigningKeyAccessor,
  responseCache,
} from "../interceptors/etagCache"
import * as rateLimit from "../interceptors/rateLimit"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const KEY = "events:session-race"
const originalAdapter = api.defaults.adapter

beforeEach(() => {
  resetEtagCache()
  registerSigningKeyAccessor(() => "session-a")
})

afterEach(() => {
  api.defaults.adapter = originalAdapter
  vi.restoreAllMocks()
  clearCachesOnLogout()
  registerSigningKeyAccessor(() => null)
})

describe("ETag interceptor request ownership", () => {
  it("rejects a response from the previous session before caching it with the new key", async () => {
    const entered = deferred()
    const gate = deferred()
    const release = vi.spyOn(rateLimit, "releaseClientQueueSlot")
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      entered.resolve()
      await gate.promise
      return {
        config,
        data: { owner: "a" },
        headers: AxiosHeaders.from({ etag: '"a"', "content-type": "application/json" }),
        status: 200,
        statusText: "OK",
      }
    }
    const pending = api.get("/events", { etagCacheKey: KEY } as never)
    const result = pending.then(
      (value) => ({ value, error: undefined }),
      (error: unknown) => ({ value: undefined, error })
    )
    await entered.promise
    invalidateSessionEpoch()
    clearCachesOnLogout()
    registerSigningKeyAccessor(() => "session-b")
    gate.resolve()
    const settled = await result

    expect(isAbortError(settled.error)).toBe(true)
    expect(settled.value).toBeUndefined()
    expect(responseCache.get(KEY)).toBeUndefined()
    expect(etagCache.get(KEY)).toBeUndefined()
    expect(release).toHaveBeenCalledTimes(1)
  })

  it.each([200, 304])(
    "rejects a %s result if its request loses ownership during HMAC and releases its slot",
    async (status) => {
      const release = vi.spyOn(rateLimit, "releaseClientQueueSlot")
      api.defaults.adapter = async (config): Promise<AxiosResponse> => ({
        config,
        data: { owner: "a" },
        headers: AxiosHeaders.from({ etag: '"a"', "content-type": "application/json" }),
        status: 200,
        statusText: "OK",
      })
      if (status === 304) await api.get("/events", { etagCacheKey: KEY } as never)
      release.mockClear()
      api.defaults.adapter = async (config): Promise<AxiosResponse> => ({
        config,
        data: status === 304 ? null : { owner: "a" },
        headers: AxiosHeaders.from({ etag: '"a"', "content-type": "application/json" }),
        status,
        statusText: "OK",
      })
      const realSign = crypto.subtle.sign.bind(crypto.subtle)
      vi.spyOn(crypto.subtle, "sign").mockImplementationOnce(async (...args) => {
        // This is the request owner's epoch, independent of the cache's epoch.
        invalidateSessionEpoch()
        return realSign(...args)
      })

      await expect(api.get("/events", { etagCacheKey: KEY } as never)).rejects.toSatisfy(
        isAbortError
      )
      expect(release).toHaveBeenCalledTimes(1)
      if (status === 200) expect(responseCache.get(KEY)).toBeUndefined()
    }
  )

  it("releases the queue slot if HMAC computation rejects", async () => {
    const release = vi.spyOn(rateLimit, "releaseClientQueueSlot")
    api.defaults.adapter = async (config): Promise<AxiosResponse> => ({
      config,
      data: { owner: "a" },
      headers: AxiosHeaders.from({ etag: '"a"', "content-type": "application/json" }),
      status: 200,
      statusText: "OK",
    })
    vi.spyOn(crypto.subtle, "sign").mockRejectedValueOnce(new Error("HMAC unavailable"))
    await expect(api.get("/events", { etagCacheKey: KEY } as never)).rejects.toThrow(
      "HMAC unavailable"
    )
    expect(release).toHaveBeenCalledTimes(1)
    expect(responseCache.get(KEY)).toBeUndefined()
  })
})
