import { describe, expect, it } from "vitest"
import type { AxiosRequestConfig } from "axios"

import { API_UNAUTHORIZED_EVENT, resolveRequestPath } from "@/api/client"

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
})
