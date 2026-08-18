import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { http, HttpResponse } from "msw"

import { server } from "@/tests/mocks/server"

type DedupeMessage = { key: string; action: "add" | "delete" }
type DedupeListener = (event: MessageEvent<DedupeMessage>) => void

class RecordingBroadcastChannel {
  static instances: RecordingBroadcastChannel[] = []
  readonly messages: unknown[] = []
  listener: DedupeListener | undefined

  constructor(readonly name: string) {
    RecordingBroadcastChannel.instances.push(this)
  }

  addEventListener(_type: string, listener: DedupeListener) {
    this.listener = listener
  }

  postMessage(message: unknown) {
    this.messages.push(message)
  }

  close() {}
}

const make429 = (
  config: InternalAxiosRequestConfig,
  error: Error | DOMException,
  headers: Record<string, string> = {}
) =>
  Object.assign(error, {
    config,
    response: {
      status: 429,
      statusText: "Too Many Requests",
      headers: AxiosHeaders.from(headers),
      data: { detail: "slow down" },
      config,
    },
  })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

describe("api/client — LHCI safe adapter", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv("VITE_LHCI", "true")
  })

  it("returns the safe fallback outside the explicitly mocked E2E routes", async () => {
    const { default: lhciApi } = await import("@/api/client")

    ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = false
    const response = await lhciApi.get("/news")

    expect(response.status).toBe(200)
    expect(response.data).toEqual({ items: [] })
  })

  it("delegates explicitly mocked chat routes to the real adapter", async () => {
    server.use(
      http.get("*/chats", () =>
        HttpResponse.json({
          items: [
            {
              id: "chat-1",
              participants: [],
              created_at: "2026-07-30T00:00:00Z",
              updated_at: "2026-07-30T00:00:00Z",
            },
          ],
        })
      )
    )
    const { default: lhciApi } = await import("@/api/client")

    ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = true
    const response = await lhciApi.get("/api/v1/chats")

    expect(response.data.items[0]).toMatchObject({ id: "chat-1", participants: [] })
  })

  it("resolves both relative and absolute paths before applying the safe fallback", async () => {
    const { default: lhciApi } = await import("@/api/client")

    ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = true

    await expect(lhciApi.get("/other")).resolves.toMatchObject({
      status: 200,
      data: { items: [] },
    })
    await expect(lhciApi.get("https://example.test/other")).resolves.toMatchObject({
      status: 200,
      data: { items: [] },
    })
  })

  it("handles an adapter config without url or baseURL", async () => {
    const { default: lhciApi } = await import("@/api/client")

    ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = true
    const adapter = lhciApi.defaults.adapter as (
      config: InternalAxiosRequestConfig
    ) => Promise<AxiosResponse>
    expect(adapter).toBeTypeOf("function")

    const response = await adapter({
      method: "get",
      headers: new AxiosHeaders(),
      url: undefined,
      baseURL: undefined,
    } as InternalAxiosRequestConfig)

    expect(response.status).toBe(200)
    expect(response.data).toEqual({ items: [] })
  })

  it("tolerates a request without url or method and skips the CSRF endpoint guard", async () => {
    const { default: lhciApi } = await import("@/api/client")

    await expect(lhciApi.request({ skipRateLimitQueue: true } as never)).resolves.toMatchObject({
      status: 200,
      data: { items: [] },
    })
    await expect(lhciApi.post("/auth/csrf-cookie", {})).resolves.toMatchObject({ status: 200 })
  })

  it("short-circuits the LHCI E2E matcher during SSR", async () => {
    vi.stubGlobal("window", undefined)
    const { default: lhciApi } = await import("@/api/client")

    await expect(lhciApi.get("/news")).resolves.toMatchObject({
      status: 200,
      data: { items: [] },
    })
  })
})

describe("api/client — production browser configuration", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv("DEV", false)
  })

  it("uses the gateway API prefix outside development", async () => {
    const { default: productionApi } = await import("@/api/client")

    expect(productionApi.defaults.baseURL).toBe("/api/v1")
  })

  it("silently revokes a non-allowlisted queue bypass outside development", async () => {
    const { default: productionApi } = await import("@/api/client")
    const requestHandler = (productionApi.interceptors.request as any).handlers.find(
      (handler: { fulfilled?: unknown }) => typeof handler.fulfilled === "function"
    )?.fulfilled as (config: InternalAxiosRequestConfig) => Promise<InternalAxiosRequestConfig>
    const config = {
      method: "get",
      url: "/news",
      headers: new AxiosHeaders(),
      skipRateLimitQueue: true,
    } as InternalAxiosRequestConfig & { skipRateLimitQueue: boolean }

    await requestHandler(config)

    expect(config.skipRateLimitQueue).toBe(false)
  })
})

describe("api/client — BroadcastChannel idempotency coordination", () => {
  beforeEach(() => {
    RecordingBroadcastChannel.instances = []
    vi.resetModules()
    vi.stubGlobal("BroadcastChannel", RecordingBroadcastChannel)
  })

  it("honors add/delete messages received from another tab", async () => {
    const { default: channelApi } = await import("@/api/client")
    const channel = RecordingBroadcastChannel.instances[0]
    expect(channel?.name).toBe("ecosystem.idempotency.dedup")

    channel?.listener?.({
      data: { key: "remote-key", action: "add" },
    } as MessageEvent<DedupeMessage>)

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    channelApi.defaults.adapter = adapter

    await expect(
      channelApi.post("/events", { ok: true }, { headers: { "Idempotency-Key": "remote-key" } })
    ).rejects.toMatchObject({ message: expect.stringContaining("Duplicate") })

    channel?.listener?.({
      data: { key: "remote-key", action: "delete" },
    } as MessageEvent<DedupeMessage>)
    await channelApi.post("/events", { ok: true }, { headers: { "Idempotency-Key": "remote-key" } })

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(channel?.messages).toEqual([
      { key: "remote-key", action: "add" },
      { key: "remote-key", action: "delete" },
    ])
  })

  it("continues without cross-tab coordination when BroadcastChannel construction fails", async () => {
    class ThrowingBroadcastChannel {
      constructor() {
        throw new Error("BroadcastChannel unavailable")
      }
    }
    vi.stubGlobal("BroadcastChannel", ThrowingBroadcastChannel)
    const { default: safeApi } = await import("@/api/client")

    safeApi.defaults.adapter = async (config): Promise<AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    })

    await expect(safeApi.get("/news")).resolves.toMatchObject({ status: 200 })
  })

  it("continues without cross-tab coordination when BroadcastChannel is absent", async () => {
    vi.stubGlobal("BroadcastChannel", undefined)
    const { default: safeApi } = await import("@/api/client")

    safeApi.defaults.adapter = async (config): Promise<AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    })

    await expect(safeApi.get("/news")).resolves.toMatchObject({ status: 200 })
  })
})

describe("api/client — abort-aware 429 handling", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "100")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
  })

  it("does not retry a DOM AbortError returned with a 429 response", async () => {
    const { default: abortApi } = await import("@/api/client")
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      throw make429(config, new DOMException("cancelled", "AbortError"), {
        "Retry-After": "not-a-number",
      })
    })
    abortApi.defaults.adapter = adapter

    const result = await abortApi.get("/news").catch((error: unknown) => error)

    expect(result).toBeInstanceOf(DOMException)
    expect((result as DOMException).name).toBe("AbortError")
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it("does not retry a canceled axios-style error returned with a 429 response", async () => {
    const { default: abortApi } = await import("@/api/client")
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      throw make429(config, Object.assign(new Error("cancelled"), { name: "CanceledError" }), {
        "retry-after": "-1",
      })
    })
    abortApi.defaults.adapter = adapter

    const result = await abortApi.get("/news").catch((error: unknown) => error)

    expect(result).toMatchObject({ response: { status: 429 } })
    expect(adapter).toHaveBeenCalledTimes(1)
  })
})

describe("api/client — SSR request branches", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal("window", undefined)
    vi.stubGlobal(
      "__ssrCookieGetter__",
      vi.fn(() => "access_token_v2=server-token")
    )
    vi.stubEnv("VITE_BACKEND_ORIGIN", "")
    vi.stubEnv("BACKEND_ORIGIN", "")
  })

  it("forwards the incoming cookie and uses the SSR fallback base configuration", async () => {
    const { default: ssrApi, ensureCsrfCookie } = await import("@/api/client")
    const seen: InternalAxiosRequestConfig[] = []
    ssrApi.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push(config)
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    await ssrApi.get("/news")
    await ensureCsrfCookie()

    expect(AxiosHeaders.from(seen[0]!.headers).get("Cookie")).toBe("access_token_v2=server-token")
    const { resolveSsrBackendOrigin } = await import("@/api/backendOrigin")
    expect(resolveSsrBackendOrigin()).toBe("http://localhost:8000")
  })

  it("prefers the runtime backend origin in the Node SSR container", async () => {
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://build-time.example")
    vi.stubEnv("BACKEND_ORIGIN", "http://release-backend:8000/")

    const { resolveSsrBackendOrigin } = await import("@/api/backendOrigin")

    expect(resolveSsrBackendOrigin()).toBe("http://release-backend:8000")
  })

  it("does not add an empty SSR cookie header", async () => {
    const cookieGetter = vi.fn(() => "")
    vi.stubGlobal("__ssrCookieGetter__", cookieGetter)
    const { default: ssrApi } = await import("@/api/client")
    const seen: InternalAxiosRequestConfig[] = []
    ssrApi.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push(config)
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    await ssrApi.get("/news")

    expect(cookieGetter).toHaveBeenCalledOnce()
    expect(AxiosHeaders.from(seen[0]!.headers).get("Cookie")).toBeUndefined()
  })
})

describe("api/client — defensive request/response interceptor inputs", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "100")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
  })

  it("normalizes an unsafe request with missing URL, headers, and FormData content", async () => {
    const { default: client } = await import("@/api/client")
    const requestHandler = (client.interceptors.request as any).handlers.find(
      (handler: { fulfilled?: unknown }) => typeof handler.fulfilled === "function"
    )?.fulfilled as (config: InternalAxiosRequestConfig) => Promise<InternalAxiosRequestConfig>

    const config = {
      method: "post",
      url: undefined,
      headers: undefined,
      data: new FormData(),
    } as unknown as InternalAxiosRequestConfig & { __clientRateLimitAcquired?: boolean }

    const normalized = await requestHandler(config)
    const headers = AxiosHeaders.from(normalized.headers)
    expect(headers.get("Accept-Language")).toBeDefined()
    expect(headers.has("Content-Type")).toBe(false)

    const { releaseClientQueueSlot } = await import("@/api/interceptors/rateLimit")
    releaseClientQueueSlot(config as Parameters<typeof releaseClientQueueSlot>[0])
  })

  it("rejects a 401 response even when its request has no headers object", async () => {
    const { default: client } = await import("@/api/client")
    const responseHandler = (client.interceptors.response as any).handlers.find(
      (handler: { rejected?: unknown }) => typeof handler.rejected === "function"
    )?.rejected as (error: unknown) => Promise<unknown>
    const error = { response: { status: 401 }, config: { headers: undefined } }

    await expect(responseHandler(error)).rejects.toBe(error)
  })

  it("uses the default backoff for a direct 429 response without headers", async () => {
    const { default: client } = await import("@/api/client")
    const { RATE_LIMIT_MAX_RETRY } = await import("@/api/interceptors/rateLimit")
    const responseHandler = (client.interceptors.response as any).handlers.find(
      (handler: { rejected?: unknown }) => typeof handler.rejected === "function"
    )?.rejected as (error: unknown) => Promise<unknown>
    const error = {
      response: { status: 429, headers: undefined },
      config: {
        headers: new AxiosHeaders(),
        __rateLimitRetryCount: RATE_LIMIT_MAX_RETRY,
      },
    }

    await expect(responseHandler(error)).rejects.toBe(error)
  })
})
