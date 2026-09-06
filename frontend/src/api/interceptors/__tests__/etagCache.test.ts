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

const SIGNING_KEY = "test-signing-key"
// Independent known-answer vector: this lets the test detect algorithm/encoding
// drift without passing a hard-coded secret to a second HMAC implementation.
const EXPECTED_DIGEST_FOR_KNOWN_PAYLOAD = Array.from(
  new Uint8Array([
    0x69, 0xd4, 0xa6, 0x22, 0xaf, 0x04, 0xdc, 0xbe, 0x5c, 0xf2, 0xdd, 0x5d, 0x59, 0xf0, 0x0e, 0x8b,
    0x27, 0x58, 0x1e, 0xb8, 0xe9, 0xc9, 0xae, 0x81, 0xd1, 0x2d, 0xaf, 0x13, 0xfb, 0xa7, 0xf4, 0xfd,
  ])
)
  .map((value) => value.toString(16).padStart(2, "0"))
  .join("")

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

  it("does not schedule persistence when deleting a missing key", () => {
    vi.useFakeTimers()
    try {
      etagCache.delete("never-scheduled")
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
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
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)

    try {
      expect(() => etagCache.clear()).not.toThrow()
      expect(etagCache.get("clear:error")).toBeUndefined()
      expect(warnSpy).toHaveBeenCalledWith("Failed to remove etag cache", expect.any(Error))
    } finally {
      warnSpy.mockRestore()
      removeSpy.mockRestore()
    }
  })

  it("removes the current ETag key from browser storage when clearing", () => {
    const removeSpy = vi.spyOn(Storage.prototype, "removeItem")
    try {
      etagCache.clear()
      expect(removeSpy).toHaveBeenCalledWith("ue:etag-cache:v1")
    } finally {
      removeSpy.mockRestore()
    }
  })

  it("evicts the least-recently-used ETag when the bounded map overflows", () => {
    for (let index = 0; index <= 200; index += 1) {
      etagCache.set(`etag:${index}`, `"tag-${index}"`)
    }

    expect(etagCache.get("etag:0")).toBeUndefined()
    expect(etagCache.get("etag:1")).toBe('"tag-1"')
    expect(etagCache.get("etag:200")).toBe('"tag-200"')
  })

  it("evicts only the overflow entries and retains the bounded tail", () => {
    const entries = Array.from({ length: 205 }, (_, index) => index)
    for (const index of entries) {
      etagCache.set(`etag:bounded:${index}`, `"tag-${index}"`)
    }

    const evicted = entries.slice(0, 5)
    const retained = entries.slice(5)
    expect(evicted.every((index) => etagCache.get(`etag:bounded:${index}`) === undefined)).toBe(
      true
    )
    expect(retained.every((index) => etagCache.get(`etag:bounded:${index}`) !== undefined)).toBe(
      true
    )
    expect(
      retained.filter((index) => etagCache.get(`etag:bounded:${index}`) !== undefined)
    ).toHaveLength(200)
  })

  it("does not sort the ETag map when an update stays exactly at its bound", () => {
    for (let index = 0; index < 200; index += 1) {
      etagCache.set(`etag:boundary:${index}`, `"tag-${index}"`)
    }

    const entriesSpy = vi.spyOn(Map.prototype, "entries")
    try {
      etagCache.set("etag:boundary:0", '"updated"')
      expect(entriesSpy).not.toHaveBeenCalled()
    } finally {
      entriesSpy.mockRestore()
    }
  })

  it("keeps a recently touched ETag while evicting the oldest untouched entry", () => {
    const nowSpy = vi.spyOn(Date, "now")
    try {
      nowSpy.mockReturnValueOnce(1).mockReturnValueOnce(2).mockReturnValueOnce(3)
      etagCache.set("etag:lru:a", '"a"')
      etagCache.set("etag:lru:b", '"b"')
      etagCache.set("etag:lru:c", '"c"')

      nowSpy.mockReturnValue(4)
      etagCache.get("etag:lru:a")
      for (let index = 0; index < 197; index += 1) {
        nowSpy.mockReturnValue(5 + index)
        etagCache.set(`etag:lru:filler:${index}`, `"${index}"`)
      }
      nowSpy.mockReturnValue(500)
      etagCache.set("etag:lru:overflow", '"overflow"')

      expect(etagCache.get("etag:lru:a")).toBe('"a"')
      expect(etagCache.get("etag:lru:b")).toBeUndefined()
      expect(etagCache.get("etag:lru:c")).toBe('"c"')
    } finally {
      nowSpy.mockRestore()
    }
  })

  it("cancels a pending flush exactly once and does not clear a null timer", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")
    try {
      etagCache.set("timer:pending", '"tag"')
      expect(vi.getTimerCount()).toBe(1)

      etagCache.clear()
      expect(clearTimeoutSpy).toHaveBeenCalledTimes(1)
      expect(vi.getTimerCount()).toBe(0)

      clearTimeoutSpy.mockClear()
      etagCache.clear()
      expect(clearTimeoutSpy).not.toHaveBeenCalled()
    } finally {
      clearTimeoutSpy.mockRestore()
      vi.useRealTimers()
    }
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

  it("exposes the complete response-cache contract", () => {
    expect(responseCache).toEqual(
      expect.objectContaining({
        get: expect.any(Function),
        set: expect.any(Function),
        delete: expect.any(Function),
        clear: expect.any(Function),
      })
    )
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

  it("evicts exactly the response overflow and retains the newest bounded entries", () => {
    const entries = Array.from({ length: 205 }, (_, index) => index)
    for (const index of entries) {
      responseCache.set(`response:bounded:${index}`, {
        data: index,
        hmac: `hmac-${index}`,
        ts: index,
      })
    }

    expect(
      entries
        .slice(0, 5)
        .every((index) => responseCache.get(`response:bounded:${index}`) === undefined)
    ).toBe(true)
    expect(
      entries
        .slice(5)
        .every((index) => responseCache.get(`response:bounded:${index}`) !== undefined)
    ).toBe(true)
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
    const setSpy = vi.spyOn(AxiosHeaders.prototype, "set")
    try {
      applyEtagHeader(config, "no-such-key")
      const headers = config.headers as AxiosHeaders
      expect(headers.has("if-none-match")).toBe(false)
      expect(setSpy).not.toHaveBeenCalled()
    } finally {
      setSpy.mockRestore()
    }
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

  it("uses the canonical SHA-256 hex digest and a non-extractable signing key", async () => {
    const data = { digest: "known-payload" }
    const importKeySpy = vi.spyOn(crypto.subtle, "importKey")
    try {
      const response = makeResponse(
        200,
        { etag: '"etag-digest"', "content-type": "application/json" },
        data
      )
      await handleEtagResponse(response, "digest:key")

      expect(responseCache.get("digest:key")?.hmac).toBe(EXPECTED_DIGEST_FOR_KNOWN_PAYLOAD)
      const [format, keyData, algorithm, extractable, usages] = importKeySpy.mock.calls[0] ?? []
      expect(format).toBe("raw")
      expect(keyData).toBeDefined()
      expect(algorithm).toEqual({ name: "HMAC", hash: "SHA-256" })
      expect(extractable).toBe(false)
      expect(usages).toEqual(["sign"])
    } finally {
      importKeySpy.mockRestore()
    }
  })

  it("fails closed when no signing-key accessor has been registered", async () => {
    vi.resetModules()
    const mod = await import("../etagCache")
    try {
      const response = makeResponse(
        200,
        { etag: '"etag-no-accessor"', "content-type": "application/json" },
        { cold: true }
      )
      await expect(mod.handleEtagResponse(response, "cold:no-accessor")).resolves.toBeUndefined()
      expect(mod.etagCache.get("cold:no-accessor")).toBe('"etag-no-accessor"')
      expect(mod.responseCache.get("cold:no-accessor")).toBeUndefined()
    } finally {
      mod.clearCachesOnLogout()
    }
  })

  it("uses a dynamically registered signing accessor for a freshly loaded module", async () => {
    vi.resetModules()
    const mod = await import("../etagCache")
    mod.registerSigningKeyAccessor(() => SIGNING_KEY)

    try {
      const response = makeResponse(
        200,
        { etag: '"etag-dynamic-accessor"', "content-type": "application/json" },
        { dynamic: true }
      )

      await mod.handleEtagResponse(response, "dynamic:accessor")

      expect(mod.responseCache.get("dynamic:accessor")?.data).toEqual({ dynamic: true })
    } finally {
      mod.clearCachesOnLogout()
    }
  })

  it("treats the exact response-cache limit as bounded without sorting", () => {
    for (let index = 0; index < 200; index += 1) {
      responseCache.set(`response:boundary:${index}`, {
        data: index,
        hmac: "hmac",
        ts: index,
      })
    }

    const entriesSpy = vi.spyOn(Map.prototype, "entries")
    try {
      // Updating an existing key keeps the map exactly at its limit. The
      // eviction path must return before constructing a sorted snapshot.
      responseCache.set("response:boundary:0", { data: "updated", hmac: "hmac", ts: 999 })
      expect(entriesSpy).not.toHaveBeenCalled()
    } finally {
      entriesSpy.mockRestore()
    }
  })

  it("evicts by timestamp rather than insertion order when responses overflow", () => {
    for (let index = 0; index < 199; index += 1) {
      responseCache.set(`response:ordered:${index}`, {
        data: index,
        hmac: "hmac",
        ts: 1_000 + index,
      })
    }
    responseCache.set("response:ordered:oldest", { data: "old", hmac: "hmac", ts: 1 })

    responseCache.set("response:ordered:overflow", { data: "new", hmac: "hmac", ts: 2_000 })

    expect(responseCache.get("response:ordered:oldest")).toBeUndefined()
    expect(responseCache.get("response:ordered:0")).toBeDefined()
    expect(responseCache.get("response:ordered:overflow")).toBeDefined()
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

  it("does not cache JSON payloads for a non-200 response", async () => {
    const response = makeResponse(
      201,
      { etag: '"etag-created"', "content-type": "application/json" },
      { created: true }
    )

    await handleEtagResponse(response, "created:response")

    expect(etagCache.get("created:response")).toBe('"etag-created"')
    expect(responseCache.get("created:response")).toBeUndefined()
  })

  it("stores an ETag without caching when content type is absent", async () => {
    const response = makeResponse(200, { etag: '"etag-no-content-type"' }, { ok: true })

    await handleEtagResponse(response, "no-content-type")

    expect(etagCache.get("no-content-type")).toBe('"etag-no-content-type"')
    expect(responseCache.get("no-content-type")).toBeUndefined()
  })

  it("accepts AxiosHeaders case-insensitive matching for an upper-case ETag", async () => {
    const response = makeResponse(
      200,
      { ETag: '"etag-uppercase"', "content-type": "text/plain" },
      "plain text"
    )

    await handleEtagResponse(response, "uppercase:etag")

    expect(etagCache.get("uppercase:etag")).toBe('"etag-uppercase"')
  })

  it("rejects a whitespace-only ETag and clears stale caches", async () => {
    etagCache.set("whitespace:etag", '"old"')
    responseCache.set("whitespace:etag", { data: { old: true }, hmac: "hmac", ts: 1 })

    const response = makeResponse(
      200,
      { etag: "   ", "content-type": "application/json" },
      { fresh: true }
    )
    await handleEtagResponse(response, "whitespace:etag")

    expect(etagCache.get("whitespace:etag")).toBeUndefined()
    expect(responseCache.get("whitespace:etag")).toBeUndefined()
  })

  it("rejects Unicode whitespace ETags that Axios does not normalize", async () => {
    etagCache.set("unicode-whitespace:etag", '"old"')
    responseCache.set("unicode-whitespace:etag", { data: { old: true }, hmac: "hmac", ts: 1 })

    const response = makeResponse(
      200,
      { etag: "\u2003", "content-type": "application/json" },
      { fresh: true }
    )
    await handleEtagResponse(response, "unicode-whitespace:etag")

    expect(etagCache.get("unicode-whitespace:etag")).toBeUndefined()
    expect(responseCache.get("unicode-whitespace:etag")).toBeUndefined()
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

  it("deletes an existing response cache when the signing key disappears", async () => {
    const first = makeResponse(
      200,
      { etag: '"etag-key-present"', "content-type": "application/json" },
      { old: true }
    )
    await handleEtagResponse(first, "key:disappears")
    expect(responseCache.get("key:disappears")).toBeDefined()

    registerSigningKeyAccessor(() => null)
    const second = makeResponse(
      200,
      { etag: '"etag-key-missing"', "content-type": "application/json" },
      { fresh: true }
    )
    await handleEtagResponse(second, "key:disappears")

    expect(responseCache.get("key:disappears")).toBeUndefined()
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

  it("advances a fresh session epoch so an in-flight HMAC is discarded", async () => {
    vi.resetModules()
    const mod = await import("../etagCache")
    mod.registerSigningKeyAccessor(() => SIGNING_KEY)

    const realSign = crypto.subtle.sign.bind(crypto.subtle)
    const signSpy = vi
      .spyOn(crypto.subtle, "sign")
      .mockImplementation(async (...args: Parameters<typeof realSign>) => {
        mod.incrementSessionEpoch()
        return realSign(...args)
      })

    try {
      const response = makeResponse(
        200,
        { etag: '"fresh-epoch"', "content-type": "application/json" },
        { fresh: true }
      )
      await mod.handleEtagResponse(response, "fresh:epoch")
      expect(mod.responseCache.get("fresh:epoch")).toBeUndefined()
    } finally {
      signSpy.mockRestore()
      mod.clearCachesOnLogout()
    }
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

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    try {
      const notModified = makeResponse(304, { etag: '"etag-bad-hmac"' }, null)
      await handleEtagResponse(notModified, "bad:hmac")

      // Mismatch path: status stays 304, both caches evicted.
      expect(notModified.status).toBe(304)
      expect(notModified.data).toBeNull()
      expect(etagCache.get("bad:hmac")).toBeUndefined()
      expect(responseCache.get("bad:hmac")).toBeUndefined()
      expect(warnSpy).toHaveBeenCalledWith("[etagCache] HMAC mismatch for key:", "bad:hmac")
    } finally {
      warnSpy.mockRestore()
    }
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

  it("rejects an empty stored HMAC before attempting a constant-time comparison", async () => {
    const response = makeResponse(
      200,
      { etag: '"etag-empty-hmac"', "content-type": "application/json" },
      { v: 2 }
    )
    await handleEtagResponse(response, "empty:hmac")
    const cached = responseCache.get("empty:hmac")!
    responseCache.set("empty:hmac", { ...cached, hmac: "" })

    const notModified = makeResponse(304, { etag: '"etag-empty-hmac"' }, null)
    await handleEtagResponse(notModified, "empty:hmac")

    expect(notModified.status).toBe(304)
    expect(responseCache.get("empty:hmac")).toBeUndefined()
    expect(etagCache.get("empty:hmac")).toBeUndefined()
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
    expect(calls.some(([, value]) => value.includes("vis:k"))).toBe(true)
  })

  it("does not flush on a visibilitychange while the document remains visible", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    try {
      etagCache.set("vis:visible", '"tag"')
      setItemSpy.mockClear()
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "visible",
      })
      document.dispatchEvent(new Event("visibilitychange"))

      expect(setItemSpy).not.toHaveBeenCalled()
    } finally {
      setItemSpy.mockRestore()
    }
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

    // The static module performs two writes: the failing one + the retry after
    // eviction. Fresh module imports in isolated suites also own listeners,
    // so unrelated empty snapshots may be present in the shared spy.
    const cacheWrites = setItemSpy.mock.calls.filter(([k]) => k.startsWith("ue:etag-cache"))
    expect(cacheWrites.length).toBeGreaterThanOrEqual(2)
    expect(cacheWrites.some(([, value]) => value.includes("q:oldest"))).toBe(true)

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
    expect(cacheWrites.length).toBeGreaterThanOrEqual(2)
    expect(cacheWrites.filter(([, value]) => value.includes("q:retry-fails"))).toHaveLength(1)
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

  it("does not treat a plain error named QuotaExceededError as a browser quota error", () => {
    const namedError = Object.assign(new Error("storage unavailable"), {
      name: "QuotaExceededError",
    })
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw namedError
    })
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    try {
      etagCache.set("q:plain-error", '"tag"')
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "hidden",
      })
      document.dispatchEvent(new Event("visibilitychange"))

      expect(etagCache.get("q:plain-error")).toBe('"tag"')
      expect(setItemSpy).toHaveBeenCalled()
      expect(warnSpy).toHaveBeenCalledWith("Failed to flush etag cache to localStorage", namedError)
    } finally {
      warnSpy.mockRestore()
      setItemSpy.mockRestore()
    }
  })

  it("does not evict entries for a DOMException with a non-quota name", () => {
    const securityError = new DOMException("storage blocked", "SecurityError")
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw securityError
    })
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    try {
      etagCache.set("q:security-error", '"tag"')
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "hidden",
      })
      document.dispatchEvent(new Event("visibilitychange"))

      expect(etagCache.get("q:security-error")).toBe('"tag"')
      expect(setItemSpy).toHaveBeenCalled()
      expect(warnSpy).toHaveBeenCalledWith(
        "Failed to flush etag cache to localStorage",
        securityError
      )
    } finally {
      warnSpy.mockRestore()
      setItemSpy.mockRestore()
    }
  })

  it("evicts by last-used timestamp rather than insertion order after quota recovery", () => {
    const nowSpy = vi.spyOn(Date, "now")
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
      realSetItem.call(this, key, value)
    })
    try {
      nowSpy.mockReturnValue(3_000)
      etagCache.set("q:timestamp:newest", '"new"')
      nowSpy.mockReturnValue(1_000)
      etagCache.set("q:timestamp:oldest", '"old"')
      nowSpy.mockReturnValue(2_000)
      etagCache.set("q:timestamp:middle", '"mid"')

      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "hidden",
      })
      document.dispatchEvent(new Event("visibilitychange"))

      expect(etagCache.get("q:timestamp:oldest")).toBeUndefined()
      expect(etagCache.get("q:timestamp:newest")).toBe('"new"')
      expect(etagCache.get("q:timestamp:middle")).toBeUndefined()
      const cacheWrites = setItemSpy.mock.calls.filter(([key]) => key.startsWith("ue:etag-cache"))
      expect(cacheWrites.length).toBeGreaterThanOrEqual(2)
      expect(cacheWrites.some(([, value]) => value.includes("q:timestamp:oldest"))).toBe(true)
    } finally {
      nowSpy.mockRestore()
      setItemSpy.mockRestore()
    }
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
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)

    try {
      const mod = await import("../etagCache")
      // Corrupt payload → hydration fails gracefully to an empty map, no throw.
      expect(() => mod.etagCache.get("anything")).not.toThrow()
      expect(mod.etagCache.get("anything")).toBeUndefined()
      expect(warnSpy).toHaveBeenCalledWith("Failed to hydrate etag cache", expect.any(Error))
    } finally {
      warnSpy.mockRestore()
    }
  })

  it("does not parse an empty storage payload or emit a hydration warning", async () => {
    localStorage.setItem(KEY, "")
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)

    try {
      const mod = await import("../etagCache")
      expect(mod.etagCache.get("empty-payload")).toBeUndefined()
      expect(warnSpy).not.toHaveBeenCalledWith("Failed to hydrate etag cache", expect.anything())
    } finally {
      warnSpy.mockRestore()
    }
  })

  it("removes stale unversioned and prior-version keys during module startup", async () => {
    localStorage.setItem("ue:etag-cache", "stale")
    localStorage.setItem("ue:etag-cache:v0", "old-version")

    await import("../etagCache")

    expect(localStorage.getItem("ue:etag-cache")).toBeNull()
    expect(localStorage.getItem("ue:etag-cache:v0")).toBeNull()
  })

  it("removes every stale cache key from one startup snapshot", async () => {
    const staleKeys = Array.from({ length: 9 }, (_, index) => `ue:etag-cache:v${index + 2}`)
    for (const key of staleKeys) {
      localStorage.setItem(key, "stale")
    }
    localStorage.setItem(KEY, "current")
    localStorage.setItem("unrelated:key", "keep")

    await import("../etagCache")

    expect(staleKeys.every((key) => localStorage.getItem(key) === null)).toBe(true)
    expect(localStorage.getItem(KEY)).toBe("current")
    expect(localStorage.getItem("unrelated:key")).toBe("keep")
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

  it("ignores null storage keys while still removing stale keys", async () => {
    localStorage.setItem("unrelated:first", "keep")
    localStorage.setItem("ue:etag-cache:v0", "stale")
    const realKey = Storage.prototype.key
    let firstKey = true
    const keySpy = vi.spyOn(Storage.prototype, "key").mockImplementation(function (
      this: Storage,
      index: number
    ) {
      if (firstKey) {
        firstKey = false
        return null
      }
      return realKey.call(this, index)
    })

    try {
      await import("../etagCache")
      expect(localStorage.getItem("ue:etag-cache:v0")).toBeNull()
    } finally {
      keySpy.mockRestore()
    }
  })

  it("skips browser-only hydration, cleanup, and timers during SSR", async () => {
    vi.useFakeTimers()
    const originalWindow = globalThis.window
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem")
    const keySpy = vi.spyOn(Storage.prototype, "key")
    try {
      vi.stubGlobal("window", undefined)
      const mod = await import("../etagCache")
      expect(mod.etagCache.get("ssr:key")).toBeUndefined()
      mod.etagCache.set("ssr:key", '"tag"')
      expect(vi.getTimerCount()).toBe(0)
      expect(getItemSpy).not.toHaveBeenCalled()
      expect(keySpy).not.toHaveBeenCalled()

      const removeSpy = vi.spyOn(Storage.prototype, "removeItem")
      mod.etagCache.clear()
      expect(removeSpy).not.toHaveBeenCalled()
      removeSpy.mockRestore()
    } finally {
      vi.stubGlobal("window", originalWindow)
      getItemSpy.mockRestore()
      keySpy.mockRestore()
      vi.useRealTimers()
    }
  })

  it("loads without a visibility listener when document is unavailable during SSR startup", async () => {
    const originalDocument = globalThis.document
    try {
      vi.stubGlobal("document", undefined)
      vi.resetModules()

      await expect(import("../etagCache")).resolves.toBeDefined()
    } finally {
      vi.stubGlobal("document", originalDocument)
    }
  })

  it("skips stale-key cleanup when window is unavailable during SSR startup", async () => {
    const staleKey = "ue:etag-cache:v0"
    localStorage.setItem(staleKey, "stale")
    const keySpy = vi.spyOn(Storage.prototype, "key")
    const originalWindow = globalThis.window

    try {
      vi.stubGlobal("window", undefined)
      vi.resetModules()

      await expect(import("../etagCache")).resolves.toBeDefined()
      expect(keySpy).not.toHaveBeenCalled()
      expect(localStorage.getItem(staleKey)).toBe("stale")
    } finally {
      keySpy.mockRestore()
      vi.stubGlobal("window", originalWindow)
      localStorage.removeItem(staleKey)
    }
  })

  it("registers a passive visibility listener once at browser module load", async () => {
    const addSpy = vi.spyOn(document, "addEventListener")
    try {
      const mod = await import("../etagCache")
      expect(mod).toBeDefined()
      const visibilityCalls = addSpy.mock.calls.filter(([type]) => type === "visibilitychange")
      expect(visibilityCalls).toHaveLength(1)
      expect(visibilityCalls[0]?.[2]).toEqual({ passive: true })
      expect(typeof visibilityCalls[0]?.[1]).toBe("function")
    } finally {
      addSpy.mockRestore()
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
