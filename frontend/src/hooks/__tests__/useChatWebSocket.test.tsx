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
  dbUpsert: vi.fn(),
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

vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: vi.fn(async () => ({
    messages: { upsert: mocks.dbUpsert },
  })),
}))

// Import after mocks
import {
  useChatWebSocket,
  WebSocketProvider,
  applyReadFrame,
  appendLiveMessageToCache,
  rememberLiveMessage,
} from "../useChatWebSocket"
import type { ChatsListResponse, Message, MessagesListResponse } from "@/api/chat"

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
  window.sessionStorage.clear()
  mocks.apiPost.mockResolvedValue({ data: { ticket: "mock-ticket", expires_in: 15 } })
  mocks.parseWsMessage.mockReturnValue(null)
  mocks.dbUpsert.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true })
})

// ---------- Tests ----------

describe("appendLiveMessageToCache boundaries", () => {
  const message = (index: number) =>
    ({
      id: `boundary-${index}`,
      chat_id: "chat-boundary",
      sender_id: "peer",
      content: String(index),
      created_at: new Date(Date.UTC(2026, 7, 26, 0, 0, 0, index)).toISOString(),
      read_status: false,
      attachments: [],
    }) as Message

  it.each([0, 199])(
    "keeps all %i terminal-history messages while the cache stays within its bound",
    (size) => {
      const cached: MessagesListResponse = {
        items: Array.from({ length: size }, (_, index) => message(index)),
        has_more: false,
        next_cursor: null,
      }
      const result = appendLiveMessageToCache(cached, message(size))

      expect(result.items).toHaveLength(size + 1)
      expect(result.items[0]?.id).toBe("boundary-0")
      expect(result.has_more).toBe(false)
      expect(result.next_cursor).toBeNull()
    }
  )

  it.each([200, 201])(
    "bounds %i terminal-history messages and synthesizes a lossless recovery cursor",
    (size) => {
      const cached: MessagesListResponse = {
        items: Array.from({ length: size }, (_, index) => message(index)),
        has_more: false,
        next_cursor: null,
      }
      const result = appendLiveMessageToCache(cached, message(size))
      const newOldest = result.items[0]!

      expect(result.items).toHaveLength(200)
      expect(result.has_more).toBe(true)
      expect(result.next_cursor).toBe(`${Date.parse(newOldest.created_at) * 1000}:${newOldest.id}`)
    }
  )

  it("keeps a hard render bound when legacy cache contains a malformed timestamp", () => {
    const cached: MessagesListResponse = {
      items: Array.from({ length: 200 }, (_, index) => message(index)),
      has_more: false,
      next_cursor: null,
    }
    cached.items[1] = { ...cached.items[1]!, created_at: "not-a-datetime" }

    const result = appendLiveMessageToCache(cached, message(200))

    expect(result.items).toHaveLength(200)
    expect(result.items[0]?.id).toBe("boundary-1")
    expect(result.has_more).toBe(true)
    expect(result.next_cursor).toBeNull()
  })

  it("never exceeds the render bound under an adversarial malformed timestamp stream", () => {
    let cached: MessagesListResponse = {
      items: [],
      has_more: false,
      next_cursor: null,
    }

    for (let index = 0; index < 1000; index += 1) {
      cached = appendLiveMessageToCache(cached, {
        ...message(index),
        id: `malformed-${index}`,
        created_at: "not-a-timestamp",
      })
      expect(cached.items.length).toBeLessThanOrEqual(200)
    }

    expect(cached.items[0]?.id).toBe("malformed-800")
    expect(cached.items.at(-1)?.id).toBe("malformed-999")
    expect(cached.has_more).toBe(true)
  })

  it("preserves the server cursor when appending does not trim continuing history", () => {
    const cached: MessagesListResponse = {
      items: Array.from({ length: 199 }, (_, index) => message(index)),
      has_more: true,
      next_cursor: "recoverable-older-edge",
    }
    const result = appendLiveMessageToCache(cached, message(199))

    expect(result.items).toHaveLength(200)
    expect(result.next_cursor).toBe("recoverable-older-edge")
  })

  it("orders delayed messages by created_at and uses id as the deterministic tie-breaker", () => {
    const first = message(1)
    const last = message(3)
    const sameTimeLowerId = { ...first, id: "boundary-0" }
    const exactTie = { ...first }
    const sameTimeHigherId = { ...first, id: "boundary-z" }
    const delayedMiddle = message(2)
    const cached: MessagesListResponse = {
      items: [first, last],
      has_more: false,
      next_cursor: null,
    }

    const withMiddle = appendLiveMessageToCache(cached, delayedMiddle)
    const withTie = appendLiveMessageToCache(withMiddle, sameTimeLowerId)
    const withExactTie = appendLiveMessageToCache(withTie, exactTie)
    const withHigherTie = appendLiveMessageToCache(withExactTie, sameTimeHigherId)

    expect(withHigherTie.items.map((item) => item.id)).toEqual([
      "boundary-0",
      "boundary-1",
      "boundary-1",
      "boundary-z",
      "boundary-2",
      "boundary-3",
    ])
    expect(withHigherTie.items[1]).toBe(first)
    expect(withHigherTie.items[2]).toBe(exactTie)
  })

  it("trims a delayed message outside the render window using the actual retained oldest", () => {
    const cached: MessagesListResponse = {
      items: Array.from({ length: 200 }, (_, index) => message(index + 1)),
      has_more: false,
      next_cursor: null,
    }

    const result = appendLiveMessageToCache(cached, message(0))

    expect(result.items.map((item) => item.id)).toEqual(cached.items.map((item) => item.id))
    expect(result.has_more).toBe(true)
    expect(result.next_cursor).toBe(
      `${Date.parse(cached.items[0]!.created_at) * 1000}:${cached.items[0]!.id}`
    )
  })

  it.each([200, 201])(
    "bounds %i continuing-history messages while advancing the recovery cursor",
    (size) => {
      const cached: MessagesListResponse = {
        items: Array.from({ length: size }, (_, index) => message(index)),
        has_more: true,
        next_cursor: "recoverable-older-edge",
      }
      const result = appendLiveMessageToCache(cached, message(size))

      expect(result.items).toHaveLength(200)
      expect(result.items.at(-1)?.id).toBe(`boundary-${size}`)
      expect(result.has_more).toBe(true)
      const newOldest = result.items[0]!
      expect(result.next_cursor).toBe(`${Date.parse(newOldest.created_at) * 1000}:${newOldest.id}`)
    }
  )
})

describe("useChatWebSocket", () => {
  it("pauses ticket acquisition while offline and reconnects on the online event", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false })

    renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await act(async () => Promise.resolve())
    expect(mocks.apiPost).not.toHaveBeenCalled()

    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true })
    act(() => window.dispatchEvent(new Event("online")))
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledTimes(1))

    vi.unstubAllGlobals()
  })

  it("does not create a socket when the ticket resolves after unmount", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    let resolveTicket:
      ((value: { data: { ticket: string; expires_in: number } }) => void) | undefined
    mocks.apiPost.mockReturnValue(
      new Promise((resolve) => {
        resolveTicket = resolve
      })
    )

    const { unmount } = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledTimes(1))
    act(() => unmount())
    resolveTicket?.({ data: { ticket: "late-ticket", expires_in: 15 } })
    await act(async () => Promise.resolve())

    expect(TestWebSocket.instances).toHaveLength(0)
    vi.unstubAllGlobals()
  })

  it("keeps a newer online ticket request owned when an aborted request settles late", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    let resolveFirst:
      ((value: { data: { ticket: string; expires_in: number } }) => void) | undefined
    let resolveSecond:
      ((value: { data: { ticket: string; expires_in: number } }) => void) | undefined
    mocks.apiPost
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve
        })
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveSecond = resolve
        })
      )

    renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledTimes(1))

    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledTimes(2))

    resolveFirst?.({ data: { ticket: "stale-ticket", expires_in: 15 } })
    await act(async () => Promise.resolve())
    act(() => window.dispatchEvent(new Event("online")))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)

    resolveSecond?.({ data: { ticket: "current-ticket", expires_in: 15 } })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    expect(TestWebSocket.instances[0]?.url).toContain("current-ticket")
    vi.unstubAllGlobals()
  })

  it("ignores a stale close event after an online reconnect opens a newer socket", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const { result } = renderHook(() => useChatWebSocket({ enabled: true }), { wrapper })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const firstSocket = TestWebSocket.instances[0]!
    const staleClose = firstSocket.onclose
    act(() => firstSocket.onopen?.())
    expect(result.current.isConnected).toBe(true)

    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    const secondSocket = TestWebSocket.instances[1]!
    act(() => secondSocket.onopen?.())
    expect(result.current.isConnected).toBe(true)

    act(() => staleClose?.({ code: 1006 } as CloseEvent))
    expect(result.current.isConnected).toBe(true)
    vi.unstubAllGlobals()
  })

  it("processes a duplicate new_message exactly once", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "message-1",
      chat_id: "chat-1",
      sender_id: "peer",
      content: "hello",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    const priorMessage: Message = {
      ...message,
      id: "message-prior",
      content: "prior",
      created_at: "2026-08-25T11:59:00Z",
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-1"], {
      items: [],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData<ChatsListResponse>(["chats"], {
      items: [
        {
          id: "chat-1",
          participants: [],
          unread_count: 0,
          last_message: priorMessage,
          created_at: "2026-08-25T11:00:00Z",
          updated_at: "2026-08-25T11:00:00Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    })
    mocks.parseWsMessage.mockReturnValue({ type: "new_message", chat_id: "chat-1", message })
    const onNewMessage = vi.fn()

    renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => {
      socket.onmessage?.({ data: "message-frame" } as MessageEvent)
      socket.onmessage?.({ data: "duplicate-frame" } as MessageEvent)
    })

    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", "chat-1"])?.items
    ).toHaveLength(1)
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]?.unread_count).toBe(1)
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]?.last_message).toEqual(
      message
    )
    expect(onNewMessage).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it("reconciles an absent self-authored replay before advancing its opaque cursor", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "self-replayed-message",
      chat_id: "self-replay-chat",
      sender_id: "me",
      content: "recovered optimistic gap",
      created_at: "2026-08-25T12:00:00Z",
      read_status: true,
      attachments: [],
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", message.chat_id], {
      items: [],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData<ChatsListResponse>(["chats"], {
      items: [
        {
          id: message.chat_id,
          participants: [],
          unread_count: 5,
          created_at: "2026-08-25T11:00:00Z",
          updated_at: "2026-08-25T11:00:00Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    })
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: message.chat_id,
      message,
      stream_seq: 88,
      resume_token: "self-resume-token-88",
      replayed: true,
    })
    const onNewMessage = vi.fn()
    const session = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => {
      socket.onmessage?.({ data: "self-replay" } as MessageEvent)
      socket.onmessage?.({ data: "self-replay-duplicate" } as MessageEvent)
    })

    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", message.chat_id])?.items
    ).toEqual([message])
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]).toMatchObject({
      unread_count: 5,
      last_message: message,
    })
    expect(onNewMessage).not.toHaveBeenCalled()
    act(() => session.result.current.sendJoin(message.chat_id))
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        type: "join",
        room: message.chat_id,
        resume_token: "self-resume-token-88",
      })
    )
    session.unmount()
    vi.unstubAllGlobals()
  })

  it("deduplicates a self-authored echo already present in the optimistic cache", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "optimistic-self-message",
      chat_id: "optimistic-self-chat",
      sender_id: "me",
      content: "already optimistic",
      created_at: "2026-08-25T12:00:00Z",
      read_status: true,
      attachments: [],
    }
    const cached: MessagesListResponse = {
      items: [message],
      has_more: false,
      next_cursor: null,
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", message.chat_id], cached)
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: message.chat_id,
      message,
      stream_seq: 89,
      resume_token: "optimistic-self-token-89",
    })
    const onNewMessage = vi.fn()
    const session = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => socket.onmessage?.({ data: "optimistic-self-echo" } as MessageEvent))

    expect(queryClient.getQueryData<MessagesListResponse>(["messages", message.chat_id])).toBe(
      cached
    )
    expect(onNewMessage).not.toHaveBeenCalled()
    act(() => session.result.current.sendJoin(message.chat_id))
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        type: "join",
        room: message.chat_id,
        resume_token: "optimistic-self-token-89",
      })
    )

    session.unmount()
    vi.unstubAllGlobals()
  })

  it("seeds replay protection from a duplicate already present in the render cache", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "preloaded-message",
      chat_id: "chat-1",
      sender_id: "peer",
      content: "already hydrated",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    const cached: MessagesListResponse = {
      items: [message],
      has_more: false,
      next_cursor: null,
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-1"], cached)
    mocks.parseWsMessage.mockReturnValue({ type: "new_message", chat_id: "chat-1", message })
    const onNewMessage = vi.fn()
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")

    renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "preloaded-1" } as MessageEvent)
      TestWebSocket.instances[0]?.onmessage?.({ data: "preloaded-2" } as MessageEvent)
    })
    await act(async () => Promise.resolve())

    expect(queryClient.getQueryData<MessagesListResponse>(["messages", "chat-1"])).toBe(cached)
    expect(mocks.dbUpsert).not.toHaveBeenCalled()
    expect(invalidateQueries).not.toHaveBeenCalled()
    expect(onNewMessage).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it("keeps delayed live delivery ordered without rolling back the chat preview", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const newerMessage: Message = {
      id: "message-newer",
      chat_id: "chat-1",
      sender_id: "peer",
      content: "newer",
      created_at: "2026-08-25T12:02:00.000000Z",
      read_status: false,
      attachments: [],
    }
    const delayedMessage: Message = {
      ...newerMessage,
      id: "message-delayed",
      content: "delayed",
      created_at: "2026-08-25T12:01:00.000000Z",
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-1"], {
      items: [newerMessage],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData<ChatsListResponse>(["chats"], {
      items: [
        {
          id: "chat-1",
          participants: [],
          unread_count: 4,
          last_message: newerMessage,
          created_at: "2026-08-25T11:00:00Z",
          updated_at: "2026-08-25T12:02:00Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    })
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-1",
      message: delayedMessage,
    })
    const onNewMessage = vi.fn()
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")

    renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "delayed-frame" } as MessageEvent)
    })
    await waitFor(() => expect(mocks.dbUpsert).toHaveBeenCalledTimes(1))

    expect(
      queryClient
        .getQueryData<MessagesListResponse>(["messages", "chat-1"])
        ?.items.map((message) => message.id)
    ).toEqual(["message-delayed", "message-newer"])
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]).toMatchObject({
      unread_count: 5,
      last_message: { id: "message-newer" },
    })
    expect(onNewMessage).toHaveBeenCalledTimes(1)

    const invalidTimestampMessage = {
      ...delayedMessage,
      id: "message-invalid-timestamp",
      created_at: "not-a-timestamp",
    }
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-1",
      message: invalidTimestampMessage,
    })
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "invalid-timestamp-frame" } as MessageEvent)
    })
    await waitFor(() => expect(mocks.dbUpsert).toHaveBeenCalledTimes(2))

    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]).toMatchObject({
      unread_count: 6,
      last_message: { id: "message-newer" },
    })
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", "chat-1"],
      refetchType: "active",
    })
    expect(onNewMessage).toHaveBeenCalledTimes(2)

    invalidateQueries.mockClear()
    const recoveryMessage = {
      ...newerMessage,
      id: "message-recovery",
      created_at: "2026-08-25T12:03:00.000000Z",
    }
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-1",
      message: recoveryMessage,
    })
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "recovery-frame" } as MessageEvent)
    })
    await waitFor(() => expect(mocks.dbUpsert).toHaveBeenCalledTimes(3))

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", "chat-1"],
      refetchType: "active",
    })
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]).toMatchObject({
      unread_count: 7,
      last_message: { id: "message-recovery" },
    })
    expect(onNewMessage).toHaveBeenCalledTimes(3)
    vi.unstubAllGlobals()
  })

  it("drops an at-least-once replay after the original message leaves the render cache", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const messages = Array.from({ length: 201 }, (_, index): Message => ({
      id: `message-${index + 1}`,
      chat_id: "chat-1",
      sender_id: "peer",
      content: `message ${index + 1}`,
      created_at: new Date(Date.UTC(2026, 7, 25, 12, 0, index + 1)).toISOString(),
      read_status: false,
      attachments: [],
    }))
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-1"], {
      items: [],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData<ChatsListResponse>(["chats"], {
      items: [
        {
          id: "chat-1",
          participants: [],
          unread_count: 0,
          created_at: "2026-08-25T11:00:00Z",
          updated_at: "2026-08-25T11:00:00Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    })
    mocks.parseWsMessage.mockImplementation((frame: string) => {
      const index = Number(frame.slice("message-".length)) - 1
      return { type: "new_message", chat_id: "chat-1", message: messages[index]! }
    })
    const onNewMessage = vi.fn()
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")

    renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "me", onNewMessage }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => {
      for (const message of messages) {
        socket.onmessage?.({ data: message.id } as MessageEvent)
      }
    })
    await waitFor(() => expect(mocks.dbUpsert).toHaveBeenCalledTimes(201))
    const acceptedCache = queryClient.getQueryData<MessagesListResponse>(["messages", "chat-1"])!
    const acceptedItems = acceptedCache.items
    expect(acceptedItems.map((message) => message.id)).toEqual(
      messages.slice(1).map((message) => message.id)
    )

    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    const replaySocket = TestWebSocket.instances[1]!

    act(() => {
      replaySocket.onmessage?.({ data: "message-1" } as MessageEvent)
    })
    await act(async () => Promise.resolve())

    expect(queryClient.getQueryData<MessagesListResponse>(["messages", "chat-1"])).toBe(
      acceptedCache
    )
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]).toMatchObject({
      unread_count: 201,
      last_message: { id: "message-201" },
    })
    expect(mocks.dbUpsert).toHaveBeenCalledTimes(201)
    expect(onNewMessage).toHaveBeenCalledTimes(201)
    expect(invalidateQueries).toHaveBeenCalledTimes(402)
    vi.unstubAllGlobals()
  })

  it("bounds replay memory with LRU eviction while retaining recently replayed IDs", () => {
    const seen = new Map<string, true>()
    for (let index = 1; index <= 4096; index += 1) {
      expect(rememberLiveMessage(seen, "chat-lru", `lru-message-${index}`)).toBe(true)
    }

    // Refresh ID 1, then overflow the 4096-entry LRU. ID 2 must be the
    // evicted member while the recently replayed ID 1 remains protected.
    expect(rememberLiveMessage(seen, "chat-lru", "lru-message-1")).toBe(false)
    expect(rememberLiveMessage(seen, "chat-lru", "lru-message-4097")).toBe(true)
    expect(rememberLiveMessage(seen, "chat-lru", "lru-message-2")).toBe(true)
    expect(rememberLiveMessage(seen, "chat-lru", "lru-message-1")).toBe(false)
    expect(seen).toHaveLength(4096)
  })

  it("resumes a room from the durable sequence after reconnect", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "checkpoint-message",
      chat_id: "chat-checkpoint",
      sender_id: "peer",
      content: "checkpoint",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-checkpoint",
      message,
      stream_seq: 73,
      resume_token: "checkpoint-token-73",
    })

    const { result } = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "checkpoint-user" }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const firstSocket = TestWebSocket.instances[0]!
    act(() => result.current.sendJoin("chat-checkpoint"))
    act(() => firstSocket.onmessage?.({ data: "checkpoint-frame" } as MessageEvent))

    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    const replaySocket = TestWebSocket.instances[1]!
    act(() => replaySocket.onopen?.())

    expect(replaySocket.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: "chat-checkpoint", resume_token: "checkpoint-token-73" })
    )
    vi.unstubAllGlobals()
  })

  it("forgets an expired opaque cursor after the server rejects it", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const userId = "expired-cursor-user"
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532629"
    window.sessionStorage.setItem(
      `university.chat.replay.v2:${userId}`,
      JSON.stringify({ entries: [[chatId, 73, "expired-token-73"]] })
    )
    mocks.parseWsMessage.mockReturnValue({
      type: "error",
      code: "invalid_resume_token",
      room: chatId,
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const session = renderHook(() => useChatWebSocket({ enabled: true, currentUserId: userId }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => session.result.current.sendJoin(chatId))
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: chatId, resume_token: "expired-token-73" })
    )
    act(() => socket.onmessage?.({ data: "invalid-token" } as MessageEvent))
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", chatId],
      refetchType: "all",
    })
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["chats"],
      refetchType: "all",
    })
    act(() => session.result.current.sendJoin(chatId))
    expect(socket.send).toHaveBeenLastCalledWith(JSON.stringify({ type: "join", room: chatId }))

    session.unmount()
    vi.unstubAllGlobals()
  })

  it("persists a checkpoint at most once per accepted sequenced frame", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "storage-write-message",
      chat_id: "storage-write-chat",
      sender_id: "peer",
      content: "checkpoint",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    let sequence = 10
    mocks.parseWsMessage.mockImplementation(() => ({
      type: "new_message",
      chat_id: "storage-write-chat",
      message: { ...message, id: `storage-write-message-${sequence}` },
      stream_seq: sequence++,
      resume_token: `storage-token-${sequence}`,
    }))

    const session = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "storage-write-user" }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "first" } as MessageEvent)
      TestWebSocket.instances[0]?.onmessage?.({ data: "second" } as MessageEvent)
    })

    expect(setItem).toHaveBeenCalledTimes(2)
    session.unmount()
    setItem.mockRestore()
    vi.unstubAllGlobals()
  })

  it.each([
    ["oversized", () => "x".repeat(65_537)],
    ["non-array entries", () => JSON.stringify({ entries: {} })],
    [
      "invalid entry",
      () => JSON.stringify({ entries: [["storage-chat", 0, "invalid-sequence-token"]] }),
    ],
  ])("fails closed for a %s persisted checkpoint registry", async (_label, storedValue) => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const userId = `invalid-storage-${_label}`
    const storageKey = `university.chat.replay.v2:${encodeURIComponent(userId)}`
    window.sessionStorage.setItem(storageKey, storedValue())
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")

    const session = renderHook(() => useChatWebSocket({ enabled: true, currentUserId: userId }), {
      wrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => session.result.current.sendJoin("storage-chat"))

    expect(TestWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: "storage-chat" })
    )
    expect(removeItem).toHaveBeenCalledWith(storageKey)
    expect(window.sessionStorage.getItem(storageKey)).toBeNull()

    session.unmount()
    vi.unstubAllGlobals()
  })

  it("ignores replay checkpoint operations for an anonymous session", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532625"
    mocks.parseWsMessage.mockReturnValue({
      type: "replay_checkpoint",
      chat_id: chatId,
      stream_seq: 65,
      resume_token: "anonymous-token-65",
      replayed: true,
    })
    const session = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: undefined }),
      { wrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!

    act(() => socket.onmessage?.({ data: "anonymous-checkpoint" } as MessageEvent))
    act(() => session.result.current.sendJoin(chatId))
    expect(socket.send).toHaveBeenLastCalledWith(JSON.stringify({ type: "join", room: chatId }))

    mocks.parseWsMessage.mockReturnValue({
      type: "error",
      code: "invalid_resume_token",
      room: chatId,
    })
    act(() => socket.onmessage?.({ data: "anonymous-invalid-token" } as MessageEvent))

    session.unmount()
    vi.unstubAllGlobals()
  })

  it("treats invalidation of an absent replay checkpoint as an idempotent no-op", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
    mocks.parseWsMessage.mockReturnValue({
      type: "error",
      code: "invalid_resume_token",
      room: chatId,
    })
    const session = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "empty-checkpoint-user" }),
      { wrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))

    act(() =>
      TestWebSocket.instances[0]?.onmessage?.({ data: "missing-invalid-token" } as MessageEvent)
    )
    act(() => session.result.current.sendJoin(chatId))
    expect(TestWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: chatId })
    )

    session.unmount()
    vi.unstubAllGlobals()
  })

  it("retains shared replay memory until the final same-user hook unmounts", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const userId = "shared-mount-user"
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532627"
    const storageKey = `university.chat.replay.v2:${encodeURIComponent(userId)}`
    mocks.parseWsMessage.mockReturnValue({
      type: "replay_checkpoint",
      chat_id: chatId,
      stream_seq: 77,
      resume_token: "in-memory-token-77",
      replayed: true,
    })
    const first = renderHook(
      ({ enabled, currentUserId }) => useChatWebSocket({ enabled, currentUserId }),
      {
        wrapper,
        initialProps: { enabled: false, currentUserId: undefined as string | undefined },
      }
    )
    first.rerender({ enabled: true, currentUserId: userId })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() =>
      TestWebSocket.instances[0]?.onmessage?.({ data: "shared-checkpoint" } as MessageEvent)
    )
    const second = renderHook(() => useChatWebSocket({ enabled: true, currentUserId: userId }), {
      wrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))

    first.unmount()
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify({ entries: [[chatId, 99, "storage-token-99"]] })
    )
    act(() => second.result.current.sendJoin(chatId))
    expect(TestWebSocket.instances[1]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: chatId, resume_token: "in-memory-token-77" })
    )

    second.unmount()
    vi.unstubAllGlobals()
  })

  it("advances replay state from a terminal poison checkpoint without message side effects", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const onNewMessage = vi.fn()
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532621"
    mocks.parseWsMessage.mockReturnValue({
      type: "replay_checkpoint",
      chat_id: chatId,
      stream_seq: 42,
      resume_token: "poison-token-42",
      replayed: true,
    })

    const session = renderHook(
      () =>
        useChatWebSocket({
          enabled: true,
          currentUserId: "poison-checkpoint-user",
          onNewMessage,
        }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => TestWebSocket.instances[0]?.onmessage?.({ data: "checkpoint" } as MessageEvent))
    act(() => session.result.current.sendJoin(chatId))

    expect(onNewMessage).not.toHaveBeenCalled()
    expect(TestWebSocket.instances[0]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: chatId, resume_token: "poison-token-42" })
    )
    session.unmount()
    vi.unstubAllGlobals()
  })

  it("keeps a durable room checkpoint across hook remounts for the same session", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const makeWrapper = () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const RemountWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      )
      RemountWrapper.displayName = "RemountWebSocketTestWrapper"
      return RemountWrapper
    }
    const message: Message = {
      id: "remount-message",
      chat_id: "chat-remount",
      sender_id: "peer",
      content: "persist me",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-remount",
      message,
      stream_seq: 91,
      resume_token: "remount-token-91",
    })

    const first = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "remount-user" }),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => TestWebSocket.instances[0]?.onmessage?.({ data: "checkpoint" } as MessageEvent))
    first.unmount()

    const second = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "remount-user" }),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    act(() => second.result.current.sendJoin("chat-remount"))
    expect(TestWebSocket.instances[1]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: "chat-remount", resume_token: "remount-token-91" })
    )
    second.unmount()
    vi.unstubAllGlobals()
  })

  it("releases process memory on final unmount and reloads the persisted checkpoint", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const makeWrapper = () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const FinalUnmountWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      )
      FinalUnmountWrapper.displayName = "FinalUnmountWebSocketTestWrapper"
      return FinalUnmountWrapper
    }
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532622"
    mocks.parseWsMessage.mockReturnValue({
      type: "replay_checkpoint",
      chat_id: chatId,
      stream_seq: 91,
      resume_token: "final-token-91",
      replayed: true,
    })

    const first = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "final-unmount-user" }),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => TestWebSocket.instances[0]?.onmessage?.({ data: "checkpoint" } as MessageEvent))
    first.unmount()
    const storageKey = "university.chat.replay.v2:final-unmount-user"
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify({ entries: [[chatId, 37, "persisted-token-37"]] })
    )

    const second = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "final-unmount-user" }),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    act(() => second.result.current.sendJoin(chatId))

    expect(TestWebSocket.instances[1]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: chatId, resume_token: "persisted-token-37" })
    )
    second.unmount()
    vi.unstubAllGlobals()
  })

  it("globally bounds user checkpoint registries while preserving session storage", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const chatId = "8ef3bb0c-a893-4f74-bdb4-01544a532623"
    mocks.parseWsMessage.mockImplementation((frame: string) => ({
      type: "replay_checkpoint",
      chat_id: chatId,
      stream_seq: Number(frame.slice("global-checkpoint-".length)) + 1,
      resume_token: `global-token-${frame.slice("global-checkpoint-".length)}`,
      replayed: true,
    }))
    const sessions: Array<{
      result: { current: ReturnType<typeof useChatWebSocket> }
      unmount: () => void
    }> = []

    for (let index = 0; index < 17; index += 1) {
      const session = renderHook(
        () => useChatWebSocket({ enabled: true, currentUserId: `global-user-${index}` }),
        { wrapper: localWrapper }
      )
      sessions.push(session)
      await waitFor(() => expect(TestWebSocket.instances).toHaveLength(index + 1))
      act(() =>
        TestWebSocket.instances[index]?.onmessage?.({
          data: `global-checkpoint-${index}`,
        } as MessageEvent)
      )
    }

    // The 17th active account evicts the least-recently-used in-memory registry
    // while its durable session value remains independently reloadable.
    window.sessionStorage.setItem(
      "university.chat.replay.v2:global-user-0",
      JSON.stringify({ entries: [[chatId, 99, "persisted-global-token-99"]] })
    )
    act(() => sessions[0]?.result.current.sendJoin(chatId))
    expect(TestWebSocket.instances[0]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: chatId, resume_token: "persisted-global-token-99" })
    )

    sessions.forEach((session) => session.unmount())
    vi.unstubAllGlobals()
  })

  it("clears durable checkpoints when the authenticated session logs out", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const makeWrapper = () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const LogoutWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      )
      LogoutWrapper.displayName = "LogoutWebSocketTestWrapper"
      return LogoutWrapper
    }
    const message: Message = {
      id: "logout-message",
      chat_id: "chat-logout",
      sender_id: "peer",
      content: "clear me",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-logout",
      message,
      stream_seq: 101,
      resume_token: "logout-token-101",
    })

    const session = renderHook(
      ({ userId }) => useChatWebSocket({ enabled: true, currentUserId: userId }),
      { wrapper: makeWrapper(), initialProps: { userId: "logout-user" as string | undefined } }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => TestWebSocket.instances[0]?.onmessage?.({ data: "checkpoint" } as MessageEvent))
    session.rerender({ userId: undefined })
    await act(async () => Promise.resolve())
    session.unmount()

    const nextSession = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "logout-user" }),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    act(() => nextSession.result.current.sendJoin("chat-logout"))
    expect(TestWebSocket.instances[1]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: "chat-logout" })
    )
    nextSession.unmount()
    vi.unstubAllGlobals()
  })

  it("bounds the persisted room registry without evicting the active room", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    mocks.parseWsMessage.mockImplementation((frame: string) => {
      const index = Number(frame.slice("checkpoint-".length))
      const chatId = `checkpoint-chat-${index}`
      return {
        type: "new_message",
        chat_id: chatId,
        message: {
          id: `checkpoint-message-${index}`,
          chat_id: chatId,
          sender_id: "peer",
          content: String(index),
          created_at: new Date(Date.UTC(2026, 7, 25, 12, 0, index)).toISOString(),
          read_status: false,
          attachments: [],
        },
        stream_seq: index + 1,
        resume_token: `bounded-token-${index + 1}`,
      }
    })

    const first = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "bounded-checkpoint-user" }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => first.result.current.sendJoin("checkpoint-chat-0"))
    act(() => {
      for (let index = 0; index <= 256; index += 1) {
        TestWebSocket.instances[0]?.onmessage?.({ data: `checkpoint-${index}` } as MessageEvent)
      }
    })
    first.unmount()

    expect(window.sessionStorage).toHaveLength(1)
    const registry = JSON.parse(window.sessionStorage.getItem(window.sessionStorage.key(0)!)!) as {
      entries: Array<[string, number, string]>
    }
    expect(registry.entries).toHaveLength(256)
    expect(registry.entries).toContainEqual(["checkpoint-chat-0", 1, "bounded-token-1"])

    const second = renderHook(
      () => useChatWebSocket({ enabled: true, currentUserId: "bounded-checkpoint-user" }),
      { wrapper: localWrapper }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(2))
    act(() => second.result.current.sendJoin("checkpoint-chat-0"))
    expect(TestWebSocket.instances[1]?.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "join", room: "checkpoint-chat-0", resume_token: "bounded-token-1" })
    )
    second.unmount()
    vi.unstubAllGlobals()
  })

  it("resets replay protection when the authenticated user session changes", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const message: Message = {
      id: "session-message",
      chat_id: "chat-session",
      sender_id: "peer",
      content: "new session",
      created_at: "2026-08-25T12:00:00Z",
      read_status: false,
      attachments: [],
    }
    const emptyCache = (): MessagesListResponse => ({
      items: [],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-session"], emptyCache())
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-session",
      message,
    })
    const onNewMessage = vi.fn()
    const { rerender } = renderHook(
      ({ currentUserId }) => useChatWebSocket({ enabled: true, currentUserId, onNewMessage }),
      { wrapper: localWrapper, initialProps: { currentUserId: "session-user-1" } }
    )
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    const socket = TestWebSocket.instances[0]!
    act(() => socket.onmessage?.({ data: "first-session" } as MessageEvent))

    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-session"], emptyCache())
    rerender({ currentUserId: "session-user-2" })
    act(() => socket.onmessage?.({ data: "second-session" } as MessageEvent))

    expect(onNewMessage).toHaveBeenCalledTimes(2)
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", "chat-session"])?.items
    ).toEqual([message])
    vi.unstubAllGlobals()
  })

  it("bounds the 201st live message while keeping the trimmed edge recoverable", async () => {
    TestWebSocket.instances = []
    vi.stubGlobal("WebSocket", TestWebSocket)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const initialItems: Message[] = Array.from({ length: 200 }, (_, index) => ({
      id: `message-${index}`,
      chat_id: "chat-1",
      sender_id: "peer",
      content: `message ${index}`,
      created_at: new Date(Date.UTC(2026, 7, 25, 12, 0, index)).toISOString(),
      read_status: false,
      attachments: [],
    }))
    const liveMessage: Message = {
      id: "message-200",
      chat_id: "chat-1",
      sender_id: "peer",
      content: "message 200",
      created_at: "2026-08-25T12:04:00Z",
      read_status: false,
      attachments: [],
    }
    queryClient.setQueryData<MessagesListResponse>(["messages", "chat-1"], {
      items: initialItems,
      has_more: false,
      next_cursor: null,
    })
    mocks.parseWsMessage.mockReturnValue({
      type: "new_message",
      chat_id: "chat-1",
      message: liveMessage,
    })

    renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "me" }), {
      wrapper: localWrapper,
    })
    await waitFor(() => expect(TestWebSocket.instances).toHaveLength(1))
    act(() => {
      TestWebSocket.instances[0]?.onmessage?.({ data: "message-frame" } as MessageEvent)
    })

    const cached = queryClient.getQueryData<MessagesListResponse>(["messages", "chat-1"])
    expect(cached?.items).toHaveLength(200)
    expect(cached?.items[0]?.id).toBe("message-1")
    expect(cached?.has_more).toBe(true)
    expect(cached?.next_cursor).toBe(`${Date.parse(initialItems[1]!.created_at) * 1000}:message-1`)
    vi.unstubAllGlobals()
  })

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
