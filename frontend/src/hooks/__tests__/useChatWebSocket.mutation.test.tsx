import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logError: vi.fn(),
  upsert: vi.fn(),
}))

vi.mock("@/api/client", () => ({ default: { post: mocks.apiPost } }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: vi.fn(async () => ({ messages: { upsert: mocks.upsert } })),
}))

import { useChatWebSocket, WebSocketProvider } from "../useChatWebSocket"

class MutationWebSocket {
  static readonly OPEN = 1
  static readonly CONNECTING = 0
  static readonly CLOSED = 3
  static instances: MutationWebSocket[] = []

  readyState = MutationWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(public readonly url: string) {
    MutationWebSocket.instances.push(this)
  }

  send() {}

  close() {
    this.readyState = MutationWebSocket.CLOSED
  }
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  MutationWebSocket.instances = []
  mocks.apiPost.mockResolvedValue({ data: { ticket: "mutation-ticket", expires_in: 15 } })
  mocks.logError.mockReset()
  mocks.upsert.mockReset()
  vi.stubGlobal("WebSocket", MutationWebSocket)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("useChatWebSocket mutation contracts", () => {
  it("uses the enabled=true default and obtains a ticket when no option is supplied", async () => {
    const rendered = renderHook(() => useChatWebSocket({}), { wrapper })

    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledOnce())
    await waitFor(() => expect(MutationWebSocket.instances).toHaveLength(1))
    expect(MutationWebSocket.instances[0]?.url).toContain("mutation-ticket")

    rendered.unmount()
  })

  it("does not log or schedule a retry when a ticket fails after the browser goes offline", async () => {
    let rejectTicket!: (error: Error) => void
    mocks.apiPost.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectTicket = reject
        })
    )
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })

    try {
      await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledOnce())
      online.mockReturnValue(false)
      await act(async () => {
        rejectTicket(new Error("ticket service unavailable while offline"))
        await Promise.resolve()
      })

      expect(mocks.logError).not.toHaveBeenCalled()
      expect(mocks.apiPost).toHaveBeenCalledOnce()
    } finally {
      rendered.unmount()
    }
  })

  it("handles a ticket promise that settles after disconnect cleared its request ref", async () => {
    let resolveTicket!: (value: { data: { ticket: string; expires_in: number } }) => void
    mocks.apiPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTicket = resolve
        })
    )
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledOnce())

    rendered.unmount()
    await act(async () => {
      resolveTicket({ data: { ticket: "late-ticket", expires_in: 15 } })
      await Promise.resolve()
    })

    expect(MutationWebSocket.instances).toHaveLength(0)
    expect(mocks.logError).not.toHaveBeenCalled()
  })
})
