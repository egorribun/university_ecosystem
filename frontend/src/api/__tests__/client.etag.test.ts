import { beforeEach, describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"

import api, { resetEtagCache } from "@/api/client"
import { registerSigningKeyAccessor } from "@/api/interceptors/etagCache"
import { server } from "@/tests/mocks/server"

describe("API ETag interceptor", () => {
  beforeEach(() => {
    resetEtagCache()
    registerSigningKeyAccessor(() => "test-signing-key-1234567890abcdef")
  })

  it("reuses cached ETags for subsequent requests when an etagCacheKey is provided", async () => {
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
})
