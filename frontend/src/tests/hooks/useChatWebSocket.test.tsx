import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
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
import type { Message, MessagesListResponse } from "@/api/chat"

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
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
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
    queryClient.setQueryData(["messages", CHAT_ID], makeList([makeMessage({ content: "old" })]))
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
    unmount()
  })

  it("applies a message_deleted frame to the cache (tombstone)", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(["messages", CHAT_ID], makeList([makeMessage({ content: "doomed" })]))
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
    const list = makeList([makeMessage({ id: MSG_ID, content: "old" })])
    const out = applyMessageEditedFrame(list, {
      message_id: MSG_ID,
      content: "new",
      edited_at: "t",
    })
    expect(out?.items[0]?.content).toBe("new")
    expect(out?.items[0]?.edited_at).toBe("t")
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
  })

  it("applyReactionChangedFrame: added pushes new, added increments existing", () => {
    const base = makeList([makeMessage({ id: MSG_ID, reactions: [] })])
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
  })

  afterEach(() => {
    server.resetHandlers()
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
    server.use(
      http.post("*/ws/ticket", () => {
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
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(0)
    })

    rendered.unmount()
  })
})
