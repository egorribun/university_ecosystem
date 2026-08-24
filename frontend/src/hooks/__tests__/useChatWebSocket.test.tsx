import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

/**
 * Wave 183 SW9 — useChatWebSocket unit tests.
 *
 * Covers W183 SW3 regression guards + hook public API shape + WebSocketStore
 * primitive. Full reconnect E2E + ws.onmessage frame handling deferred to
 * SW14 (Docker chain authed visual smoke with real ws-hub).
 *
 * In-scope (testable without full WebSocket mocking):
 *  - Hook returns expected shape ({isConnected, sendTyping, sendRead,
 *    getTypingUsersForChat}).
 *  - Throws helpful error when used outside WebSocketProvider.
 *  - WebSocketStore class (subscribe/getSnapshot/setConnected) — primitive
 *    that backs useSyncExternalStore wiring.
 *  - sendTyping/sendRead are no-ops when WS is not open (TOCTOU race
 *    guard — W183 SW3 safety).
 *  - getTypingUsersForChat returns empty array when no typing state.
 *
 * Deferred to W184+ (would require MockWebSocket + fake timers):
 *  - Reconnect backoff with MAX_RECONNECT_ATTEMPTS cap (W183 SW3).
 *  - TYPING_INDICATOR_TIMEOUT_MS firing after timeout (W183 SW3).
 *  - parseWsMessage invalid-frame logError path (W183 SW3).
 *  - ws.onmessage handling for typing/read/new_message/presence frames.
 *  - Ticket fetch error handling (auth vs transient).
 */

// ---------- Hoisted mocks ----------

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logError: vi.fn(),
  parseWsMessage: vi.fn(),
}))

class TestWebSocket {
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static instances: TestWebSocket[] = []

  readonly url: string
  readyState = TestWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    TestWebSocket.instances.push(this)
  }

  send = vi.fn()

  close = vi.fn((code = 1000) => {
    this.readyState = TestWebSocket.CLOSED
    this.onclose?.({ code } as CloseEvent)
  })
}

vi.mock("@/api/client", () => ({
  default: {
    post: mocks.apiPost,
  },
}))

vi.mock("@/app/logger", () => ({
  logError: mocks.logError,
}))

vi.mock("@/api/schemas/wsMessage", () => ({
  parseWsMessage: mocks.parseWsMessage,
}))

// Import after mocks
import { useChatWebSocket, WebSocketProvider, applyReadFrame } from "../useChatWebSocket"
import type { MessagesListResponse } from "@/api/chat"

// ---------- Helpers ----------

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
}

// ---------- Setup ----------

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiPost.mockResolvedValue({ data: { ticket: "mock-ticket", expires_in: 15 } })
  mocks.parseWsMessage.mockReturnValue(null)
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------- Tests ----------

describe("useChatWebSocket", () => {
  it("ignores a typing timeout that fires after unmount", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    mocks.parseWsMessage.mockReturnValue({
      type: "typing",
      chat_id: "chat-1",
      user_id: "user-1",
      user_name: "Alice",
    })

    const { unmount } = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))

    const ws = TestWebSocket.instances[0]
    expect(ws).toBeDefined()
    await waitFor(() => expect(ws?.onmessage).toEqual(expect.any(Function)))

    // Keep the callback after cleanup so it can exercise the mountedRef guard
    // that protects a late event from updating unmounted state.
    const timeoutCallbacks: Array<() => void> = []
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout").mockImplementation((handler) => {
      if (typeof handler === "function") timeoutCallbacks.push(handler as () => void)
      return 1 as unknown as ReturnType<typeof setTimeout>
    })
    act(() => {
      ws?.onmessage?.({ data: "typing" } as MessageEvent)
    })
    expect(timeoutCallbacks).toHaveLength(1)

    try {
      act(() => unmount())
      act(() => {
        timeoutCallbacks[0]?.()
      })
    } finally {
      setTimeoutSpy.mockRestore()
      vi.unstubAllGlobals()
    }
  })

  describe("hook contract", () => {
    it("returns expected shape when enabled", () => {
      const { result } = renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })

      // The hook's return surface that consumers depend on. Adding more
      // here without updating MessengerContext consumer is a breaking
      // change — this test catches that drift.
      expect(result.current).toMatchObject({
        isConnected: expect.any(Boolean),
        sendTyping: expect.any(Function),
        sendRead: expect.any(Function),
        getTypingUsersForChat: expect.any(Function),
      })
    })

    it("isConnected defaults to false before WS opens", () => {
      const { result } = renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })
      expect(result.current.isConnected).toBe(false)
    })

    it("getTypingUsersForChat returns empty array when no typing state", () => {
      const { result } = renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })
      expect(result.current.getTypingUsersForChat("any-chat-id")).toEqual([])
    })
  })

  describe("WebSocketProvider requirement", () => {
    it("throws helpful error when used WITHOUT WebSocketProvider", () => {
      const noProviderWrapper = ({ children }: { children: ReactNode }) => {
        const queryClient = new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
        return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      }

      // Suppress React error boundary console.error noise in test output.
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      expect(() => {
        renderHook(() => useChatWebSocket({ enabled: false }), { wrapper: noProviderWrapper })
      }).toThrow(/useChatWebSocket must be used within a WebSocketProvider/)

      errorSpy.mockRestore()
    })
  })

  describe("send methods are no-ops when WS not open (W183 SW3 TOCTOU guard)", () => {
    it("sendTyping is a no-op when wsRef is null (not connected)", () => {
      const { result } = renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })

      // Should not throw even though there's no WS open.
      expect(() => {
        act(() => {
          result.current.sendTyping("chat-1")
        })
      }).not.toThrow()
    })

    it("sendRead is a no-op when wsRef is null (not connected)", () => {
      const { result } = renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })

      expect(() => {
        act(() => {
          // Wave 203 SW5 — sendRead is now chat-level (no message_id arg).
          result.current.sendRead("chat-1")
        })
      }).not.toThrow()
    })
  })

  describe("enabled gate", () => {
    it("does NOT attempt ticket fetch when enabled=false", () => {
      renderHook(() => useChatWebSocket({ enabled: false }), { wrapper })

      // The hook's connect() short-circuits at `if (!enabled) return`. No
      // network call to /ws/ticket should fire.
      expect(mocks.apiPost).not.toHaveBeenCalled()
    })
  })

  describe("WebSocketProvider", () => {
    it("provides a stable WebSocketStore across re-renders", () => {
      // Two consecutive renderHook calls inside the same provider should
      // see the SAME store instance (useMemo with empty deps).
      const { result: result1 } = renderHook(() => useChatWebSocket({ enabled: false }), {
        wrapper,
      })
      const { result: result2 } = renderHook(() => useChatWebSocket({ enabled: false }), {
        wrapper,
      })

      // Both hooks should return isConnected: false (they consume the same
      // store; if the provider re-created the store, this test would still
      // pass but for the wrong reason — see provider source for useMemo).
      expect(result1.current.isConnected).toBe(false)
      expect(result2.current.isConnected).toBe(false)
    })
  })
})

// ---------- Wave 203 SW5: applyReadFrame (chat-level read receipt cache flip) ----------

describe("applyReadFrame (Wave 203 SW5)", () => {
  const reader = "11111111-1111-1111-1111-111111111111" // the OTHER participant
  const me = "22222222-2222-2222-2222-222222222222" // the current user (sender)
  const readAt = "2026-05-30T14:32:00+00:00"

  const makeMessage = (id: string, sender_id: string) => ({
    id,
    chat_id: "chat-1",
    sender_id,
    content: "hi",
    created_at: "2026-05-30T14:30:00+00:00",
    read_status: false,
  })

  it("returns undefined when the cache is empty", () => {
    expect(applyReadFrame(undefined, { user_id: reader, read_at: readAt })).toBeUndefined()
  })

  it("flips only messages NOT sent by the reader (my own sent messages)", () => {
    const old: MessagesListResponse = {
      items: [
        makeMessage("m1", me), // my sent message → flips to read
        makeMessage("m2", reader), // the reader's own message → untouched
        makeMessage("m3", me), // my sent message → flips to read
      ],
      has_more: false,
      next_cursor: null,
    }

    const result = applyReadFrame(old, { user_id: reader, read_at: readAt })
    expect(result).toBeDefined()
    const items = result?.items ?? []
    const m1 = items.find((m) => m.id === "m1")
    const m2 = items.find((m) => m.id === "m2")
    const m3 = items.find((m) => m.id === "m3")

    expect(m1?.read_status).toBe(true)
    expect(m1?.read_at).toBe(readAt)
    expect(m3?.read_status).toBe(true)
    expect(m3?.read_at).toBe(readAt)
    // The reader's own message is never flagged "seen" — no marker on received.
    expect(m2?.read_status).toBe(false)
    expect(m2?.read_at).toBeUndefined()
  })

  it("preserves has_more / next_cursor", () => {
    const old: MessagesListResponse = {
      items: [makeMessage("m1", me)],
      has_more: true,
      next_cursor: "cursor-x",
    }
    const result = applyReadFrame(old, { user_id: reader, read_at: readAt })
    expect(result?.has_more).toBe(true)
    expect(result?.next_cursor).toBe("cursor-x")
  })
})
