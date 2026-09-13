import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { http, HttpResponse } from "msw"

import { server } from "@/tests/mocks/server"
import { testUser } from "@/tests/mocks/handlers"

type E2eWindow = Window & { __E2E_NETWORK_API_MOCKS__?: boolean }

const adapterFor = (api: { defaults: { adapter?: unknown } }) =>
  api.defaults.adapter as (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>

describe("API client mutation follow-up contracts", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv("VITE_LHCI", "true")
    vi.stubEnv("DEV", false)
    ;(window as E2eWindow).__E2E_NETWORK_API_MOCKS__ = true
  })

  afterEach(() => {
    const currentWindow = globalThis.window as E2eWindow | undefined
    if (currentWindow) delete currentWindow.__E2E_NETWORK_API_MOCKS__
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it("keeps the SSR production prefix instead of dropping the API path", async () => {
    vi.stubGlobal("window", undefined)
    vi.stubEnv("BACKEND_ORIGIN", "http://backend.internal:8000")

    const { default: api } = await import("@/api/client")

    expect(api.defaults.baseURL).toBe("http://backend.internal:8000/api/v1")
  })

  it("uses the network adapter for the exact users allowlist path when baseURL is absent", async () => {
    server.use(http.get("*/api/v1/users", () => HttpResponse.json([testUser])))
    const { default: api } = await import("@/api/client")
    const adapter = adapterFor(api)

    const response = await adapter({
      method: "get",
      url: "/api/v1/users",
      baseURL: undefined,
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig)

    expect(JSON.parse(response.data as string)).toEqual([testUser])
  })

  it("keeps the LHCI safe fallback when network mocks are disabled even for allowlisted paths", async () => {
    server.use(http.get("*/api/v1/users", () => HttpResponse.json([testUser])))
    const { default: api } = await import("@/api/client")
    ;(window as E2eWindow).__E2E_NETWORK_API_MOCKS__ = false
    const adapter = adapterFor(api)

    const response = await adapter({
      method: "get",
      url: "/api/v1/users",
      baseURL: undefined,
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig)

    expect(response.status).toBe(200)
    expect(response.data).toEqual({ items: [] })
  })
})
