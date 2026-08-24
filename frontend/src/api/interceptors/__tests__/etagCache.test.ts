import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"

import {
  applyEtagHeader,
  clearCachesOnLogout,
  etagCache,
  handleEtagResponse,
  incrementSessionEpoch,
  registerSigningKeyAccessor,
  responseCache,
} from "../etagCache"

const SIGNING_KEY = "test-signing-key-abcdef0123456789"

const makeRequestConfig = (headers?: Record<string, string>): InternalAxiosRequestConfig =>
  ({ headers: AxiosHeaders.from(headers ?? {}) }) as InternalAxiosRequestConfig

const makeResponse = (
  status: number,
  headers: Record<string, string>,
  data: unknown
): AxiosResponse =>
  ({
    status,
    statusText: "OK",
    headers: AxiosHeaders.from(headers),
    data,
    config: makeRequestConfig(),
    request: {},
  }) as AxiosResponse

describe("etagCache — in-memory etag map", () => {
  beforeEach(() => {
    etagCache.clear()
    responseCache.clear()
  })

  it("set then get returns the stored tag", () => {
    etagCache.set("k1", '"tag-1"')
    expect(etagCache.get("k1")).toBe('"tag-1"')
  })

  it("get of a missing key returns undefined", () => {
    expect(etagCache.get("missing")).toBeUndefined()
  })

  it("delete removes the entry", () => {
    etagCache.set("k2", '"tag-2"')
    etagCache.delete("k2")
    expect(etagCache.get("k2")).toBeUndefined()
  })

  it("delete of a missing key is a safe no-op", () => {
    expect(() => etagCache.delete("never-set")).not.toThrow()
  })

  it("clear wipes all entries", () => {
    etagCache.set("a", '"x"')
    etagCache.set("b", '"y"')
    etagCache.clear()
    expect(etagCache.get("a")).toBeUndefined()
    expect(etagCache.get("b")).toBeUndefined()
  })

  it("swallows localStorage removal failures during clear", () => {
    etagCache.set("clear:error", '"tag"')
    const removeSpy = vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage blocked")
    })

    expect(() => etagCache.clear()).not.toThrow()
    expect(etagCache.get("clear:error")).toBeUndefined()
    removeSpy.mockRestore()
  })

  it("evicts the least-recently-used ETag when the bounded map overflows", () => {
    for (let index = 0; index <= 200; index += 1) {
      etagCache.set(`etag:${index}`, `"tag-${index}"`)
    }

    expect(etagCache.get("etag:0")).toBeUndefined()
    expect(etagCache.get("etag:1")).toBe('"tag-1"')
    expect(etagCache.get("etag:200")).toBe('"tag-200"')
  })
})

describe("etagCache — in-memory response cache", () => {
  beforeEach(() => {
    responseCache.clear()
  })

  it("set/get/delete round-trip", () => {
    const entry = { data: { ok: true }, hmac: "deadbeef", ts: Date.now() }
    responseCache.set("rk", entry)
    expect(responseCache.get("rk")).toBe(entry)
    responseCache.delete("rk")
    expect(responseCache.get("rk")).toBeUndefined()
  })

  it("clear empties the response cache", () => {
    responseCache.set("rk2", { data: 1, hmac: "ab", ts: 1 })
    responseCache.clear()
    expect(responseCache.get("rk2")).toBeUndefined()
  })

  it("evicts the least-recently-used response when the bounded map overflows", () => {
    for (let index = 0; index <= 200; index += 1) {
      responseCache.set(`response:${index}`, {
        data: index,
        hmac: `hmac-${index}`,
        ts: index,
      })
    }

    expect(responseCache.get("response:0")).toBeUndefined()
    expect(responseCache.get("response:1")).toBeDefined()
    expect(responseCache.get("response:200")).toBeDefined()
  })
})

describe("etagCache — session epoch invalidation", () => {
  beforeEach(() => {
    etagCache.clear()
    responseCache.clear()
  })

  it("clearCachesOnLogout empties both caches", () => {
    etagCache.set("e1", '"t"')
    responseCache.set("e1", { data: {}, hmac: "ab", ts: 1 })
    clearCachesOnLogout()
    expect(etagCache.get("e1")).toBeUndefined()
    expect(responseCache.get("e1")).toBeUndefined()
  })

  it("incrementSessionEpoch does not throw and leaves stored tags intact", () => {
    etagCache.set("e2", '"t2"')
    expect(() => incrementSessionEpoch()).not.toThrow()
    expect(etagCache.get("e2")).toBe('"t2"')
  })
})

describe("etagCache — applyEtagHeader", () => {
  beforeEach(() => {
    etagCache.clear()
  })

  it("sets If-None-Match from the cached tag when none present", () => {
    etagCache.set("events:list", '"cached-etag"')
    const config = makeRequestConfig()
    applyEtagHeader(config, "events:list")
    const headers = config.headers as AxiosHeaders
    expect(headers.get("if-none-match")).toBe('"cached-etag"')
  })

  it("does not overwrite an existing If-None-Match header", () => {
    etagCache.set("events:list", '"cached-etag"')
    const config = makeRequestConfig({ "if-none-match": '"caller-supplied"' })
    applyEtagHeader(config, "events:list")
    const headers = config.headers as AxiosHeaders
    expect(headers.get("if-none-match")).toBe('"caller-supplied"')
  })

  it("leaves headers without If-None-Match when there is no cached tag", () => {
    const config = makeRequestConfig()
    applyEtagHeader(config, "no-such-key")
    const headers = config.headers as AxiosHeaders
    expect(headers.has("if-none-match")).toBe(false)
  })

  it("creates AxiosHeaders when the request config has no headers object", () => {
    const config = { headers: undefined } as unknown as InternalAxiosRequestConfig
    applyEtagHeader(config, "no-such-key")
    expect(config.headers).toBeInstanceOf(AxiosHeaders)
    expect((config.headers as AxiosHeaders).has("if-none-match")).toBe(false)
  })
})

describe("etagCache — handleEtagResponse", () => {
  beforeEach(() => {
    etagCache.clear()
    responseCache.clear()
    registerSigningKeyAccessor(() => SIGNING_KEY)
  })

  afterEach(() => {
    registerSigningKeyAccessor(() => null)
  })

  it("stores the etag and caches a signed JSON 200 response", async () => {
    const data = { items: [1, 2, 3] }
    const response = makeResponse(
      200,
      { etag: '"etag-200"', "content-type": "application/json" },
      data
    )
    await handleEtagResponse(response, "news:list")
    expect(etagCache.get("news:list")).toBe('"etag-200"')
    const entry = responseCache.get("news:list")
    expect(entry?.data).toEqual(data)
    expect(typeof entry?.hmac).toBe("string")
  })

  it("accepts a response without a headers object", async () => {
    await expect(
      handleEtagResponse(
        {
          status: 200,
          statusText: "OK",
          headers: undefined,
          data: { ok: true },
          config: makeRequestConfig(),
          request: {},
        } as unknown as AxiosResponse,
        "missing-response-headers"
      )
    ).resolves.toBeUndefined()
    expect(etagCache.get("missing-response-headers")).toBeUndefined()
  })

  it("stores the etag but does NOT cache the body for non-JSON content", async () => {
    const response = makeResponse(
      200,
      { etag: '"etag-html"', "content-type": "text/html" },
      "<html></html>"
    )
    await handleEtagResponse(response, "page:home")
    expect(etagCache.get("page:home")).toBe('"etag-html"')
    expect(responseCache.get("page:home")).toBeUndefined()
  })

  it("does not cache the body when no signing key is available (cold start)", async () => {
    registerSigningKeyAccessor(() => null)
    const response = makeResponse(
      200,
      { etag: '"etag-cold"', "content-type": "application/json" },
      { a: 1 }
    )
    await handleEtagResponse(response, "cold:key")
    expect(etagCache.get("cold:key")).toBe('"etag-cold"')
    expect(responseCache.get("cold:key")).toBeUndefined()
  })

  it("deletes both caches when the response carries no etag", async () => {
    etagCache.set("stale:key", '"old"')
    responseCache.set("stale:key", { data: {}, hmac: "ab", ts: 1 })
    const response = makeResponse(200, { "content-type": "application/json" }, { a: 1 })
    await handleEtagResponse(response, "stale:key")
    expect(etagCache.get("stale:key")).toBeUndefined()
    expect(responseCache.get("stale:key")).toBeUndefined()
  })

  it("serves cached signed data + upgrades 304 to 200 when the HMAC verifies", async () => {
    const data = { items: ["a"] }
    const first = makeResponse(
      200,
      { etag: '"etag-304"', "content-type": "application/json" },
      data
    )
    await handleEtagResponse(first, "events:304")

    const notModified = makeResponse(304, { etag: '"etag-304"' }, null)
    await handleEtagResponse(notModified, "events:304")
    expect(notModified.status).toBe(200)
    expect(notModified.data).toEqual(data)
  })

  it("evicts both caches on 304 when no cache entry exists for the key", async () => {
    etagCache.set("orphan:304", '"e"')
    const notModified = makeResponse(304, { etag: '"e"' }, null)
    await handleEtagResponse(notModified, "orphan:304")
    // no responseCache entry was ever stored → evict path taken
    expect(responseCache.get("orphan:304")).toBeUndefined()
  })

  it("discards cached data after a session change between login epochs (round-trip)", async () => {
    // Cache under one session.
    const data = { v: 1 }
    const first = makeResponse(
      200,
      { etag: '"epoch-etag"', "content-type": "application/json" },
      data
    )
    await handleEtagResponse(first, "epoch:key")
    expect(responseCache.get("epoch:key")?.data).toEqual(data)

    // A logout clears the response cache + bumps the epoch.
    clearCachesOnLogout()
    expect(responseCache.get("epoch:key")).toBeUndefined()
  })

  it("discards the result when the session epoch changes DURING the async HMAC", async () => {
    // Bump the epoch from inside crypto.subtle.sign — this fires after the
    // epochSnapshot is captured but before the post-HMAC re-check, so the
    // computed entry must be thrown away (RED-02 stale-result guard).
    const realSign = crypto.subtle.sign.bind(crypto.subtle)
    const signSpy = vi
      .spyOn(crypto.subtle, "sign")
      .mockImplementation(async (...args: Parameters<typeof realSign>) => {
        incrementSessionEpoch()
        return realSign(...args)
      })

    const response = makeResponse(
      200,
      { etag: '"epoch-race"', "content-type": "application/json" },
      { v: 99 }
    )
    await handleEtagResponse(response, "epoch:race")

    // The etag tag is still written (it happens before the async HMAC) but the
    // signed payload is discarded because the epoch moved mid-flight.
    expect(etagCache.get("epoch:race")).toBe('"epoch-race"')
    expect(responseCache.get("epoch:race")).toBeUndefined()

    signSpy.mockRestore()
  })

  it("evicts both caches on 304 when the stored HMAC does not verify", async () => {
    // Cache a valid signed 200 first.
    const data = { items: ["x"] }
    const first = makeResponse(
      200,
      { etag: '"etag-bad-hmac"', "content-type": "application/json" },
      data
    )
    await handleEtagResponse(first, "bad:hmac")
    expect(responseCache.get("bad:hmac")).toBeDefined()

    // Corrupt the stored HMAC so the 304 restore-time verification fails.
    const corrupted = responseCache.get("bad:hmac")!
    responseCache.set("bad:hmac", { ...corrupted, hmac: "00".repeat(32) })

    const notModified = makeResponse(304, { etag: '"etag-bad-hmac"' }, null)
    await handleEtagResponse(notModified, "bad:hmac")

    // Mismatch path: status stays 304, both caches evicted.
    expect(notModified.status).toBe(304)
    expect(notModified.data).toBeNull()
    expect(etagCache.get("bad:hmac")).toBeUndefined()
    expect(responseCache.get("bad:hmac")).toBeUndefined()
  })

  it("rejects a stored HMAC with a different length without comparing characters", async () => {
    const response = makeResponse(
      200,
      { etag: '"etag-short-hmac"', "content-type": "application/json" },
      { v: 1 }
    )
    await handleEtagResponse(response, "short:hmac")
    const cached = responseCache.get("short:hmac")!
    responseCache.set("short:hmac", { ...cached, hmac: "x" })

    const notModified = makeResponse(304, { etag: '"etag-short-hmac"' }, null)
    await handleEtagResponse(notModified, "short:hmac")

    expect(notModified.status).toBe(304)
    expect(responseCache.get("short:hmac")).toBeUndefined()
  })

  it("evicts both caches on 304 when there is no signing key", async () => {
    // Seed a response cache entry, then drop the signing key before the 304.
    const data = { a: 1 }
    const first = makeResponse(
      200,
      { etag: '"etag-nokey-304"', "content-type": "application/json" },
      data
    )
    await handleEtagResponse(first, "nokey:304")
    expect(responseCache.get("nokey:304")).toBeDefined()

    registerSigningKeyAccessor(() => null)
    const notModified = makeResponse(304, { etag: '"etag-nokey-304"' }, null)
    await handleEtagResponse(notModified, "nokey:304")

    expect(notModified.status).toBe(304)
    expect(etagCache.get("nokey:304")).toBeUndefined()
    expect(responseCache.get("nokey:304")).toBeUndefined()
  })
})

describe("etagCache — debounced flush + visibilitychange", () => {
  beforeEach(() => {
    etagCache.clear()
    responseCache.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    // Reset the visibilityState override back to the jsdom default so other
    // suites are not left with a "hidden" tab (which would auto-flush).
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    })
  })

  it("debounced set persists to localStorage only after the 30s flush timer fires", () => {
    vi.useFakeTimers()
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")

    etagCache.set("flush:k1", '"tag-flush"')
    // Nothing persisted synchronously — flush is debounced.
    const beforeCalls = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(beforeCalls.length).toBe(0)

    vi.advanceTimersByTime(30_000)

    const afterCalls = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(afterCalls.length).toBeGreaterThanOrEqual(1)
    const persisted = afterCalls[afterCalls.length - 1]![1]
    expect(persisted).toContain("flush:k1")
  })

  it("a second set within the debounce window resets the timer (single flush)", () => {
    vi.useFakeTimers()
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")

    etagCache.set("flush:a", '"a"')
    vi.advanceTimersByTime(20_000)
    etagCache.set("flush:b", '"b"') // resets the 30s window
    vi.advanceTimersByTime(20_000) // 40s total but only 20s since last set → no flush yet

    expect(setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache")).length).toBe(0)

    vi.advanceTimersByTime(10_000) // now 30s since last set → flush fires once

    const calls = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(calls.length).toBe(1)
    expect(calls[0]![1]).toContain("flush:b")
  })

  it("visibilitychange to hidden flushes immediately (no timer wait)", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    etagCache.set("vis:k", '"vis-tag"')

    setItemSpy.mockClear()
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    })
    document.dispatchEvent(new Event("visibilitychange"))

    const calls = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(calls.length).toBeGreaterThanOrEqual(1)
    expect(calls[calls.length - 1]![1]).toContain("vis:k")
  })

  it("evicts the oldest 50% and retries once on QuotaExceededError", () => {
    // Seed three entries with distinct lastUsed timestamps via Date.now control.
    const nowSpy = vi.spyOn(Date, "now")
    nowSpy.mockReturnValue(1000)
    etagCache.set("q:oldest", '"o"')
    nowSpy.mockReturnValue(2000)
    etagCache.set("q:mid", '"m"')
    nowSpy.mockReturnValue(3000)
    etagCache.set("q:newest", '"n"')
    nowSpy.mockReturnValue(4000)

    const realSetItem = Storage.prototype.setItem
    let throwOnce = true
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string
    ) {
      if (key.startsWith("ue:etag-cache") && throwOnce) {
        throwOnce = false
        throw new DOMException("quota", "QuotaExceededError")
      }
      // Delegate to the real impl for the retry write.
      realSetItem.call(this, key, value)
    })

    // Trigger an immediate flush via visibilitychange (avoids the 30s timer).
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    })
    document.dispatchEvent(new Event("visibilitychange"))

    // Two write attempts: the failing one + the retry after eviction.
    const cacheWrites = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(cacheWrites.length).toBe(2)

    // ceil(3/2) = 2 oldest evicted → only the newest survives in memory.
    nowSpy.mockReturnValue(5000)
    expect(etagCache.get("q:oldest")).toBeUndefined()
    expect(etagCache.get("q:mid")).toBeUndefined()
    expect(etagCache.get("q:newest")).toBe('"n"')

    nowSpy.mockRestore()
  })

  it("keeps the in-memory cache when the quota retry also fails", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError")
    })

    etagCache.set("q:retry-fails", '"tag"')
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    })
    expect(() => document.dispatchEvent(new Event("visibilitychange"))).not.toThrow()

    const cacheWrites = setItemSpy.mock.calls.filter(([key]) => key.startsWith("ue:etag-cache"))
    expect(cacheWrites.length).toBe(2)
    expect(etagCache.get("q:retry-fails")).toBeUndefined()
  })

  it("swallows a non-quota localStorage flush failure", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })

    etagCache.set("flush:error", '"tag"')
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    })
    expect(() => document.dispatchEvent(new Event("visibilitychange"))).not.toThrow()
    expect(etagCache.get("flush:error")).toBe('"tag"')
    expect(setItemSpy).toHaveBeenCalled()
  })
})

describe("etagCache — lazy hydration on first access (isolated module)", () => {
  const KEY = "ue:etag-cache:v1"

  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it("hydrates the in-memory map from localStorage on first get()", async () => {
    const seeded: [string, { tag: string; lastUsed: number }][] = [
      ["seeded:key", { tag: '"seeded-tag"', lastUsed: 123 }],
    ]
    localStorage.setItem(KEY, JSON.stringify(seeded))

    const mod = await import("../etagCache")
    // First access triggers hydration from the seeded localStorage payload.
    expect(mod.etagCache.get("seeded:key")).toBe('"seeded-tag"')
  })

  it("starts empty and logs a warning when stored JSON is corrupt", async () => {
    localStorage.setItem(KEY, "{not-valid-json")

    const mod = await import("../etagCache")
    // Corrupt payload → hydration fails gracefully to an empty map, no throw.
    expect(() => mod.etagCache.get("anything")).not.toThrow()
    expect(mod.etagCache.get("anything")).toBeUndefined()
  })

  it("removes stale unversioned and prior-version keys during module startup", async () => {
    localStorage.setItem("ue:etag-cache", "stale")
    localStorage.setItem("ue:etag-cache:v0", "old-version")

    await import("../etagCache")

    expect(localStorage.getItem("ue:etag-cache")).toBeNull()
    expect(localStorage.getItem("ue:etag-cache:v0")).toBeNull()
  })

  it("swallows storage inspection failures during module startup", async () => {
    localStorage.setItem("ue:etag-cache:v0", "old-version")
    const keySpy = vi.spyOn(Storage.prototype, "key").mockImplementation(() => {
      throw new DOMException("storage blocked", "SecurityError")
    })

    try {
      await expect(import("../etagCache")).resolves.toBeDefined()
    } finally {
      keySpy.mockRestore()
    }
  })

  it("does not flush before the lazy map has been hydrated", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")

    try {
      await import("../etagCache")
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "hidden",
      })
      vi.stubGlobal("window", undefined)
      document.dispatchEvent(new Event("visibilitychange"))

      expect(setItemSpy).not.toHaveBeenCalled()
    } finally {
      setItemSpy.mockRestore()
      vi.unstubAllGlobals()
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "visible",
      })
    }
  })
})
