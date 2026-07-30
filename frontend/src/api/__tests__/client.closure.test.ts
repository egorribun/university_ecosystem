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
