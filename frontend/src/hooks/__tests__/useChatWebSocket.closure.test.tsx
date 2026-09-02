import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import type { Message, MessagesListResponse } from "@/api/chat"
import { appendLiveMessageToCache, useChatWebSocket, WebSocketProvider } from "../useChatWebSocket"

vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: vi.fn().mockResolvedValue({
    messages: { upsert: vi.fn().mockResolvedValue(undefined) },
  }),
}))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))

class RecordingWebSocket {
  static readonly OPEN = 1
  static readonly CONNECTING = 0
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: RecordingWebSocket[] = []

  readyState = RecordingWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(public readonly url: string) {
    RecordingWebSocket.instances.push(this)
  }

  send() {}
  close() {
    this.readyState = RecordingWebSocket.CLOSED
  }
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
}

function message(index: number, createdAt: string): Message {
  return {
    id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    chat_id: "11111111-1111-4111-8111-111111111111",
    sender_id: "22222222-2222-4222-8222-222222222222",
    content: String(index),
    created_at: createdAt,
    read_status: false,
    read_at: null,
    attachments: [],
    reactions: [],
  }
}

beforeEach(() => {
  RecordingWebSocket.instances = []
  vi.stubGlobal("WebSocket", RecordingWebSocket)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("useChatWebSocket ticket and cursor closure", () => {
  it("creates an exact recovery cursor for timestamps without fractional seconds", () => {
    const createdAt = "2026-08-26T10:00:00Z"
    const cached: MessagesListResponse = {
      items: Array.from({ length: 200 }, (_, index) => message(index, createdAt)),
      has_more: false,
      next_cursor: null,
    }

    const result = appendLiveMessageToCache(cached, message(200, createdAt))
    const oldest = result.items[0]!

    expect(result.items).toHaveLength(200)
    expect(result.next_cursor).toBe(`${BigInt(Date.parse(createdAt)) * 1000n}:${oldest.id}`)
  })

  it("does not retry a ticket request aborted by its deadline", async () => {
    vi.useFakeTimers()
    vi.spyOn(api, "post").mockImplementation(((_url, _data, config) => {
      return new Promise((_resolve, reject) => {
        config?.signal?.addEventListener?.("abort", () => reject(new DOMException("aborted")))
      })
    }) as typeof api.post)

    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await act(async () => vi.advanceTimersByTimeAsync(5_000))

    expect(api.post).toHaveBeenCalledOnce()
    expect(RecordingWebSocket.instances).toHaveLength(0)
    rendered.unmount()
  })

  it("ignores a ticket failure delivered after provider cleanup", async () => {
    let rejectTicket: ((error: Error) => void) | undefined
    vi.spyOn(api, "post").mockImplementation((() => {
      return new Promise((_resolve, reject) => {
        rejectTicket = reject
      })
    }) as typeof api.post)
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(api.post).toHaveBeenCalledOnce())

    rendered.unmount()
    await act(async () => rejectTicket?.(new Error("late ticket failure")))

    expect(RecordingWebSocket.instances).toHaveLength(0)
  })

  it("does not schedule a transient ticket retry after the browser goes offline", async () => {
    vi.useFakeTimers()
    let rejectTicket: ((error: Error) => void) | undefined
    vi.spyOn(api, "post").mockImplementation((() => {
      return new Promise((_resolve, reject) => {
        rejectTicket = reject
      })
    }) as typeof api.post)
    vi.stubGlobal("navigator", { ...navigator, onLine: true })
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await act(async () => Promise.resolve())
    expect(api.post).toHaveBeenCalledOnce()

    vi.stubGlobal("navigator", { ...navigator, onLine: false })
    await act(async () => rejectTicket?.(new Error("offline during exchange")))
    await act(async () => vi.runAllTimersAsync())

    expect(api.post).toHaveBeenCalledOnce()
    expect(RecordingWebSocket.instances).toHaveLength(0)
    rendered.unmount()
  })

  it("stops transient ticket retries at the bounded attempt limit", async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, "random").mockReturnValue(0)
    vi.spyOn(api, "post").mockRejectedValue(new Error("ticket service unavailable"))
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })

    await act(async () => vi.runAllTimersAsync())

    expect(api.post).toHaveBeenCalledTimes(11)
    expect(RecordingWebSocket.instances).toHaveLength(0)
    rendered.unmount()
  })
})
