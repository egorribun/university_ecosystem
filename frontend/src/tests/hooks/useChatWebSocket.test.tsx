import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { renderToString } from "react-dom/server"
import { server } from "../mocks/server"
import { http, HttpResponse } from "msw"

import {
  useChatWebSocket,
  WebSocketProvider,
  applyReadFrame,
  applyMessageEditedFrame,
  applyMessageDeletedFrame,
  applyReactionChangedFrame,
  calculateReconnectDelay,
} from "@/hooks/useChatWebSocket"
import { chatApi, type Message, type MessagesListResponse } from "@/api/chat"
import api from "@/api/client"
import * as wsMessageSchema from "@/api/schemas/wsMessage"

const mocks = vi.hoisted(() => ({
  getDatabase: vi.fn(),
}))

vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: mocks.getDatabase,
}))

// Fixed valid-format UUIDs for frame fixtures (parseWsMessage validates v.uuid()).
const USER_A = "11111111-1111-4111-8111-111111111111"
const USER_B = "22222222-2222-4222-8222-222222222222"
const CHAT_ID = "33333333-3333-4333-8333-333333333333"
const MSG_ID = "44444444-4444-4444-8444-444444444444"

function makeMessage(over: Partial<Message> = {}): Message {
  return {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: USER_A,
    content: "hello",
    created_at: "2026-01-15T10:00:00.000Z",
    read_status: false,
    read_at: null,
    attachments: [],
    reactions: [],
    ...over,
  } as Message
}

function makeList(items: Message[]): MessagesListResponse {
  return { items, has_more: false } as MessagesListResponse
}

type ChatHookOptions = Parameters<typeof useChatWebSocket>[0]

async function mountAndOpen(opts: ChatHookOptions, queryClient = new QueryClient()) {
  const rendered = renderHook(() => useChatWebSocket(opts), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    ),
  })
  await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(0))
  const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
  act(() => socket.open())
  return { socket, queryClient, ...rendered }
}

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

// Wave 113 -> Session 15: un-skipped. The hook fetches the upgrade ticket via
// axios (api.post("/ws/ticket", null, { baseURL: "" })), NOT global fetch — the
// old vi.stubGlobal("fetch") stub never intercepted it, so the presence test
// timed out. A bare /ws/ticket MSW handler (src/tests/mocks/handlers.ts) now
// resolves the ticket so the WebSocket is created.
describe("useChatWebSocket", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    mocks.getDatabase.mockResolvedValue({
      messages: { upsert: vi.fn().mockResolvedValue(undefined) },
    })
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("rejects usage outside WebSocketProvider", () => {
    expect(() => renderHook(() => useChatWebSocket({ enabled: false }))).toThrow(
      "useChatWebSocket must be used within a WebSocketProvider"
    )
  })

  it("uses the disconnected server snapshot during SSR", () => {
    const client = new QueryClient()
    const Probe = () => {
      const { isConnected } = useChatWebSocket({ enabled: false })
      return <span>{String(isConnected)}</span>
    }

    const html = renderToString(
      <QueryClientProvider client={client}>
        <WebSocketProvider>
          <Probe />
        </WebSocketProvider>
      </QueryClientProvider>
    )

    expect(html).toContain("false")
  })

  it("emits presence updates with last seen information", async () => {
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

    // Wait for the async ticket fetch to complete and WebSocket to be created
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
    })

    const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    expect(socket).toBeDefined()

    act(() => {
      socket!.open()
    })

    act(() => {
      socket!.receive({
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

  it("calls onNewMessage for a frame from another sender", async () => {
    const onNewMessage = vi.fn()
    const { socket, unmount } = await mountAndOpen({
      enabled: true,
      currentUserId: USER_A,
      onNewMessage,
    })
    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ sender_id: USER_B }),
      })
    })
    expect(onNewMessage).toHaveBeenCalledTimes(1)
    expect(onNewMessage).toHaveBeenCalledWith(expect.objectContaining({ id: MSG_ID }), CHAT_ID)
    unmount()
  })

  it("self-echo guard: skips onNewMessage for the current user's own message", async () => {
    const onNewMessage = vi.fn()
    const { socket, unmount } = await mountAndOpen({
      enabled: true,
      currentUserId: USER_A,
      onNewMessage,
    })
    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ sender_id: USER_A }),
      })
    })
    expect(onNewMessage).not.toHaveBeenCalled()
    unmount()
  })

  it("calls onTyping for a typing frame", async () => {
    const onTyping = vi.fn()
    const { socket, unmount } = await mountAndOpen({
      enabled: true,
      currentUserId: USER_A,
      onTyping,
    })
    act(() => {
      socket.receive({ type: "typing", chat_id: CHAT_ID, user_id: USER_B, user_name: "Bob" })
    })
    expect(onTyping).toHaveBeenCalledWith(CHAT_ID, USER_B, "Bob")
    unmount()
  })

  it("calls onRead + flips read_status in the cache for a read frame from the other user", async () => {
    const onRead = vi.fn()
    const queryClient = new QueryClient()
    queryClient.setQueryData(["messages", CHAT_ID], makeList([makeMessage({ sender_id: USER_A })]))
    const { socket, unmount } = await mountAndOpen(
      { enabled: true, currentUserId: USER_A, onRead },
      queryClient
    )
    act(() => {
      socket.receive({
        type: "read",
        chat_id: CHAT_ID,
        user_id: USER_B,
        read_at: "2026-01-15T11:00:00Z",
      })
    })
    expect(onRead).toHaveBeenCalledWith(CHAT_ID, USER_B, "2026-01-15T11:00:00Z")
    const cached = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(cached?.items[0]?.read_status).toBe(true)
    unmount()
  })

  it("self-echo guard: skips onRead for the current user's own read frame", async () => {
    const onRead = vi.fn()
    const { socket, unmount } = await mountAndOpen({ enabled: true, currentUserId: USER_A, onRead })
    act(() => {
      socket.receive({ type: "read", chat_id: CHAT_ID, user_id: USER_A, read_at: null })
    })
    expect(onRead).not.toHaveBeenCalled()
    unmount()
  })

  it("calls onOnlineStatus for an online frame (true + false)", async () => {
    const onOnlineStatus = vi.fn()
    const { socket, unmount } = await mountAndOpen({ enabled: true, onOnlineStatus })
    act(() => socket.receive({ type: "online", user_id: USER_B, status: true }))
    act(() => socket.receive({ type: "online", user_id: USER_B, status: false }))
    expect(onOnlineStatus).toHaveBeenNthCalledWith(1, USER_B, true)
    expect(onOnlineStatus).toHaveBeenNthCalledWith(2, USER_B, false)
    unmount()
  })

  it("applies a message_edited frame to the cache", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(
      ["messages", CHAT_ID],
      makeList([
        makeMessage({ content: "old" }),
        makeMessage({ id: "55555555-5555-4555-8555-555555555555", content: "untouched" }),
      ])
    )
    const { socket, unmount } = await mountAndOpen({ enabled: true }, queryClient)
    act(() => {
      socket.receive({
        type: "message_edited",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        content: "edited!",
        edited_at: "2026-01-15T12:00:00Z",
      })
    })
    const cached = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(cached?.items[0]?.content).toBe("edited!")
    expect(cached?.items[1]?.content).toBe("untouched")
    unmount()
  })

  it("applies a message_deleted frame to the cache (tombstone)", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(
      ["messages", CHAT_ID],
      makeList([
        makeMessage({ content: "doomed" }),
        makeMessage({ id: "55555555-5555-4555-8555-555555555555", content: "untouched" }),
      ])
    )
    const { socket, unmount } = await mountAndOpen({ enabled: true }, queryClient)
    act(() => {
      socket.receive({
        type: "message_deleted",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        deleted_at: "2026-01-15T12:30:00Z",
      })
    })
    const cached = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(cached?.items[0]?.content).toBe("")
    expect(cached?.items[0]?.deleted_at).toBe("2026-01-15T12:30:00Z")
    expect(cached?.items[1]?.content).toBe("untouched")
    unmount()
  })

  it("applies a reaction_changed frame to the cache", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(["messages", CHAT_ID], makeList([makeMessage({ reactions: [] })]))
    const { socket, unmount } = await mountAndOpen(
      { enabled: true, currentUserId: USER_A },
      queryClient
    )
    act(() => {
      socket.receive({
        type: "reaction_changed",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        user_id: USER_B,
        emoji: "👍",
        action: "added",
      })
    })
    const cached = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(cached?.items[0]?.reactions?.[0]).toMatchObject({ emoji: "👍", count: 1 })
    act(() => {
      socket.receive({
        type: "reaction_changed",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        user_id: USER_A,
        emoji: "👍",
        action: "added",
      })
    })
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])?.items[0]
        ?.reactions?.[0]?.count
    ).toBe(1)
    unmount()
  })

  it("does not throw on error / pong / rate_limit_exceeded frames", async () => {
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    expect(() => {
      act(() => socket.receive({ type: "error", code: "message_too_large", detail: "too big" }))
      act(() => socket.receive({ type: "pong" }))
      act(() => socket.receive({ type: "rate_limit_exceeded" }))
    }).not.toThrow()
    unmount()
  })

  it("ignores an invalid (off-schema) frame without throwing", async () => {
    const onNewMessage = vi.fn()
    const { socket, unmount } = await mountAndOpen({ enabled: true, onNewMessage })
    expect(() => {
      act(() => socket.receive({ type: "new_message", chat_id: "not-a-uuid", message: {} }))
    }).not.toThrow()
    expect(onNewMessage).not.toHaveBeenCalled()
    unmount()
  })

  it("reconnects with a new socket after a non-clean close", async () => {
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    expect(MockWebSocket.instances.length).toBe(1)
    act(() => socket.close(1006))
    // calculateReconnectDelay(0) is 0–1000ms; a fresh socket is created within ~1s.
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2), {
      timeout: 3000,
    })
    unmount()
  })
})

describe("useChatWebSocket frame-cache helpers", () => {
  it("applyReadFrame: undefined stays undefined", () => {
    expect(applyReadFrame(undefined, { user_id: USER_B, read_at: "x" })).toBeUndefined()
  })

  it("applyReadFrame: flips read_status for messages NOT sent by the reader", () => {
    const list = makeList([
      makeMessage({ id: MSG_ID, sender_id: USER_A, read_status: false }),
      makeMessage({
        id: "55555555-5555-4555-8555-555555555555",
        sender_id: USER_B,
        read_status: false,
      }),
    ])
    const out = applyReadFrame(list, { user_id: USER_B, read_at: "2026-01-15T11:00:00Z" })
    expect(out?.items[0]?.read_status).toBe(true) // sender USER_A, flipped
    expect(out?.items[0]?.read_at).toBe("2026-01-15T11:00:00Z")
    expect(out?.items[1]?.read_status).toBe(false) // reader's own, untouched
  })

  it("applyMessageEditedFrame: replaces content + edited_at on the matched id only", () => {
    const list = makeList([
      makeMessage({ id: MSG_ID, content: "old" }),
      makeMessage({ id: "55555555-5555-4555-8555-555555555555", content: "untouched" }),
    ])
    const out = applyMessageEditedFrame(list, {
      message_id: MSG_ID,
      content: "new",
      edited_at: "t",
    })
    expect(out?.items[0]?.content).toBe("new")
    expect(out?.items[0]?.edited_at).toBe("t")
    expect(out?.items[1]?.content).toBe("untouched")
    expect(
      applyMessageEditedFrame(undefined, { message_id: MSG_ID, content: "n", edited_at: "t" })
    ).toBeUndefined()
  })

  it("applyMessageDeletedFrame: stamps deleted_at + clears content/attachments", () => {
    const list = makeList([
      makeMessage({ id: MSG_ID, content: "x", attachments: [{ id: "a" }] as never }),
    ])
    const out = applyMessageDeletedFrame(list, { message_id: MSG_ID, deleted_at: "d" })
    expect(out?.items[0]?.content).toBe("")
    expect(out?.items[0]?.deleted_at).toBe("d")
    expect(out?.items[0]?.attachments).toEqual([])
    expect(
      applyMessageDeletedFrame(undefined, { message_id: MSG_ID, deleted_at: "d" })
    ).toBeUndefined()
  })

  it("applyReactionChangedFrame: added pushes new, added increments existing", () => {
    const base = makeList([makeMessage({ id: MSG_ID, reactions: undefined as never })])
    const added = applyReactionChangedFrame(base, {
      message_id: MSG_ID,
      emoji: "👍",
      action: "added",
    })
    expect(added?.items[0]?.reactions?.[0]).toMatchObject({ emoji: "👍", count: 1 })
    const more = applyReactionChangedFrame(added, {
      message_id: MSG_ID,
      emoji: "👍",
      action: "added",
    })
    expect(more?.items[0]?.reactions?.[0]?.count).toBe(2)
  })

  it("applyReactionChangedFrame: removed decrements, then splices at zero", () => {
    const start = makeList([
      makeMessage({
        id: MSG_ID,
        reactions: [{ emoji: "👍", count: 2, reacted_by_me: false }] as never,
      }),
    ])
    const dec = applyReactionChangedFrame(start, {
      message_id: MSG_ID,
      emoji: "👍",
      action: "removed",
    })
    expect(dec?.items[0]?.reactions?.[0]?.count).toBe(1)
    const gone = applyReactionChangedFrame(dec, {
      message_id: MSG_ID,
      emoji: "👍",
      action: "removed",
    })
    expect(gone?.items[0]?.reactions).toEqual([])
    expect(
      applyReactionChangedFrame(undefined, { message_id: MSG_ID, emoji: "x", action: "added" })
    ).toBeUndefined()
    expect(
      applyReactionChangedFrame(makeList([makeMessage({ reactions: [] })]), {
        message_id: MSG_ID,
        emoji: "missing",
        action: "removed",
      })?.items[0]?.reactions
    ).toEqual([])
  })

  it("applyReactionChangedFrame: leaves non-matching messages unchanged", () => {
    const list = makeList([
      makeMessage({ id: "66666666-6666-4666-8666-666666666666", reactions: [] }),
    ])
    const out = applyReactionChangedFrame(list, {
      message_id: MSG_ID,
      emoji: "👍",
      action: "added",
    })
    expect(out?.items[0]?.reactions).toEqual([])
  })
})

describe("useChatWebSocket exponential backoffs and ticket exchange failures", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    server.resetHandlers()
    vi.unstubAllGlobals()
  })

  it("calculateReconnectDelay scales exponentially with attempt number", () => {
    const mathRandomSpy = vi.spyOn(Math, "random").mockReturnValue(0.9)

    // attempt 0: base = 1000 * 2^0 = 1000. delay = Math.floor(0.9 * 1000) = 900
    expect(calculateReconnectDelay(0)).toBe(900)

    // attempt 2: base = 1000 * 2^2 = 4000. delay = Math.floor(0.9 * 4000) = 3600
    expect(calculateReconnectDelay(2)).toBe(3600)

    // attempt 10: base = 1000 * 2^10 = 1024000 -> maxed to 30000. delay = Math.floor(0.9 * 30000) = 27000
    expect(calculateReconnectDelay(10)).toBe(27000)

    mathRandomSpy.mockRestore()
  })

  it("schedules reconnect when ticket exchange fails with HTTP 500", async () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0)
    let attempts = 0
    server.use(
      http.post("*/ws/ticket", () => {
        attempts += 1
        return new HttpResponse(null, { status: 500 })
      })
    )

    // Mount hook with enabled: true
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })

    // Wait and verify that it did not open a WebSocket because of the failure,
    // but reconnect is scheduled. Since it fails to fetch a ticket, MockWebSocket.instances.length remains 0.
    await waitFor(() => expect(attempts).toBeGreaterThanOrEqual(2))
    expect(MockWebSocket.instances.length).toBe(0)

    rendered.unmount()
    random.mockRestore()
  })

  it("aborts a ticket request after the five-second deadline", () => {
    vi.useFakeTimers()
    let signal: { readonly aborted: boolean } | undefined
    const post = vi.spyOn(api, "post").mockImplementation(((_url, _data, config) => {
      signal = config?.signal
      return new Promise(() => {})
    }) as typeof api.post)

    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })

    expect(signal?.aborted).toBe(false)
    act(() => vi.advanceTimersByTime(5_000))
    expect(signal?.aborted).toBe(true)

    rendered.unmount()
    post.mockRestore()
    vi.useRealTimers()
  })

  it.each([401, 403])(
    "calls the auth-error hook and does not reconnect for HTTP %s",
    async (status) => {
      server.use(
        http.post("*/ws/ticket", () => {
          return new HttpResponse(null, { status })
        })
      )
      const onAuthError = vi.fn()
      const rendered = renderHook(() => useChatWebSocket({ enabled: true, onAuthError }), {
        wrapper: ({ children }) => (
          <QueryClientProvider client={new QueryClient()}>
            <WebSocketProvider>{children}</WebSocketProvider>
          </QueryClientProvider>
        ),
      })
      await waitFor(() => expect(onAuthError).toHaveBeenCalledTimes(1))
      expect(MockWebSocket.instances).toHaveLength(0)
      rendered.unmount()
    }
  )

  it("stops reconnecting after reaching MAX_RECONNECT_ATTEMPTS", async () => {
    const mathRandomSpy = vi.spyOn(Math, "random").mockReturnValue(0)

    const { unmount } = await mountAndOpen({ enabled: true })
    expect(MockWebSocket.instances.length).toBe(1)

    // Trigger close and reconnect 10 times to reach MAX_RECONNECT_ATTEMPTS without opening (simulates persistent failure)
    for (let i = 0; i < 10; i++) {
      const currentSocket = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
      act(() => {
        currentSocket.close(1006)
      })
      await waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(i + 2)
      })
      // Sleep 20ms to allow event loop & handles to drain on Windows
      await new Promise((resolve) => setTimeout(resolve, 20))
    }

    // Now at 11 sockets. The next close should NOT trigger another reconnect attempt.
    const lastSocket = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
    act(() => {
      lastSocket.close(1006)
    })

    // Wait some time and verify no new socket is created
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(MockWebSocket.instances.length).toBe(11)

    unmount()
    mathRandomSpy.mockRestore()
  })
})

describe("useChatWebSocket outgoing controls and lifecycle edges", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    mocks.getDatabase.mockResolvedValue({
      messages: { upsert: vi.fn().mockResolvedValue(undefined) },
    })
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it("throttles REST typing and swallows transient failures", async () => {
    const sendTypingSpy = vi.spyOn(chatApi, "sendTyping").mockResolvedValue(undefined)
    const { result, unmount } = renderHook(() => useChatWebSocket({ enabled: false }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })

    act(() => {
      result.current.sendTyping(CHAT_ID)
      result.current.sendTyping(CHAT_ID)
    })
    await waitFor(() => expect(sendTypingSpy).toHaveBeenCalledTimes(1))

    sendTypingSpy.mockRejectedValueOnce(new Error("offline"))
    await act(async () => {
      result.current.sendTyping("55555555-5555-4555-8555-555555555555")
      await Promise.resolve()
    })
    expect(sendTypingSpy).toHaveBeenCalledTimes(2)

    unmount()
    sendTypingSpy.mockRestore()
  })

  it("does not expose a read sender because REST owns receipts", async () => {
    const { socket, result, unmount } = await mountAndOpen({ enabled: true })

    expect(result.current).not.toHaveProperty("sendRead")
    expect(socket.sentMessages).not.toContain(expect.stringContaining('"type":"read"'))
    unmount()
  })

  it("queues a room join before open, rejoins on open, and leaves safely", async () => {
    const queryClient = new QueryClient()
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1))
    const socket = MockWebSocket.instances[0]!

    act(() => rendered.result.current.sendLeave("55555555-5555-4555-8555-555555555555"))
    expect(socket.sentMessages).toEqual([])
    act(() => rendered.result.current.sendJoin(CHAT_ID))
    expect(socket.sentMessages).toEqual([])
    act(() => socket.open())
    expect(socket.sentMessages).toContain(`{"type":"join","room":"${CHAT_ID}"}`)

    act(() => rendered.result.current.sendLeave("55555555-5555-4555-8555-555555555555"))
    expect(socket.sentMessages).toContain(
      '{"type":"leave","room":"55555555-5555-4555-8555-555555555555"}'
    )
    act(() => rendered.result.current.sendLeave(CHAT_ID))
    expect(socket.sentMessages).toContain(`{"type":"leave","room":"${CHAT_ID}"}`)
    rendered.unmount()
  })

  it("uses the secure websocket scheme on HTTPS pages", async () => {
    const originalWindow = window
    const secureLocation = new Proxy(originalWindow.location, {
      get(target, property, receiver) {
        if (property === "protocol") return "https:"
        return Reflect.get(target, property, receiver)
      },
    })
    vi.stubGlobal(
      "window",
      new Proxy(originalWindow, {
        get(target, property) {
          if (property === "location") return secureLocation
          return Reflect.get(target, property, target)
        },
      })
    )

    const { socket, unmount } = await mountAndOpen({ enabled: true })
    expect(socket.url).toMatch(/^wss:\/\//)
    unmount()
  })

  it("swallows join/leave races without emitting an invalid application heartbeat", async () => {
    const queryClient = new QueryClient()
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1))
    const socket = MockWebSocket.instances[0]!
    act(() => rendered.result.current.sendJoin(CHAT_ID))
    vi.useFakeTimers()
    socket.send = () => {
      throw new Error("socket closed")
    }
    expect(() => act(() => socket.open())).not.toThrow()
    expect(() => act(() => rendered.result.current.sendLeave(CHAT_ID))).not.toThrow()

    socket.send = (data: string) => socket.sentMessages.push(data)
    act(() => socket.open())
    act(() => vi.advanceTimersByTime(30_000))
    // ws-hub owns the heartbeat with WebSocket control frames.  The browser
    // must not send an application JSON ping, which is rejected by the hub's
    // client-command allowlist.
    expect(socket.sentMessages).not.toContain('{"type":"ping"}')
    const sentCount = socket.sentMessages.length
    socket.readyState = MockWebSocket.CLOSING
    act(() => vi.advanceTimersByTime(30_000))
    expect(socket.sentMessages).toHaveLength(sentCount)
    rendered.unmount()
  })

  it("does not connect when disabled reconnect is requested explicitly", () => {
    const { result, unmount } = renderHook(() => useChatWebSocket({ enabled: false }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })
    act(() => result.current.reconnect())
    expect(MockWebSocket.instances).toHaveLength(0)
    unmount()
  })

  it("swallows direct join races and reports socket errors", async () => {
    const { socket, result, unmount } = await mountAndOpen({ enabled: true })
    socket.send = () => {
      throw new Error("socket closed")
    }
    expect(() => {
      act(() => result.current.sendJoin("55555555-5555-4555-8555-555555555555"))
      socket.onerror?.(new Event("error"))
    }).not.toThrow()
    unmount()
  })

  it("swallows a WebSocket constructor failure after ticket exchange", async () => {
    class ThrowingWebSocket {
      constructor() {
        throw new Error("WebSocket unavailable")
      }
    }
    vi.stubGlobal("WebSocket", ThrowingWebSocket)
    const rendered = renderHook(() => useChatWebSocket({ enabled: true }), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          <WebSocketProvider>{children}</WebSocketProvider>
        </QueryClientProvider>
      ),
    })
    await new Promise((resolve) => setTimeout(resolve, 50))
    rendered.unmount()
  })

  it("does not open a second socket when reconnect is requested while open", async () => {
    const { result, unmount } = await mountAndOpen({ enabled: true })
    act(() => result.current.reconnect())
    await new Promise((resolve) => setTimeout(resolve, 25))
    expect(MockWebSocket.instances).toHaveLength(1)
    unmount()
  })

  it("logs and drops a frame when validation throws", async () => {
    const parseSpy = vi.spyOn(wsMessageSchema, "parseWsMessage").mockImplementation(() => {
      throw new Error("validator failure")
    })
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    expect(() => {
      act(() => socket.receive({ type: "pong" }))
    }).not.toThrow()
    parseSpy.mockRestore()
    unmount()
  })

  it.each([1000, 4001, 4003])("does not reconnect after terminal close code %s", async (code) => {
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    expect(MockWebSocket.instances).toHaveLength(1)
    act(() => socket.close(code))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(MockWebSocket.instances).toHaveLength(1)
    unmount()
  })

  it("expires typing entries and rejects a per-chat overflow", async () => {
    const onTyping = vi.fn()
    const { socket, result, unmount } = await mountAndOpen({ enabled: true, onTyping })

    vi.useFakeTimers()
    const otherChat = "77777777-7777-4777-8777-777777777777"
    act(() =>
      socket.receive({
        type: "typing",
        chat_id: otherChat,
        user_id: "88888888-8888-4888-8888-888888888888",
        user_name: "Other chat",
      })
    )
    expect(result.current.getTypingUsersForChat(CHAT_ID)).toEqual([])
    act(() =>
      socket.receive({
        type: "typing",
        chat_id: CHAT_ID,
        user_id: "00000000-0000-4000-8000-000000000001",
        user_name: "First",
      })
    )
    act(() =>
      socket.receive({
        type: "typing",
        chat_id: CHAT_ID,
        user_id: "00000000-0000-4000-8000-000000000001",
        user_name: "Updated",
      })
    )
    expect(result.current.getTypingUsersForChat(CHAT_ID)[0]?.userName).toBe("Updated")
    for (let index = 0; index < 21; index += 1) {
      const userId = `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`
      act(() =>
        socket.receive({
          type: "typing",
          chat_id: CHAT_ID,
          user_id: userId,
          user_name: `User ${index}`,
        })
      )
    }
    expect(result.current.getTypingUsersForChat(CHAT_ID)).toHaveLength(20)

    act(() => vi.advanceTimersByTime(3_000))
    expect(result.current.getTypingUsersForChat(CHAT_ID)).toEqual([])
    expect(onTyping).toHaveBeenCalledTimes(24)
    unmount()
  })

  it("handles a typing timeout that races with cleanup", async () => {
    const { socket, unmount } = await mountAndOpen({ enabled: true })

    vi.useFakeTimers()
    act(() =>
      socket.receive({
        type: "typing",
        chat_id: CHAT_ID,
        user_id: "00000000-0000-4000-8000-000000000099",
        user_name: "Racer",
      })
    )

    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout").mockImplementation(() => {})
    act(() => socket.close(1000))
    act(() => vi.advanceTimersByTime(3_000))
    clearTimeoutSpy.mockRestore()
    unmount()
  })

  it("persists incoming messages, trims the cache, and ignores duplicates", async () => {
    const upsert = vi.fn().mockResolvedValue(undefined)
    mocks.getDatabase.mockResolvedValue({ messages: { upsert } })
    const queryClient = new QueryClient()
    const initial = Array.from({ length: 200 }, (_, index) =>
      makeMessage({
        id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
      })
    )
    queryClient.setQueryData(["messages", CHAT_ID], {
      ...makeList(initial),
      has_more: true,
      next_cursor: "recoverable-older-edge",
    })
    queryClient.setQueryData(["chats"], {
      items: [
        { id: CHAT_ID, unread_count: 2 },
        { id: "55555555-5555-4555-8555-555555555555", unread_count: 4 },
      ],
    })
    const { socket, unmount } = await mountAndOpen({ enabled: true }, queryClient)

    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ id: MSG_ID, sender_id: USER_B }),
      })
    })
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1))
    const afterAppend = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(afterAppend?.items).toHaveLength(200)
    expect(afterAppend?.items.at(-1)?.id).toBe(MSG_ID)
    expect(
      queryClient.getQueryData<{ items: Array<{ unread_count: number }> }>(["chats"])?.items[0]
        ?.unread_count
    ).toBe(3)

    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ id: MSG_ID, sender_id: USER_B }),
      })
    })
    const afterDuplicate = queryClient.getQueryData<MessagesListResponse>(["messages", CHAT_ID])
    expect(afterDuplicate?.items).toHaveLength(200)
    expect(afterDuplicate?.items.at(-1)?.id).toBe(MSG_ID)
    unmount()
  })

  it("swallows RxDB open and upsert failures from an incoming message", async () => {
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    mocks.getDatabase.mockRejectedValueOnce(new Error("IndexedDB unavailable"))
    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ sender_id: USER_B }),
      })
    })
    await Promise.resolve()

    const upsert = vi.fn().mockRejectedValue(new Error("write failed"))
    mocks.getDatabase.mockResolvedValueOnce({ messages: { upsert } })
    act(() => {
      socket.receive({
        type: "new_message",
        chat_id: CHAT_ID,
        message: makeMessage({ id: "55555555-5555-4555-8555-555555555555", sender_id: USER_B }),
      })
    })
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1))
    unmount()
  })

  it("applies defensive RxDB defaults to a malformed validated payload", async () => {
    const upsert = vi.fn().mockResolvedValue(undefined)
    mocks.getDatabase.mockResolvedValue({ messages: { upsert } })
    const parseSpy = vi.spyOn(wsMessageSchema, "parseWsMessage").mockReturnValueOnce({
      type: "new_message",
      chat_id: CHAT_ID,
      message: {
        id: MSG_ID,
        chat_id: CHAT_ID,
        sender_id: USER_B,
        content: "",
        created_at: "",
        read_status: undefined,
        read_at: undefined,
        edited_at: undefined,
        deleted_at: undefined,
        attachments: undefined,
      },
    } as never)
    const { socket, unmount } = await mountAndOpen({ enabled: true })
    act(() => socket.receive({ type: "new_message" }))
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1))
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        content: "",
        read_status: false,
        read_at: null,
        edited_at: null,
        deleted_at: null,
        attachments: [],
        reactions: [],
      })
    )
    parseSpy.mockRestore()
    unmount()
  })
})
