import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"

import { etagCache, registerSigningKeyAccessor, responseCache } from "@/api/interceptors/etagCache"
import { testEvents } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"

describe("API ETag interceptor", () => {
  beforeEach(async () => {
    const { resetEtagCache } = await import("@/api/client")
    resetEtagCache()
    const signingKey = crypto.randomUUID()
    registerSigningKeyAccessor(() => signingKey)
  })

  afterEach(async () => {
    const { resetEtagCache } = await import("@/api/client")
    resetEtagCache()
    registerSigningKeyAccessor(() => null)
  })

  it("reuses cached ETags for subsequent requests when an etagCacheKey is provided", async () => {
    const { default: api, resetEtagCache } = await import("@/api/client")
    resetEtagCache()
    registerSigningKeyAccessor(() => "test-signing-key-1234567890abcdef")

    const observedIfNoneMatch: Array<string | null> = []
    let requestCount = 0

    server.use(
      http.get("*/events", ({ request }) => {
        requestCount += 1
        observedIfNoneMatch.push(request.headers.get("if-none-match"))

        if (requestCount === 1) {
          return HttpResponse.json(
            {
              items: [],
              total: 0,
              limit: 12,
              cursor: null,
              next_cursor: null,
              has_more: false,
            },
            { headers: { ETag: '"etag-123"' } }
          )
        }

        if (request.headers.get("if-none-match") === '"etag-123"') {
          return new HttpResponse(null, { status: 304, headers: { ETag: '"etag-123"' } })
        }

        return HttpResponse.json({
          items: [],
          total: 0,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      })
    )

    const config = {
      etagCacheKey: "events:test",
      validateStatus: (status: number) => status >= 200 && status < 400,
    } as const

    const firstResponse = await api.get("/events", config)
    expect(firstResponse.status).toBe(200)

    const secondResponse = await api.get("/events", config)
    expect(secondResponse.status).toBe(200)
    expect(secondResponse.data).toEqual(firstResponse.data)

    expect(observedIfNoneMatch).toEqual([null, '"etag-123"'])
  })

  it("recovers a full body before revalidating a surviving ETag", async () => {
    const { default: api } = await import("@/api/client")
    const tag = '"bodyless-etag"'
    const key = "events:bodyless"
    etagCache.set(key, tag)
    expect(responseCache.get(key)).toBeUndefined()
    const page = {
      items: testEvents.slice(0, 1),
      total: 1,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    }
    const conditions: Array<string | null> = []
    server.use(
      http.get("*/events", ({ request }) => {
        const condition = request.headers.get("if-none-match")
        conditions.push(condition)
        return condition === tag
          ? new HttpResponse(null, { status: 304, headers: { ETag: tag } })
          : HttpResponse.json(page, { headers: { ETag: tag } })
      })
    )
    const config = {
      etagCacheKey: key,
      validateStatus: (status: number) => status === 304 || (status >= 200 && status < 300),
    }

    const recovered = await api.get("/events", config)
    expect(recovered.status).toBe(200)
    expect(recovered.data).toEqual(page)
    expect(recovered.data.items).toHaveLength(1)
    expect(conditions).toEqual([null])

    const revalidated = await api.get("/events", config)
    expect(revalidated.status).toBe(200)
    expect(revalidated.data).toEqual(page)
    expect(conditions).toEqual([null, tag])
  })

  it("preserves an explicit caller condition when no response body is cached", async () => {
    const { default: api } = await import("@/api/client")
    etagCache.set("events:caller", '"automatic-tag"')
    const conditions: Array<string | null> = []
    server.use(
      http.get("*/events", ({ request }) => {
        conditions.push(request.headers.get("if-none-match"))
        return HttpResponse.json({
          items: [],
          total: 0,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      })
    )
    const config = {
      etagCacheKey: "events:caller",
      headers: { "If-None-Match": '"caller-condition"' },
    }

    const response = await api.get("/events", config)
    expect(response.status).toBe(200)
    expect(conditions).toEqual(['"caller-condition"'])
  })

  it("does not turn an aborted bodyless-cache request into network recovery", async () => {
    const { default: api, isAbortError } = await import("@/api/client")
    etagCache.set("events:aborted", '"orphaned-tag"')
    const requests: string[] = []
    server.use(
      http.get("*/events", ({ request }) => {
        requests.push(request.url)
        return HttpResponse.json({
          items: [],
          total: 0,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      })
    )
    const controller = new AbortController()
    controller.abort()
    const config = { etagCacheKey: "events:aborted", signal: controller.signal }

    await expect(api.get("/events", config)).rejects.toSatisfy(isAbortError)
    expect(requests).toEqual([])
    expect(responseCache.get("events:aborted")).toBeUndefined()
  })
})
