import { describe, expect, it } from "vitest"
import type { AxiosRequestConfig } from "axios"

import { API_UNAUTHORIZED_EVENT, resetEtagCache, resolveRequestPath } from "@/api/client"
import { etagCache, responseCache } from "@/api/interceptors/etagCache"

const requestPath = (config: AxiosRequestConfig) => resolveRequestPath(config)

describe("api/client survivor contracts", () => {
  it("keeps the canonical unauthorized event name", () => {
    expect(API_UNAUTHORIZED_EVENT).toBe("auth:unauthorized")
  })

  it("resolves an omitted URL from the configured base URL", () => {
    expect(
      requestPath({
        baseURL: "/api/v1/users",
        url: undefined,
      })
    ).toBe("/api/v1/users/")
  })

  it("strips every leading slash while preserving interior path separators", () => {
    expect(
      requestPath({
        baseURL: "/gateway",
        url: "///api/v1/users",
      })
    ).toBe("/gateway/api/v1/users")

    expect(
      requestPath({
        baseURL: "/gateway",
        url: "api/v1//users",
      })
    ).toBe("/gateway/api/v1//users")
  })

  it("clears signed response payloads together with ETag metadata", () => {
    const key = "survivor:reset-etag-cache"
    etagCache.set(key, '"stale-etag"')
    responseCache.set(key, { data: { private: true }, hmac: "digest", ts: Date.now() })

    resetEtagCache()

    expect(etagCache.get(key)).toBeUndefined()
    expect(responseCache.get(key)).toBeUndefined()
  })
})
