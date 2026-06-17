import { afterEach, beforeEach, describe, expect, it } from "vitest"
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
})
