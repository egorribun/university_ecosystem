import { renderHook, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"

import { useChatWebSocket, WebSocketProvider } from "@/hooks/useChatWebSocket"

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static CLOSING = 2
  static CLOSED = 3
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  sentMessages: string[] = []

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sentMessages.push(data)
  }

  close(code?: number) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code } as CloseEvent)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  receive(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }
}

describe("useChatWebSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("emits presence updates with last seen information", () => {
    const presenceSpy = vi.fn()
    const onlineSpy = vi.fn()
    const queryClient = new QueryClient()

    const { unmount } = renderHook(
      () =>
        useChatWebSocket({
          enabled: true,
          onPresenceUpdate: presenceSpy,
          onOnlineStatus: onlineSpy,
        }),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={queryClient}>
            <WebSocketProvider>{children}</WebSocketProvider>
          </QueryClientProvider>
        ),
      }
    )

    const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    expect(socket).toBeDefined()

    act(() => {
      socket.open()
    })

    act(() => {
      socket.receive({
        type: "presence",
        user_id: "550e8400-e29b-41d4-a716-446655440000",
        active: true,
        last_seen: "2024-02-01T10:00:00Z",
      })
    })

    expect(presenceSpy).toHaveBeenCalledWith(
      "550e8400-e29b-41d4-a716-446655440000",
      true,
      "2024-02-01T10:00:00Z"
    )
    expect(onlineSpy).toHaveBeenCalledWith("550e8400-e29b-41d4-a716-446655440000", true)

    unmount()
  })
})
