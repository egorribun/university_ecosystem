import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode, useContext, useLayoutEffect, type ReactNode } from "react"
import { flushSync } from "react-dom"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Transport, connectivity and cache-reconciliation contracts of
 * useChatWebSocket, driven with fake timers and a scripted WebSocket.
 */

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logError: vi.fn(),
  parseWsMessage: vi.fn(),
  dbUpsert: vi.fn(),
  dbLoad: vi.fn(),
}))

class ScriptedWebSocket {
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static instances: ScriptedWebSocket[] = []

  readonly url: string
  readyState = ScriptedWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  autoAcknowledgeHeartbeats = true
  emitCloseEventOnClose = true
  closeEventCount = 0

  constructor(url: string) {
    this.url = url
    ScriptedWebSocket.instances.push(this)
  }

  send = vi.fn((payload: string) => {
    const frame = JSON.parse(payload) as { type?: unknown; nonce?: unknown }
    if (
      this.autoAcknowledgeHeartbeats &&
      frame.type === "heartbeat_ping" &&
      typeof frame.nonce === "string"
    ) {
      const pong = { type: "heartbeat_pong", nonce: frame.nonce }
      mocks.parseWsMessage.mockReturnValueOnce(pong)
      this.onmessage?.({ data: JSON.stringify(pong) } as MessageEvent)
    }
  })

  close = vi.fn((code = 1000, reason?: string) => {
    this.readyState = ScriptedWebSocket.CLOSED
    if (this.emitCloseEventOnClose) {
      this.closeEventCount += 1
      this.onclose?.({ code, reason } as CloseEvent)
    }
  })

  receive(frame: unknown) {
    mocks.parseWsMessage.mockReturnValueOnce(frame)
    this.onmessage?.({ data: "frame" } as MessageEvent)
  }
}

vi.mock("@/api/client", () => ({ default: { post: mocks.apiPost } }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@/api/schemas/wsMessage", () => ({ parseWsMessage: mocks.parseWsMessage }))
vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: mocks.dbLoad,
}))

import {
  chatApi,
  type ChatsListResponse,
  type Message,
  type MessagesListResponse,
} from "@/api/chat"
import {
  applyReactionChangedFrame,
  applyMessageDeletedFrame,
  applyMessageEditedFrame,
  useChatWebSocket,
  WebSocketProvider,
  WebSocketStoreContext,
  type UseChatWebSocketOptions,
} from "../useChatWebSocket"
import { peekReplayCheckpoint, writeReplayCheckpoint } from "../chatReplayCheckpoints"

const CHAT = "chat-a"
const OTHER_CHAT = "chat-b"
const TICKET = { data: { ticket: "ticket-1", expires_in: 15 } }

const flush = () => act(() => vi.advanceTimersByTimeAsync(0))
const sockets = () => ScriptedWebSocket.instances
const lastSocket = () => sockets().at(-1)!
const sentHeartbeats = (socket: ScriptedWebSocket) =>
  socket.send.mock.calls
    .map(([payload]) => JSON.parse(payload) as { type?: string; nonce?: string })
    .filter((frame) => frame.type === "heartbeat_ping")
const sentJoins = (socket: ScriptedWebSocket) =>
  socket.send.mock.calls
    .map(
      ([payload]) => JSON.parse(payload) as { type?: string; room?: string; resume_token?: string }
    )
    .filter((frame) => frame.type === "join")

function expectTicketSocket(ticket: string) {
  expect(sockets()).toHaveLength(1)
  const socketUrl = new URL(lastSocket().url)
  expect(socketUrl.protocol).toBe(window.location.protocol === "https:" ? "wss:" : "ws:")
  expect(socketUrl.host).toBe(window.location.host)
  expect(socketUrl.pathname).toBe("/ws/chat")
  expect([...socketUrl.searchParams]).toStrictEqual([["ticket", ticket]])
  expect(socketUrl.username).toBe("")
  expect(socketUrl.password).toBe("")
  expect(socketUrl.hash).toBe("")
}

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: "m-1",
    chat_id: CHAT,
    sender_id: "peer",
    content: "hello",
    created_at: "2026-08-25T12:00:00.000Z",
    read_status: false,
    attachments: [],
    ...overrides,
  }
}

function setup(initialProps: UseChatWebSocketOptions = {}, strict = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")
  let renders = 0
  const providers = (children: ReactNode) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  const wrapper = ({ children }: { children: ReactNode }) =>
    strict ? <StrictMode>{providers(children)}</StrictMode> : providers(children)
  const hook = renderHook(
    (props: UseChatWebSocketOptions) => {
      renders += 1
      return useChatWebSocket(props)
    },
    { wrapper, initialProps: { enabled: true, ...initialProps } }
  )
  return { ...hook, queryClient, invalidateQueries, renders: () => renders }
}

async function connected(initialProps: UseChatWebSocketOptions = {}) {
  const session = setup(initialProps)
  await flush()
  const socket = lastSocket()
  act(() => socket.onopen?.())
  return { ...session, socket }
}

beforeEach(() => {
  vi.useFakeTimers({ now: Date.UTC(2026, 7, 25, 12) })
  vi.clearAllMocks()
  window.sessionStorage.clear()
  ScriptedWebSocket.instances = []
  vi.stubGlobal("WebSocket", ScriptedWebSocket)
  vi.spyOn(Math, "random").mockReturnValue(0)
  mocks.apiPost.mockReset().mockResolvedValue(TICKET)
  mocks.parseWsMessage.mockReset().mockReturnValue(null)
  mocks.dbUpsert.mockResolvedValue(undefined)
  mocks.dbLoad.mockReset().mockResolvedValue({ messages: { upsert: mocks.dbUpsert } })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true })
})

describe("WebSocketProvider store", () => {
  it("provides one store that notifies subscribers only on real changes", () => {
    const { result, rerender } = renderHook(() => useContext(WebSocketStoreContext), {
      wrapper: WebSocketProvider,
    })
    const store = result.current!
    rerender()
    expect(result.current).toBe(store)
    expect(store.getSnapshot()).toBe(false)

    const listener = vi.fn()
    const unsubscribe = store.subscribe(listener)
    store.setConnected(true)
    store.setConnected(true)
    expect(store.getSnapshot()).toBe(true)
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    store.setConnected(false)
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe("ticket exchange", () => {
  it("requests a ticket outside the API prefix and opens a same-host socket", async () => {
    setup()
    await flush()

    expect(mocks.apiPost).toHaveBeenCalledExactlyOnceWith("/ws/ticket", undefined, {
      signal: expect.any(AbortSignal),
      baseURL: "",
    })
    expectTicketSocket("ticket-1")
  })

  it("retries transient ticket failures with backoff until the attempt limit", async () => {
    const networkError = new Error("network down")
    mocks.apiPost.mockRejectedValueOnce(networkError)
    mocks.apiPost.mockRejectedValue({ response: { status: 503 } })

    setup()
    for (let step = 0; step < 30; step += 1) await act(() => vi.advanceTimersByTimeAsync(100))

    expect(mocks.apiPost).toHaveBeenCalledTimes(11)
    expect(mocks.logError).toHaveBeenCalledWith(
      "[WebSocket] Ticket fetch failed; will retry.",
      networkError
    )
    expect(mocks.logError).toHaveBeenLastCalledWith("[WebSocket] Ticket retry limit reached.", {
      attempts: 10,
    })
    expect(sockets()).toHaveLength(0)
  })

  it("stops on an expired session even without an auth-error handler", async () => {
    mocks.apiPost.mockRejectedValue({ response: { status: 401 } })

    setup()
    for (let step = 0; step < 5; step += 1) await flush()

    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
    expect(mocks.logError).toHaveBeenCalledExactlyOnceWith(
      "[WebSocket] Session invalid (status %s); aborting connection.",
      401
    )
  })

  it("stays silent when a disconnect aborts the ticket request", async () => {
    let rejectTicket: (reason: unknown) => void = () => undefined
    mocks.apiPost.mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectTicket = reject
      })
    )
    const { result } = setup()
    await flush()

    act(() => result.current.disconnect())
    rejectTicket({ response: { status: 503 } })
    for (let step = 0; step < 5; step += 1) await flush()

    expect(mocks.logError).not.toHaveBeenCalled()
    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
    expect(sockets()).toHaveLength(0)
  })

  it("retries a ticket deadline when axios rejects its aborted request", async () => {
    mocks.apiPost.mockImplementationOnce(
      (_url, _body, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))
        })
    )
    setup({ currentUserId: "user-a" })
    await act(() => vi.advanceTimersByTimeAsync(5_000))
    await act(() => vi.advanceTimersByTimeAsync(1_000))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expectTicketSocket("ticket-1")
  })

  it("does not connect when the ticket request timed out before it resolved", async () => {
    let resolveTicket: (value: unknown) => void = () => undefined
    mocks.apiPost.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveTicket = resolve
      })
    )
    setup()
    await flush()

    await act(() => vi.advanceTimersByTimeAsync(5_000))
    resolveTicket(TICKET)
    await flush()

    expect(sockets()).toHaveLength(0)
  })
})

describe("connection lifecycle", () => {
  it("bounds retries when every short-lived reconnect opens before failing", async () => {
    setup()
    await flush()

    for (let attempt = 0; attempt < 11; attempt += 1) {
      const socket = sockets()[attempt]!
      act(() => socket.onopen?.())
      act(() => socket.close(1006))
      await flush()
    }

    expect(sockets()).toHaveLength(11)
    expect(mocks.logError).toHaveBeenLastCalledWith(
      "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
      { attempts: 10, lastCode: 1006 }
    )
  })

  it("restores the retry budget only after a connection stays open for the stability window", async () => {
    setup()
    await flush()

    for (let attempt = 0; attempt < 10; attempt += 1) {
      const socket = sockets()[attempt]!
      act(() => socket.onopen?.())
      act(() => socket.close(1006))
      await flush()
    }

    const stableSocket = sockets()[10]!
    act(() => stableSocket.onopen?.())
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    act(() => stableSocket.close(1006))
    await flush()

    expect(sockets()).toHaveLength(12)
    expect(mocks.logError).not.toHaveBeenCalledWith(
      "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
      expect.anything()
    )
  })

  it("does not publish a message after a cache subscriber synchronously changes accounts", async () => {
    const onNewMessageA = vi.fn()
    const onNewMessageB = vi.fn()
    const session = await connected({ currentUserId: "user-a", onNewMessage: onNewMessageA })
    session.queryClient.setQueryData<ChatsListResponse>(["chats"], {
      items: [],
      has_more: false,
      next_cursor: null,
    })
    const unsubscribe = session.queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type === "updated" &&
        event.query.queryKey[0] === "chats" &&
        event.action.type === "invalidate"
      ) {
        unsubscribe()
        flushSync(() =>
          session.rerender({
            enabled: true,
            currentUserId: "user-b",
            onNewMessage: onNewMessageB,
          })
        )
      }
    })

    act(() =>
      session.socket.receive({
        type: "new_message",
        chat_id: CHAT,
        message: message({ id: "accepted-before-switch" }),
        stream_seq: 5,
        resume_token: "checkpoint-a",
      })
    )
    await flush()
    unsubscribe()

    expect(session.socket.close).toHaveBeenCalledOnce()
    expect(sockets()).toHaveLength(2)
    expect(onNewMessageA).not.toHaveBeenCalled()
    expect(onNewMessageB).not.toHaveBeenCalled()
    expect(mocks.dbUpsert).not.toHaveBeenCalled()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-a")).toBeNull()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-b")).toBeNull()

    const incomingB = message({ id: "owned-b", chat_id: OTHER_CHAT })
    act(() => lastSocket().onopen?.())
    act(() =>
      lastSocket().receive({ type: "new_message", chat_id: OTHER_CHAT, message: incomingB })
    )
    expect(onNewMessageB).toHaveBeenCalledExactlyOnceWith(incomingB, OTHER_CHAT)
  })

  it.each(["account change", "same-account reconnect"])(
    "ignores a captured error callback after %s while reporting the owned socket's error",
    async (transition) => {
      const session = await connected({ currentUserId: "user-a" })
      const capturedError = session.socket.onerror!
      if (transition === "account change")
        session.rerender({ enabled: true, currentUserId: "user-b" })
      else {
        act(() => session.socket.close(1006))
        await act(() => vi.advanceTimersByTimeAsync(1_000))
      }
      await flush()
      expect(sockets()).toHaveLength(2)
      act(() => lastSocket().onopen?.())

      act(() => capturedError(new Event("error")))
      expect(mocks.logError).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)

      const ownedError = new Event("error")
      act(() => lastSocket().onerror?.(ownedError))
      expect(mocks.logError).toHaveBeenCalledExactlyOnceWith("[WebSocket] Error:", ownedError)
      expect(session.result.current.isConnected).toBe(true)
    }
  )

  it("queues the new account's room during commit without sending its token on the old socket", async () => {
    window.sessionStorage.setItem(
      "university.chat.replay.v2:user-b",
      JSON.stringify({
        entries: [[OTHER_CHAT, 7, "private-token-b"]],
      })
    )
    const client = new QueryClient()
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <WebSocketProvider>{children}</WebSocketProvider>
      </QueryClientProvider>
    )
    const session = renderHook(
      (props: UseChatWebSocketOptions) => {
        const hook = useChatWebSocket(props)
        const { sendJoin } = hook
        useLayoutEffect(() => {
          if (props.currentUserId === "user-b") sendJoin(OTHER_CHAT)
        }, [props.currentUserId, sendJoin])
        return hook
      },
      { wrapper, initialProps: { enabled: true, currentUserId: "user-a" } }
    )
    await flush()
    const oldSocket = lastSocket()
    act(() => oldSocket.onopen?.())

    session.rerender({ enabled: true, currentUserId: "user-b" })
    await flush()

    expect(oldSocket.send).not.toHaveBeenCalled()
    act(() => lastSocket().onopen?.())
    expect(lastSocket().send).toHaveBeenCalledExactlyOnceWith(
      JSON.stringify({
        type: "join",
        room: OTHER_CHAT,
        resume_token: "private-token-b",
      })
    )
  })

  it("does not commit an old checkpoint when the message callback switches accounts", async () => {
    const onNewMessage = vi.fn(() => {
      flushSync(() => session.rerender({ enabled: true, currentUserId: "user-b", onNewMessage }))
    })
    const session = await connected({ currentUserId: "user-a", onNewMessage })

    act(() =>
      session.socket.receive({
        type: "new_message",
        chat_id: CHAT,
        message: message(),
        stream_seq: 5,
        resume_token: "checkpoint-a",
      })
    )
    await flush()

    expect(onNewMessage).toHaveBeenCalledOnce()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-b")).toBeNull()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-a")).toBeNull()
  })

  it("does not deliver old presence to the new account's online callback after a synchronous switch", async () => {
    const onOnlineStatusA = vi.fn()
    const onOnlineStatusB = vi.fn()
    const onPresenceUpdateB = vi.fn()
    const onPresenceUpdateA = vi.fn(() => {
      flushSync(() =>
        session.rerender({
          enabled: true,
          currentUserId: "user-b",
          onPresenceUpdate: onPresenceUpdateB,
          onOnlineStatus: onOnlineStatusB,
        })
      )
    })
    const session = await connected({
      currentUserId: "user-a",
      onPresenceUpdate: onPresenceUpdateA,
      onOnlineStatus: onOnlineStatusA,
    })

    act(() =>
      session.socket.receive({
        type: "presence",
        user_id: "peer-a",
        active: true,
        last_seen: null,
      })
    )
    await flush()

    expect(onPresenceUpdateA).toHaveBeenCalledExactlyOnceWith("peer-a", true, null)
    expect(onOnlineStatusA).not.toHaveBeenCalled()
    expect(onPresenceUpdateB).not.toHaveBeenCalled()
    expect(onOnlineStatusB).not.toHaveBeenCalled()

    act(() => lastSocket().onopen?.())
    act(() =>
      lastSocket().receive({
        type: "presence",
        user_id: "peer-b",
        active: false,
        last_seen: "2026-08-25T12:00:00.000Z",
      })
    )
    expect(onPresenceUpdateB).toHaveBeenCalledExactlyOnceWith(
      "peer-b",
      false,
      "2026-08-25T12:00:00.000Z"
    )
    expect(onOnlineStatusB).toHaveBeenCalledExactlyOnceWith("peer-b", false)
  })

  it.each(["account change", "account round trip", "same-account reconnect"])(
    "guards deferred offline persistence across %s",
    async (transition) => {
      let resolveDatabase!: (value: { messages: { upsert: typeof mocks.dbUpsert } }) => void
      mocks.dbLoad.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveDatabase = resolve
        })
      )
      const session = await connected({ currentUserId: "user-a" })
      const incoming = message({ id: "accepted-a" })
      act(() => session.socket.receive({ type: "new_message", chat_id: CHAT, message: incoming }))
      expect(mocks.dbLoad).toHaveBeenCalledOnce()
      expect(mocks.dbUpsert).not.toHaveBeenCalled()

      if (transition !== "same-account reconnect")
        session.rerender({ enabled: true, currentUserId: "user-b" })
      else act(() => session.socket.close(1006))
      await flush()
      if (transition === "account round trip") {
        session.rerender({ enabled: true, currentUserId: "user-a" })
        await flush()
      }
      resolveDatabase({ messages: { upsert: mocks.dbUpsert } })
      await flush()

      if (transition !== "same-account reconnect") expect(mocks.dbUpsert).not.toHaveBeenCalled()
      else
        expect(mocks.dbUpsert).toHaveBeenCalledExactlyOnceWith(
          expect.objectContaining({ id: "accepted-a" })
        )
    }
  )

  it("replaces the transport on account changes without rejoining the previous account's room", async () => {
    const session = await connected({ currentUserId: "user-a" })
    act(() => session.result.current.sendJoin(CHAT))

    session.rerender({ enabled: true, currentUserId: "user-b" })
    await flush()

    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(1000)
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(sockets()).toHaveLength(2)
    act(() => lastSocket().onopen?.())
    expect(lastSocket().send).not.toHaveBeenCalled()
  })

  it("ignores the old account's open and private frames but accepts the new account's frames", async () => {
    const onNewMessage = vi.fn()
    const session = await connected({ currentUserId: "user-a", onNewMessage })
    session.rerender({ enabled: true, currentUserId: "user-b", onNewMessage })

    act(() => {
      session.socket.onopen?.()
      session.socket.receive({
        type: "new_message",
        chat_id: CHAT,
        message: message({ id: "private-a" }),
        stream_seq: 4,
        resume_token: "private-token-a",
      })
      session.socket.receive({
        type: "replay_checkpoint",
        chat_id: CHAT,
        stream_seq: 5,
        resume_token: "checkpoint-a",
      })
    })
    await flush()

    expect(session.result.current.isConnected).toBe(false)
    expect(session.queryClient.getQueryData(["messages", CHAT])).toBeUndefined()
    expect(onNewMessage).not.toHaveBeenCalled()
    expect(mocks.dbUpsert).not.toHaveBeenCalled()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-b")).toBeNull()
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-a")).toBeNull()

    // Ignored transports do not consume a parser result; clear only the scripted frame queue.
    mocks.parseWsMessage.mockReset()
    const newSocket = lastSocket()
    const incoming = message({ id: "private-b" })
    act(() => {
      newSocket.onopen?.()
      newSocket.receive({
        type: "new_message",
        chat_id: CHAT,
        message: incoming,
        stream_seq: 1,
        resume_token: "token-b",
      })
    })
    await flush()

    expect(session.result.current.isConnected).toBe(true)
    expect(
      session.queryClient.getQueryData<MessagesListResponse>(["messages", CHAT])?.items
    ).toStrictEqual([incoming])
    expect(onNewMessage).toHaveBeenCalledExactlyOnceWith(incoming, CHAT)
    expect(mocks.dbUpsert).toHaveBeenCalledOnce()
    expect(
      JSON.parse(window.sessionStorage.getItem("university.chat.replay.v2:user-b")!)
    ).toStrictEqual({
      entries: [[CHAT, 1, "token-b"]],
    })
    expect(window.sessionStorage.getItem("university.chat.replay.v2:user-a")).toBeNull()
  })

  it("aborts the previous account's ticket without releasing the new account's pending request", async () => {
    let resolveA!: (value: typeof TICKET) => void
    let resolveB!: (value: typeof TICKET) => void
    mocks.apiPost
      .mockReturnValueOnce(
        new Promise<typeof TICKET>((resolve) => {
          resolveA = resolve
        })
      )
      .mockReturnValueOnce(
        new Promise<typeof TICKET>((resolve) => {
          resolveB = resolve
        })
      )
    const session = setup({ currentUserId: "user-a" })
    await flush()
    const signalA = mocks.apiPost.mock.calls[0]![2].signal as AbortSignal

    session.rerender({ enabled: true, currentUserId: "user-b" })
    await flush()

    expect(signalA.aborted).toBe(true)
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    resolveA({ data: { ticket: "ticket-a", expires_in: 15 } })
    await flush()
    expect(sockets()).toHaveLength(0)
    act(() => window.dispatchEvent(new Event("online")))
    await flush()
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)

    resolveB({ data: { ticket: "ticket-b", expires_in: 15 } })
    await flush()
    expectTicketSocket("ticket-b")
  })

  it("keeps the same account's socket and checkpoint across ordinary rerenders", async () => {
    const session = await connected({ currentUserId: "user-a" })
    session.socket.receive({
      type: "replay_checkpoint",
      chat_id: CHAT,
      stream_seq: 3,
      resume_token: "a3",
    })

    session.rerender({ enabled: true, currentUserId: "user-a" })
    await flush()
    act(() => session.result.current.sendJoin(CHAT))

    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
    expect(session.socket.close).not.toHaveBeenCalled()
    expect(session.socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: CHAT, resume_token: "a3" })
    )
  })

  it.each(["disabled", "unmounted"])(
    "ignores stale open and private frames after the hook is %s",
    async (state) => {
      const onNewMessage = vi.fn()
      const session = await connected({ currentUserId: "user-a", onNewMessage })
      if (state === "disabled")
        session.rerender({ enabled: false, currentUserId: "user-a", onNewMessage })
      else session.unmount()

      act(() => {
        session.socket.onopen?.()
        session.socket.receive({ type: "new_message", chat_id: CHAT, message: message() })
      })
      await flush()

      expect(onNewMessage).not.toHaveBeenCalled()
      expect(mocks.dbUpsert).not.toHaveBeenCalled()
      expect(session.queryClient.getQueryData(["messages", CHAT])).toBeUndefined()
      if (state === "disabled") expect(session.result.current.isConnected).toBe(false)
    }
  )

  it("ignores reconnect requests while disabled or after unmount", async () => {
    const disabled = setup({ enabled: false })
    await flush()
    act(() => disabled.result.current.reconnect())
    await flush()
    expect(mocks.apiPost).not.toHaveBeenCalled()

    const { result, unmount } = await connected()
    const reconnect = result.current.reconnect
    lastSocket().readyState = ScriptedWebSocket.CLOSED
    unmount()
    act(() => reconnect())
    await flush()
    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
  })

  it("replaces a socket that closed before its close event arrived", async () => {
    const { result, socket } = await connected()

    act(() => result.current.reconnect())
    await flush()
    expect(mocks.apiPost).toHaveBeenCalledTimes(1)

    socket.readyState = ScriptedWebSocket.CLOSED
    act(() => result.current.reconnect())
    await flush()
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(sockets()).toHaveLength(2)
  })

  it("closes the socket and reports disconnection without waiting for the close event", async () => {
    const { result, socket } = await connected()
    socket.close = vi.fn()
    expect(result.current.isConnected).toBe(true)

    act(() => result.current.disconnect())

    expect(socket.close).toHaveBeenCalledExactlyOnceWith(1000)
    expect(result.current.isConnected).toBe(false)
  })

  it("closes the socket on unmount", async () => {
    const { unmount, socket } = await connected()

    unmount()

    expect(socket.close).toHaveBeenCalledExactlyOnceWith(1000)
  })

  it("cancels a scheduled reconnect on disconnect", async () => {
    const { result, socket } = await connected()
    act(() => socket.close(1006))

    act(() => result.current.disconnect())
    await act(() => vi.advanceTimersByTimeAsync(60_000))

    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
  })

  it("starts, retries and listens for connectivity only while enabled", async () => {
    const session = setup({ enabled: false })
    await flush()
    act(() => window.dispatchEvent(new Event("online")))
    await flush()
    expect(mocks.apiPost).not.toHaveBeenCalled()

    session.rerender({ enabled: true })
    await flush()
    expect(sockets()).toHaveLength(1)
    act(() => lastSocket().onopen?.())

    // A retry scheduled by the enabled connection uses the enabled connect.
    act(() => lastSocket().close(1006))
    await flush()
    expect(sockets()).toHaveLength(2)

    act(() => window.dispatchEvent(new Event("offline")))
    expect(lastSocket().close).toHaveBeenCalledWith(1000)

    session.rerender({ enabled: false })
    await flush()
    const rendersWhileDisabled = session.renders()
    act(() => window.dispatchEvent(new Event("online")))
    act(() => window.dispatchEvent(new Event("offline")))
    await flush()
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(session.renders()).toBe(rendersWhileDisabled)
  })

  it("keeps a released user's checkpoints out of memory after switching accounts", async () => {
    const session = await connected({ currentUserId: "user-a" })
    session.rerender({ enabled: true, currentUserId: "user-b" })
    await flush()
    lastSocket().receive({
      type: "replay_checkpoint",
      chat_id: CHAT,
      stream_seq: 4,
      resume_token: "token-b-4",
    })
    session.unmount()
    window.sessionStorage.clear()

    const next = await connected({ currentUserId: "user-b" })
    act(() => next.result.current.sendJoin(CHAT))

    expect(next.socket.send).toHaveBeenLastCalledWith(JSON.stringify({ type: "join", room: CHAT }))
  })
})

describe("rooms", () => {
  it("joins nothing on open until a room is selected", async () => {
    const { socket } = await connected()

    expect(socket.send).not.toHaveBeenCalled()
  })

  it("tolerates room changes before any socket exists", () => {
    mocks.apiPost.mockReturnValue(new Promise(() => undefined))
    const { result } = setup()

    expect(() => {
      result.current.sendJoin(CHAT)
      result.current.sendLeave(CHAT)
    }).not.toThrow()
  })

  it("rejoins only the room that is still selected after a reconnect", async () => {
    const { result, socket } = await connected()
    act(() => result.current.sendJoin(CHAT))
    act(() => result.current.sendLeave(OTHER_CHAT))

    act(() => socket.close(1006))
    await flush()
    act(() => lastSocket().onopen?.())
    expect(lastSocket().send).toHaveBeenCalledExactlyOnceWith(
      JSON.stringify({ type: "join", room: CHAT })
    )

    act(() => result.current.sendLeave(CHAT))
    act(() => lastSocket().close(1006))
    await flush()
    act(() => lastSocket().onopen?.())
    expect(lastSocket().send).not.toHaveBeenCalled()
  })

  it("throttles typing notifications to one per 500 ms per chat", () => {
    const sendTyping = vi.spyOn(chatApi, "sendTyping").mockResolvedValue(undefined)
    mocks.apiPost.mockReturnValue(new Promise(() => undefined))
    const { result } = setup()

    result.current.sendTyping(CHAT)
    vi.advanceTimersByTime(499)
    result.current.sendTyping(CHAT)
    vi.advanceTimersByTime(1)
    result.current.sendTyping(CHAT)

    expect(sendTyping).toHaveBeenCalledTimes(2)
  })
})

describe("typing indicators", () => {
  const typing = (userId: string, chatId = CHAT) => ({
    type: "typing",
    chat_id: chatId,
    user_id: userId,
    user_name: `Name ${userId}`,
  })

  it.each([false, true])(
    "releases every typing timer on unmount (StrictMode=%s)",
    async (strict) => {
      const session = setup({ currentUserId: "user-a" }, strict)
      await flush()
      const socket = lastSocket()
      act(() => socket.onopen?.())
      const baselineTimers = vi.getTimerCount()

      act(() => {
        socket.receive(typing("u1"))
        socket.receive(typing("u2"))
        socket.receive(typing("u1"))
      })
      expect(session.result.current.getTypingUsersForChat(CHAT)).toHaveLength(2)
      expect(vi.getTimerCount()).toBe(baselineTimers + 2)

      session.unmount()
      expect(vi.getTimerCount()).toBe(0)
    }
  )

  it.each(["disable", "account switch", "disconnect"])(
    "releases owned typing timers on %s without waiting for expiry",
    async (transition) => {
      const session = await connected({ currentUserId: "user-a" })
      const baselineTimers = vi.getTimerCount()
      act(() => session.socket.receive(typing("u1")))
      expect(vi.getTimerCount()).toBe(baselineTimers + 1)

      if (transition === "disable") session.rerender({ enabled: false, currentUserId: "user-a" })
      else if (transition === "account switch")
        session.rerender({ enabled: true, currentUserId: "user-b" })
      else act(() => session.result.current.disconnect())
      await flush()

      expect(session.result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])
      expect(vi.getTimerCount()).toBe(0)
      session.unmount()
      expect(vi.getTimerCount()).toBe(0)
    }
  )

  it("keeps a user typing for three seconds after their latest event", async () => {
    const { result, socket } = await connected()
    const baselineTimers = vi.getTimerCount()
    act(() => socket.receive(typing("u1")))
    act(() => vi.advanceTimersByTime(2_000))
    act(() => socket.receive(typing("u1")))

    act(() => vi.advanceTimersByTime(1_500))
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(1)
    act(() => vi.advanceTimersByTime(1_500))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])
    expect(vi.getTimerCount()).toBe(baselineTimers)
  })

  it("ignores a replaced typing entry's already queued expiry callback", async () => {
    const { result, socket } = await connected()
    const baselineTimers = vi.getTimerCount()
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout")
    act(() => socket.receive(typing("u1")))
    const staleExpiry = timeoutSpy.mock.calls.find((call) => call[1] === 3_000)![0]
    expect(staleExpiry).toEqual(expect.any(Function))
    act(() => vi.advanceTimersByTime(1_000))
    act(() => socket.receive(typing("u1")))

    act(() => (staleExpiry as () => void)())

    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([
      { userId: "u1", userName: "Name u1" },
    ])
    expect(vi.getTimerCount()).toBe(baselineTimers + 1)
    act(() => vi.advanceTimersByTime(3_000))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])
    expect(vi.getTimerCount()).toBe(baselineTimers)
  })

  it("rejects a new user at per-chat capacity while allowing another chat and refreshing existing users", async () => {
    const { result, socket } = await connected()
    const baselineTimers = vi.getTimerCount()
    act(() => {
      for (let index = 0; index < 20; index += 1) socket.receive(typing(`u${index}`))
    })
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(20)
    expect(vi.getTimerCount()).toBe(baselineTimers + 20)

    act(() => socket.receive(typing("u20")))
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(20)
    expect(result.current.getTypingUsersForChat(CHAT).some((user) => user.userId === "u20")).toBe(
      false
    )
    expect(vi.getTimerCount()).toBe(baselineTimers + 20)

    act(() => socket.receive(typing("other-peer", OTHER_CHAT)))
    expect(result.current.getTypingUsersForChat(OTHER_CHAT)).toStrictEqual([
      { userId: "other-peer", userName: "Name other-peer" },
    ])
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(20)
    expect(vi.getTimerCount()).toBe(baselineTimers + 21)

    act(() => vi.advanceTimersByTime(2_500))
    act(() => socket.receive(typing("u0")))
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(20)
    expect(vi.getTimerCount()).toBe(baselineTimers + 21)

    act(() => vi.advanceTimersByTime(1_000))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([
      { userId: "u0", userName: "Name u0" },
    ])
    expect(result.current.getTypingUsersForChat(OTHER_CHAT)).toStrictEqual([])
    expect(vi.getTimerCount()).toBe(baselineTimers + 1)
    act(() => vi.advanceTimersByTime(2_000))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])
    expect(vi.getTimerCount()).toBe(baselineTimers)
  })

  it("clears indicators and their timers when the connection closes", async () => {
    const { result, socket } = await connected()
    act(() => socket.receive(typing("u1")))
    act(() => vi.advanceTimersByTime(1_000))

    act(() => socket.close(1000))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])

    act(() => vi.advanceTimersByTime(1_000))
    act(() => socket.receive(typing("u1")))
    expect(result.current.getTypingUsersForChat(CHAT)).toStrictEqual([])
    act(() => result.current.reconnect())
    await flush()
    act(() => {
      lastSocket().onopen?.()
      lastSocket().receive(typing("u1"))
    })
    act(() => vi.advanceTimersByTime(1_500))
    expect(result.current.getTypingUsersForChat(CHAT)).toHaveLength(1)
  })
})

describe("new_message reconciliation", () => {
  const chats = (lastMessage: Message | undefined): ChatsListResponse =>
    ({
      items: [
        { id: CHAT, last_message: lastMessage, unread_count: 0 },
        { id: OTHER_CHAT, last_message: undefined, unread_count: 0 },
      ],
    }) as unknown as ChatsListResponse

  it("starts an empty history with the first live message and stores it offline", async () => {
    const { socket, queryClient, invalidateQueries } = await connected()
    const incoming = message({ content: "" })

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: incoming }))
    await flush()

    expect(queryClient.getQueryData(["messages", CHAT])).toStrictEqual({
      items: [incoming],
      has_more: false,
      next_cursor: null,
    })
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", CHAT],
      refetchType: "none",
    })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["chats"], refetchType: "none" })
    expect(mocks.dbUpsert).toHaveBeenCalledExactlyOnceWith({
      id: "m-1",
      chat_id: CHAT,
      sender_id: "peer",
      content: "",
      created_at: "2026-08-25T12:00:00.000Z",
      read_status: false,
      read_at: null,
      edited_at: null,
      deleted_at: null,
      attachments: [],
      reactions: [],
      sync_status: "synced",
    })
  })

  it("stores the message content offline", async () => {
    const { socket } = await connected()

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: message() }))
    await flush()

    expect(mocks.dbUpsert.mock.calls[0]?.[0]).toMatchObject({ content: "hello" })
  })

  it("refetches the active history when the cached history has an unreadable timestamp", async () => {
    const { socket, queryClient, invalidateQueries } = await connected()
    queryClient.setQueryData<MessagesListResponse>(["messages", CHAT], {
      items: [message({ id: "legacy", created_at: "not a date" })],
      has_more: false,
      next_cursor: null,
    })

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: message() }))

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", CHAT],
      refetchType: "active",
    })
  })

  it("does not append a message the render cache already shows", async () => {
    const { socket, queryClient } = await connected()
    const cached: MessagesListResponse = { items: [message()], has_more: false, next_cursor: null }
    queryClient.setQueryData(["messages", CHAT], cached)

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: message() }))

    expect(queryClient.getQueryData(["messages", CHAT])).toBe(cached)
  })

  it("updates the preview of the target chat only", async () => {
    const { socket, queryClient } = await connected()
    queryClient.setQueryData(["chats"], chats(undefined))
    const incoming = message()

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: incoming }))

    const items = queryClient.getQueryData<ChatsListResponse>(["chats"])!.items
    expect(items.map((chat) => [chat.last_message, chat.unread_count])).toStrictEqual([
      [incoming, 1],
      [undefined, 0],
    ])
  })

  it.each([
    ["a later id at the same instant replaces", { id: "m-2" }, "incoming"],
    ["the same id and instant keeps", { id: "m-1", content: "edited" }, "current"],
    ["an unreadable incoming timestamp keeps", { id: "m-2", created_at: "bad" }, "current"],
  ])("%s the chat preview", async (_label, overrides, expected) => {
    const { socket, queryClient } = await connected()
    const current = message({ id: "m-1" })
    queryClient.setQueryData(["chats"], chats(current))
    const incoming = message(overrides)

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: incoming }))

    const preview = queryClient.getQueryData<ChatsListResponse>(["chats"])!.items[0]!.last_message
    expect(preview).toStrictEqual(expected === "incoming" ? incoming : current)
  })

  it("keeps an unreadable preview rather than guessing the order", async () => {
    const { socket, queryClient } = await connected()
    const current = message({ id: "m-0", created_at: "bad" })
    queryClient.setQueryData(["chats"], chats(current))

    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: message() }))

    expect(
      queryClient.getQueryData<ChatsListResponse>(["chats"])!.items[0]!.last_message
    ).toStrictEqual(current)
  })
})

describe("frame side effects", () => {
  it.each([
    ["read", { user_id: "peer", read_at: null }],
    ["message_edited", { message_id: "m-1", content: "x", edited_at: "2026-08-25T12:00:00Z" }],
    ["reaction_changed", { message_id: "m-1", emoji: "👍", action: "added", user_id: "peer" }],
  ])("marks the chat history stale without refetching on %s", async (type, fields) => {
    const { socket, invalidateQueries } = await connected()

    act(() => socket.receive({ type, chat_id: CHAT, ...fields }))

    expect(invalidateQueries).toHaveBeenCalledExactlyOnceWith({
      queryKey: ["messages", CHAT],
      refetchType: "none",
    })
  })

  it("invalidates the active sidebar after a message deletion", async () => {
    const { socket, invalidateQueries } = await connected()

    act(() =>
      socket.receive({
        type: "message_deleted",
        chat_id: CHAT,
        message_id: "m-1",
        deleted_at: "2026-08-25T12:00:00Z",
      })
    )

    expect(invalidateQueries).toHaveBeenNthCalledWith(1, {
      queryKey: ["messages", CHAT],
      refetchType: "none",
    })
    expect(invalidateQueries).toHaveBeenNthCalledWith(2, {
      queryKey: ["chats"],
      refetchType: "active",
    })
  })

  it("handles read and presence frames without optional handlers", async () => {
    const { socket } = await connected()

    act(() => {
      socket.receive({ type: "read", chat_id: CHAT, user_id: "peer", read_at: null })
      socket.receive({ type: "presence", user_id: "peer", active: false, last_seen: null })
    })

    expect(mocks.logError).not.toHaveBeenCalled()
  })

  it.each([
    ["another error code", { code: "rate_limited", room: CHAT }],
    ["an expired resume token without a room", { code: "invalid_resume_token" }],
  ])("keeps the room checkpoint for %s", async (_label, fields) => {
    const { socket, result, invalidateQueries } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    const joinsBeforeError = sentJoins(socket).length

    act(() => socket.receive({ type: "error", ...fields }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(invalidateQueries).not.toHaveBeenCalled()
    expect(sentJoins(socket)).toHaveLength(joinsBeforeError)
    act(() => result.current.sendJoin(CHAT))
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: CHAT, resume_token: "t3" })
    )
  })

  it("reconnects after replay storage recovers and rejoins with the saved signed cursor", async () => {
    const session = await connected({ currentUserId: "me" })
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    const rejectedSocket = session.socket
    rejectedSocket.receive({
      type: "replay_checkpoint",
      chat_id: CHAT,
      stream_seq: 3,
      resume_token: "t3",
    })
    act(() => session.result.current.sendJoin(CHAT))

    act(() => rejectedSocket.receive({ type: "error", code: "replay_unavailable", room: CHAT }))

    expect(rejectedSocket.close).toHaveBeenCalledExactlyOnceWith(4002, "replay_unavailable")
    expect(session.result.current.isConnected).toBe(false)
    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(sockets()).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()

    expect(sockets()).toHaveLength(2)
    const recoveredSocket = lastSocket()
    act(() => recoveredSocket.onopen?.())
    expect(session.result.current.isConnected).toBe(true)
    expect(sentJoins(recoveredSocket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "t3" },
    ])

    act(() =>
      recoveredSocket.receive({
        type: "replay_checkpoint",
        chat_id: CHAT,
        stream_seq: 4,
        resume_token: "t4",
      })
    )
    act(() => session.result.current.sendJoin(CHAT))
    expect(sentJoins(recoveredSocket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "t3" },
      { type: "join", room: CHAT, resume_token: "t4" },
    ])
  })

  it.each([
    ["another room", "me", true, OTHER_CHAT],
    ["missing room", "me", true, undefined],
    ["missing checkpoint", "me", false, CHAT],
    ["anonymous scope", undefined, false, CHAT],
  ])(
    "does not restart the transport when replay is unavailable for %s",
    async (_label, userId, hasCheckpoint, errorRoom) => {
      const session = await connected({ currentUserId: userId })
      if (hasCheckpoint) {
        session.socket.receive({
          type: "replay_checkpoint",
          chat_id: CHAT,
          stream_seq: 3,
          resume_token: "t3",
        })
      }
      act(() => session.result.current.sendJoin(CHAT))
      act(() =>
        session.socket.receive({ type: "error", code: "replay_unavailable", room: errorRoom })
      )

      await act(() => vi.advanceTimersByTimeAsync(1_000))

      expect(session.socket.close).not.toHaveBeenCalled()
      expect(sockets()).toHaveLength(1)
      expect(session.result.current.isConnected).toBe(true)
    }
  )

  it("uses the existing ten-attempt reconnect cap if replay remains unavailable", async () => {
    const session = await connected({ currentUserId: "me" })
    let socket = session.socket
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => session.result.current.sendJoin(CHAT))

    for (let unavailableCount = 0; unavailableCount <= 10; unavailableCount += 1) {
      if (unavailableCount > 0) {
        socket = lastSocket()
        act(() => socket.onopen?.())
        expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT, resume_token: "t3" }])
      }
      act(() => socket.receive({ type: "error", code: "replay_unavailable", room: CHAT }))

      if (unavailableCount < 10) {
        await act(() => vi.advanceTimersByTimeAsync(60_000))
        await flush()
        expect(sockets()).toHaveLength(unavailableCount + 2)
      }
    }

    expect(sockets()).toHaveLength(11)
    expect(session.result.current.isConnected).toBe(false)
    expect(mocks.logError).toHaveBeenCalledWith(
      "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
      { attempts: 10, lastCode: 4002 }
    )
    expect(vi.getTimerCount()).toBe(0)
  })

  it("retries a rate-limited resume once on the same socket with the unchanged signed cursor", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))

    await act(() => vi.advanceTimersByTimeAsync(1_049))
    expect(sentJoins(socket)).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))

    expect(lastSocket()).toBe(socket)
    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "t3" },
      { type: "join", room: CHAT, resume_token: "t3" },
    ])

    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(socket)).toHaveLength(2)
  })

  it("does not retry a rate-limited cursor after the active room changes", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() => result.current.sendJoin(OTHER_CHAT))

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "t3" },
      { type: "join", room: OTHER_CHAT },
    ])
  })

  it("does not retry a rate-limited cursor after its checkpoint advances", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() =>
      socket.receive({
        type: "replay_checkpoint",
        chat_id: CHAT,
        stream_seq: 4,
        resume_token: "t4",
      })
    )

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT, resume_token: "t3" }])
  })

  it("does not schedule a rate-limited retry for a room that is no longer active", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => result.current.sendJoin(OTHER_CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "t3" },
      { type: "join", room: OTHER_CHAT },
    ])
  })

  it("does not retry a rate-limited cursor after invalidation removes its checkpoint", async () => {
    const { socket, result, invalidateQueries } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() => socket.receive({ type: "error", code: "invalid_resume_token", room: CHAT }))

    expect(peekReplayCheckpoint("me", CHAT)).toBeUndefined()
    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT, resume_token: "t3" }])
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["messages", CHAT],
      refetchType: "all",
    })
  })

  it("does not retry a cursor when its resume token changes at the same sequence", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() => writeReplayCheckpoint("me", CHAT, 3, "replacement-t3", CHAT))

    expect(peekReplayCheckpoint("me", CHAT)).toStrictEqual({
      sequence: 3,
      resumeToken: "replacement-t3",
    })
    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT, resume_token: "t3" }])
  })

  it("does not retry a rate-limited cursor on a closed socket", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    socket.readyState = ScriptedWebSocket.CLOSED

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toHaveLength(1)
  })

  it("contains a socket send failure during the bounded replay retry", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    socket.send.mockImplementationOnce(() => {
      throw new Error("socket closed during retry")
    })
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toHaveLength(2)
  })

  it("does not retry a rate-limited cursor after the authenticated user changes", async () => {
    const session = await connected({ currentUserId: "user-a" })
    session.socket.receive({
      type: "replay_checkpoint",
      chat_id: CHAT,
      stream_seq: 3,
      resume_token: "a3",
    })
    act(() => session.result.current.sendJoin(CHAT))
    act(() =>
      session.socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT })
    )
    session.rerender({ enabled: true, currentUserId: "user-b" })

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(session.socket)).toStrictEqual([
      { type: "join", room: CHAT, resume_token: "a3" },
    ])
  })

  it.each([
    ["missing checkpoint", "me"],
    ["anonymous session", undefined],
  ])(
    "does not retry a rate-limited join without an authenticated checkpoint for %s",
    async (_label, userId) => {
      const { socket, result } = await connected({ currentUserId: userId })
      act(() => result.current.sendJoin(CHAT))
      act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))

      await act(() => vi.advanceTimersByTimeAsync(1_050))

      expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT }])
    }
  )

  it("clears a pending replay retry when the hook disconnects", async () => {
    const { socket, result } = await connected({ currentUserId: "me" })
    socket.receive({ type: "replay_checkpoint", chat_id: CHAT, stream_seq: 3, resume_token: "t3" })
    act(() => result.current.sendJoin(CHAT))
    act(() => socket.receive({ type: "error", code: "replay_join_rate_limited", room: CHAT }))
    act(() => result.current.disconnect())

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([{ type: "join", room: CHAT, resume_token: "t3" }])
  })

  it.each([
    ["no stream sequence", { chat_id: CHAT, resume_token: "t9" }],
    ["no resume token", { chat_id: CHAT, stream_seq: 9 }],
    ["no chat", { stream_seq: 9, resume_token: "t9" }],
  ])("stores no checkpoint for a frame with %s", async (_label, fields) => {
    const { socket, result } = await connected({ currentUserId: "me" })

    act(() =>
      socket.receive({
        type: "presence",
        user_id: "peer",
        active: true,
        last_seen: null,
        ...fields,
      })
    )

    act(() => result.current.sendJoin(CHAT))
    expect(socket.send).toHaveBeenLastCalledWith(JSON.stringify({ type: "join", room: CHAT }))
  })
})

describe("applyReactionChangedFrame", () => {
  it("counts a reaction on its own emoji and adds a new one as someone else's", () => {
    const cache: MessagesListResponse = {
      items: [
        message({
          reactions: [
            { emoji: "👍", count: 1, reacted_by_me: true },
            { emoji: "❤️", count: 1, reacted_by_me: false },
          ],
        }),
      ],
      has_more: false,
      next_cursor: null,
    }

    const counted = applyReactionChangedFrame(cache, {
      message_id: "m-1",
      emoji: "❤️",
      action: "added",
    })
    const added = applyReactionChangedFrame(counted, {
      message_id: "m-1",
      emoji: "🔥",
      action: "added",
    })

    expect(added!.items[0]!.reactions).toStrictEqual([
      { emoji: "👍", count: 1, reacted_by_me: true },
      { emoji: "❤️", count: 2, reacted_by_me: false },
      { emoji: "🔥", count: 1, reacted_by_me: false },
    ])
  })
})

describe("legacy message edit and deletion reconciliation", () => {
  it.each([
    ["valid", "invalid", "previous"],
    ["invalid", "2026-08-25T12:00:00Z", "updated"],
  ])(
    "reconciles %s cached edit timestamps without allowing unreadable incoming edits",
    (existing, incoming, content) => {
      const current = message({
        content: "previous",
        edited_at: existing === "valid" ? "2026-08-24T12:00:00Z" : "invalid",
      })
      const cached = { items: [current], has_more: false, next_cursor: null }
      expect(
        applyMessageEditedFrame(cached, {
          message_id: current.id,
          content: "updated",
          edited_at: incoming,
        })?.items[0]?.content
      ).toBe(content)
    }
  )

  it("keeps a chat with no preview when a different message is deleted", async () => {
    const { socket, queryClient } = await connected()
    queryClient.setQueryData(["chats"], {
      items: [{ id: CHAT, last_message: undefined, unread_count: 0 }],
      has_more: false,
      next_cursor: null,
    })
    act(() =>
      socket.receive({
        type: "message_deleted",
        chat_id: CHAT,
        message_id: "older-message",
        deleted_at: "2026-08-25T12:00:00Z",
      })
    )
    expect(
      queryClient.getQueryData<ChatsListResponse>(["chats"])!.items[0]?.last_message
    ).toBeUndefined()
  })
})

describe("remaining selected WebSocket decisions", () => {
  it("uses the disconnected external-store snapshot during server rendering", () => {
    function ServerSnapshot() {
      return <output>{String(useChatWebSocket({}).isConnected)}</output>
    }

    const html = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <WebSocketProvider>
          <ServerSnapshot />
        </WebSocketProvider>
      </QueryClientProvider>
    )

    expect(html).toContain("<output>false</output>")
  })

  it("uses WSS on an HTTPS page", async () => {
    const originalWindow = globalThis.window
    const secureLocation = new Proxy(originalWindow.location, {
      get(target, property) {
        if (property === "protocol") return "https:"
        const value = Reflect.get(target, property, target)
        return typeof value === "function" ? value.bind(target) : value
      },
    })
    const secureWindow = new Proxy(originalWindow, {
      get(target, property) {
        if (property === "location") return secureLocation
        return Reflect.get(target, property, target)
      },
    })
    vi.stubGlobal("window", secureWindow)

    try {
      setup()
      await flush()
      expect(new URL(lastSocket().url).protocol).toBe("wss:")
      expectTicketSocket("ticket-1")
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("does not allocate a second heartbeat interval for a duplicate open event", async () => {
    const intervalSpy = vi.spyOn(globalThis, "setInterval")
    const session = await connected()
    const heartbeatIntervals = () => intervalSpy.mock.calls.filter(([, delay]) => delay === 30_000)

    expect(heartbeatIntervals()).toHaveLength(1)
    act(() => session.socket.onopen?.())
    expect(heartbeatIntervals()).toHaveLength(1)
  })

  it("uses safe offline defaults for absent message fields", async () => {
    const { socket } = await connected()
    const receivedAt = new Date(Date.now()).toISOString()

    act(() =>
      socket.receive({
        type: "new_message",
        chat_id: CHAT,
        message: {
          id: "defaults",
          sender_id: "peer",
          content: "",
          created_at: "",
          read_status: null,
          read_at: null,
          edited_at: null,
          deleted_at: null,
          attachments: null,
          reactions: null,
        },
      })
    )
    await flush()

    expect(mocks.dbUpsert).toHaveBeenCalledExactlyOnceWith({
      id: "defaults",
      chat_id: CHAT,
      sender_id: "peer",
      content: "",
      created_at: receivedAt,
      read_status: false,
      read_at: null,
      edited_at: null,
      deleted_at: null,
      attachments: [],
      reactions: [],
      sync_status: "synced",
    })
  })

  it("swallows lazy database and message upsert failures", async () => {
    const { socket } = await connected()
    mocks.dbLoad.mockRejectedValueOnce(new Error("database unavailable"))
    act(() => socket.receive({ type: "new_message", chat_id: CHAT, message: message() }))
    await flush()

    mocks.dbUpsert.mockRejectedValueOnce(new Error("write unavailable"))
    mocks.dbLoad.mockResolvedValueOnce({ messages: { upsert: mocks.dbUpsert } })
    act(() =>
      socket.receive({ type: "new_message", chat_id: CHAT, message: message({ id: "m-2" }) })
    )
    await flush()

    expect(mocks.dbLoad).toHaveBeenCalledTimes(2)
    expect(mocks.dbUpsert).toHaveBeenCalledOnce()
    expect(mocks.logError).not.toHaveBeenCalled()
  })

  it("logs a parser exception from a malformed socket frame", async () => {
    const { socket } = await connected()
    const parseError = new Error("bad frame")
    mocks.parseWsMessage.mockImplementationOnce(() => {
      throw parseError
    })

    act(() => socket.onmessage?.({ data: "not-json" } as MessageEvent))

    expect(mocks.logError).toHaveBeenCalledExactlyOnceWith(
      "[WebSocket] Failed to parse message:",
      parseError
    )
  })

  it("swallows transient typing request failures", async () => {
    const sendTyping = vi.spyOn(chatApi, "sendTyping").mockRejectedValueOnce(new Error("offline"))
    const { result } = setup()

    act(() => result.current.sendTyping(CHAT))
    await flush()

    expect(sendTyping).toHaveBeenCalledExactlyOnceWith(CHAT)
    expect(mocks.logError).not.toHaveBeenCalled()
  })

  it("keeps deleted messages terminal and accepts the first edit timestamp", () => {
    const deleted = message({ id: "deleted", deleted_at: "2026-08-25T11:00:00Z" })
    const live = message({ id: "live", edited_at: undefined, deleted_at: undefined })
    const cache = { items: [deleted, live], has_more: false, next_cursor: null }

    expect(
      applyMessageEditedFrame(cache, {
        message_id: "deleted",
        content: "must stay deleted",
        edited_at: "2026-08-25T12:00:00Z",
      })?.items[0]
    ).toMatchObject({ content: "hello", deleted_at: "2026-08-25T11:00:00Z" })
    expect(
      applyMessageEditedFrame(cache, {
        message_id: "live",
        content: "first edit",
        edited_at: "2026-08-25T12:00:00Z",
      })?.items[1]
    ).toMatchObject({ content: "first edit", edited_at: "2026-08-25T12:00:00Z" })
    expect(
      applyMessageEditedFrame(
        {
          items: [message({ id: "ordered", edited_at: "2026-08-25T13:00:00Z" })],
          has_more: false,
          next_cursor: null,
        },
        {
          message_id: "ordered",
          content: "older edit",
          edited_at: "2026-08-25T12:00:00Z",
        }
      )?.items[0]
    ).toMatchObject({ content: "hello", edited_at: "2026-08-25T13:00:00Z" })
    expect(
      applyMessageEditedFrame(undefined, {
        message_id: "live",
        content: "ignored without cache",
        edited_at: "2026-08-25T12:00:00Z",
      })
    ).toBeUndefined()
  })

  it("tombstones only the deleted message and preserves its first deletion time", () => {
    const cache = {
      items: [
        message({ id: "target", deleted_at: undefined, attachments: [{ id: "file" }] as never }),
        message({ id: "other" }),
      ],
      has_more: false,
      next_cursor: null,
    }
    const result = applyMessageDeletedFrame(cache, {
      message_id: "target",
      deleted_at: "2026-08-25T12:00:00Z",
    })

    expect(result?.items[0]).toMatchObject({
      id: "target",
      content: "",
      attachments: [],
      deleted_at: "2026-08-25T12:00:00Z",
    })
    expect(result?.items[1]).toBe(cache.items[1])
    const alreadyDeleted = applyMessageDeletedFrame(
      {
        items: [message({ id: "target", deleted_at: "2026-08-24T12:00:00Z" })],
        has_more: false,
        next_cursor: null,
      },
      { message_id: "target", deleted_at: "2026-08-25T12:00:00Z" }
    )
    expect(alreadyDeleted?.items[0]?.deleted_at).toBe("2026-08-24T12:00:00Z")
    expect(
      applyMessageDeletedFrame(undefined, {
        message_id: "target",
        deleted_at: "2026-08-25T12:00:00Z",
      })
    ).toBeUndefined()
  })

  it("decrements and removes peer reactions without creating missing deltas", () => {
    const cache = {
      items: [
        message({
          id: "target",
          reactions: [
            { emoji: "👍", count: 1, reacted_by_me: false },
            { emoji: "❤️", count: 2, reacted_by_me: true },
          ],
        }),
        message({ id: "other" }),
      ],
      has_more: false,
      next_cursor: null,
    }
    const afterOneRemoval = applyReactionChangedFrame(cache, {
      message_id: "target",
      emoji: "❤️",
      action: "removed",
    })
    const afterSecondHeartRemoval = applyReactionChangedFrame(afterOneRemoval, {
      message_id: "target",
      emoji: "❤️",
      action: "removed",
    })
    const afterLastRemoval = applyReactionChangedFrame(afterSecondHeartRemoval, {
      message_id: "target",
      emoji: "👍",
      action: "removed",
    })
    const missingReaction = applyReactionChangedFrame(afterLastRemoval, {
      message_id: "target",
      emoji: "🚀",
      action: "removed",
    })
    const firstReaction = applyReactionChangedFrame(
      {
        items: [message({ id: "empty-reactions", reactions: undefined })],
        has_more: false,
        next_cursor: null,
      },
      { message_id: "empty-reactions", emoji: "✨", action: "added" }
    )

    expect(afterOneRemoval?.items[0]?.reactions).toStrictEqual([
      { emoji: "👍", count: 1, reacted_by_me: false },
      { emoji: "❤️", count: 1, reacted_by_me: true },
    ])
    expect(afterLastRemoval?.items[0]?.reactions).toStrictEqual([])
    expect(missingReaction?.items[0]?.reactions).toStrictEqual([])
    expect(firstReaction?.items[0]?.reactions).toStrictEqual([
      { emoji: "✨", count: 1, reacted_by_me: false },
    ])
  })

  it("does not apply the viewer's read or reaction echoes, but applies peer frames", async () => {
    const { socket, queryClient, invalidateQueries } = await connected({ currentUserId: "me" })
    const originalMessage = message({
      sender_id: "peer",
      reactions: [{ emoji: "👍", count: 1, reacted_by_me: true }],
    })
    queryClient.setQueryData<MessagesListResponse>(["messages", CHAT], {
      items: [originalMessage],
      has_more: false,
      next_cursor: null,
    })
    invalidateQueries.mockClear()

    act(() =>
      socket.receive({
        type: "read",
        chat_id: CHAT,
        user_id: "me",
        read_at: "2026-08-25T12:00:00Z",
      })
    )
    act(() =>
      socket.receive({
        type: "reaction_changed",
        chat_id: CHAT,
        message_id: originalMessage.id,
        emoji: "👍",
        action: "added",
        user_id: "me",
      })
    )
    expect(queryClient.getQueryData<MessagesListResponse>(["messages", CHAT])?.items[0]).toBe(
      originalMessage
    )
    expect(invalidateQueries).not.toHaveBeenCalled()

    act(() =>
      socket.receive({
        type: "reaction_changed",
        chat_id: CHAT,
        message_id: originalMessage.id,
        emoji: "👍",
        action: "added",
        user_id: "peer",
      })
    )
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", CHAT])?.items[0]?.reactions
    ).toStrictEqual([{ emoji: "👍", count: 2, reacted_by_me: true }])
    expect(invalidateQueries).toHaveBeenCalledOnce()
  })

  it("updates only the current edited sidebar preview", async () => {
    const { socket, queryClient } = await connected()
    const current = message({ id: "m-1", edited_at: "2026-08-24T12:00:00Z" })
    const unrelated = message({ id: "other" })
    queryClient.setQueryData(["chats"], {
      items: [
        { id: CHAT, last_message: current, unread_count: 0 },
        { id: OTHER_CHAT, last_message: current, unread_count: 0 },
        { id: CHAT, last_message: unrelated, unread_count: 0 },
      ],
    })
    queryClient.setQueryData<MessagesListResponse>(["messages", CHAT], {
      items: [current, unrelated],
      has_more: false,
      next_cursor: null,
    })

    act(() =>
      socket.receive({
        type: "message_edited",
        chat_id: CHAT,
        message_id: current.id,
        content: "updated preview",
        edited_at: "2026-08-25T12:00:00Z",
      })
    )

    const chats = queryClient.getQueryData<ChatsListResponse>(["chats"])!.items
    expect(chats[0]?.last_message).toMatchObject({ content: "updated preview" })
    expect(chats[1]?.last_message).toBe(current)
    expect(chats[2]?.last_message).toBe(unrelated)

    const deletedPreview = message({
      id: "deleted-preview",
      deleted_at: "2026-08-24T12:00:00Z",
    })
    queryClient.setQueryData(["chats"], {
      items: [{ id: CHAT, last_message: deletedPreview, unread_count: 0 }],
    })
    const cachedPreviewBeforeEdit = queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]
      ?.last_message
    expect(cachedPreviewBeforeEdit).toStrictEqual(deletedPreview)
    const cachedPreviewSnapshotBeforeEdit = structuredClone(cachedPreviewBeforeEdit)
    act(() =>
      socket.receive({
        type: "message_edited",
        chat_id: CHAT,
        message_id: deletedPreview.id,
        content: "a tombstone cannot be edited",
        edited_at: "2026-08-25T12:00:00Z",
      })
    )
    const cachedPreviewAfterEdit = queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]
      ?.last_message
    expect(cachedPreviewAfterEdit).toBe(cachedPreviewBeforeEdit)
    expect(cachedPreviewAfterEdit).toStrictEqual(cachedPreviewSnapshotBeforeEdit)
  })

  it("tombstones cached history and removes the matching deleted sidebar preview", async () => {
    const { socket, queryClient } = await connected()
    const target = message({ id: "deleted-preview" })
    const other = message({ id: "other" })
    queryClient.setQueryData<MessagesListResponse>(["messages", CHAT], {
      items: [target, other],
      has_more: false,
      next_cursor: null,
    })
    queryClient.setQueryData(["chats"], {
      items: [{ id: CHAT, last_message: target, unread_count: 0 }],
    })

    act(() =>
      socket.receive({
        type: "message_deleted",
        chat_id: CHAT,
        message_id: target.id,
        deleted_at: "2026-08-25T12:00:00Z",
      })
    )

    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", CHAT])?.items[0]
    ).toMatchObject({
      id: target.id,
      content: "",
      deleted_at: "2026-08-25T12:00:00Z",
    })
    expect(queryClient.getQueryData<ChatsListResponse>(["chats"])?.items[0]?.last_message).toBe(
      undefined
    )
  })
})

describe("application heartbeat", () => {
  it("sends every 30 seconds and accepts the matching nonce acknowledgement", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    await act(() => vi.advanceTimersByTimeAsync(29_999))
    expect(sentHeartbeats(session.socket)).toHaveLength(0)

    await act(() => vi.advanceTimersByTimeAsync(1))
    const firstPings = sentHeartbeats(session.socket)
    expect(firstPings).toHaveLength(1)
    const firstPing = firstPings[0]!
    expect(firstPing.type).toBe("heartbeat_ping")
    expect(firstPing.nonce).toMatch(/^[0-9a-f]{32}$/)

    act(() => session.socket.receive({ type: "heartbeat_pong", nonce: firstPing.nonce }))
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(session.socket.close).not.toHaveBeenCalled()
    expect(session.result.current.isConnected).toBe(true)

    await act(() => vi.advanceTimersByTimeAsync(20_000))
    const heartbeats = sentHeartbeats(session.socket)
    expect(heartbeats).toHaveLength(2)
    expect(heartbeats[1]!.nonce).not.toBe(firstPing.nonce)
  })

  it("does not schedule a heartbeat interval when the socket opens in a hidden page", async () => {
    const originalVisibility = Object.getOwnPropertyDescriptor(document, "visibilityState")
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" })
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    try {
      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(sentHeartbeats(session.socket)).toHaveLength(0)
      expect(session.socket.close).not.toHaveBeenCalled()

      Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" })
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      expect(sentHeartbeats(session.socket)).toHaveLength(1)
    } finally {
      session.unmount()
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
    }
  })

  it("pauses an acknowledgement deadline when visibility became hidden without an event", async () => {
    const originalVisibility = Object.getOwnPropertyDescriptor(document, "visibilityState")
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    try {
      await act(() => vi.advanceTimersByTimeAsync(30_000))
      const firstPing = sentHeartbeats(session.socket)[0]!
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" })

      await act(() => vi.advanceTimersByTimeAsync(10_000))
      expect(session.socket.close).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)
      expect(vi.getTimerCount()).toBe(0)

      Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" })
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      const heartbeats = sentHeartbeats(session.socket)
      expect(heartbeats).toHaveLength(2)
      expect(heartbeats[1]!.nonce).not.toBe(firstPing.nonce)
      act(() => session.socket.receive({ type: "heartbeat_pong", nonce: heartbeats[1]!.nonce }))
      await act(() => vi.advanceTimersByTimeAsync(10_000))
      expect(session.socket.close).not.toHaveBeenCalled()
    } finally {
      session.unmount()
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
    }
  })

  it("ignores spurious visible changes and interval ticks while an ACK is pending", async () => {
    const intervalSpy = vi.spyOn(globalThis, "setInterval")
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false
    const intervalCallback = intervalSpy.mock.calls.find(([, delay]) => delay === 30_000)?.[0]
    expect(typeof intervalCallback).toBe("function")

    try {
      act(() => document.dispatchEvent(new Event("visibilitychange")))
      expect(sentHeartbeats(session.socket)).toHaveLength(0)

      await act(() => vi.advanceTimersByTimeAsync(30_000))
      const firstPing = sentHeartbeats(session.socket)[0]!
      act(() => (intervalCallback as () => void)())
      expect(sentHeartbeats(session.socket)).toHaveLength(1)

      act(() => session.socket.receive({ type: "heartbeat_pong", nonce: firstPing.nonce }))
      session.socket.readyState = ScriptedWebSocket.CLOSED
      act(() => (intervalCallback as () => void)())
      expect(sentHeartbeats(session.socket)).toHaveLength(1)
      expect(session.socket.close).not.toHaveBeenCalled()
    } finally {
      session.unmount()
    }
  })

  it("ignores a captured ACK timeout callback after transport cleanup", async () => {
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout")
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false
    session.socket.emitCloseEventOnClose = false

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(sentHeartbeats(session.socket)).toHaveLength(1)
    const timeoutCallback = timeoutSpy.mock.calls.find(([, delay]) => delay === 10_000)?.[0]
    expect(typeof timeoutCallback).toBe("function")

    act(() => session.result.current.disconnect())
    const closeCallsAfterDisconnect = session.socket.close.mock.calls.length
    act(() => (timeoutCallback as () => void)())

    expect(session.socket.close).toHaveBeenCalledTimes(closeCallsAfterDisconnect)
    expect(mocks.apiPost).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
    session.unmount()
  })

  it("does not finish the transport twice when heartbeat send races a close event", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    session.socket.send.mockImplementationOnce(() => {
      session.socket.close(1006)
      throw new Error("socket closed during send")
    })

    await act(() => vi.advanceTimersByTimeAsync(30_000))

    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(1006)
    expect(session.socket.closeEventCount).toBe(1)
    expect(session.result.current.isConnected).toBe(false)
    expect(vi.getTimerCount()).toBe(1)
    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(sockets()).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(sockets()).toHaveLength(2)
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    session.unmount()
  })

  it("does not treat an early matching heartbeat ACK as a stable recovery", async () => {
    const originalVisibility = Object.getOwnPropertyDescriptor(document, "visibilityState")
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    const changeVisibility = (state: DocumentVisibilityState) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, value: state })
      act(() => document.dispatchEvent(new Event("visibilitychange")))
    }

    try {
      changeVisibility("hidden")
      changeVisibility("visible")
      const ping = sentHeartbeats(session.socket)[0]!
      expect(ping.nonce).toMatch(/^[0-9a-f]{32}$/)
      act(() => session.socket.receive({ type: "heartbeat_pong", nonce: ping.nonce }))
      await act(() => vi.advanceTimersByTimeAsync(10_000))
      expect(session.socket.close).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)
    } finally {
      session.unmount()
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
    }
  })

  it("closes a blackholed socket and retries without a close event or stale timer", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false
    session.socket.emitCloseEventOnClose = false

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(sentHeartbeats(session.socket)).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(9_999))
    expect(session.socket.close).not.toHaveBeenCalled()
    expect(session.result.current.isConnected).toBe(true)

    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
    expect(session.socket.closeEventCount).toBe(0)
    expect(session.result.current.isConnected).toBe(false)
    expect(sockets()).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(1_000))
    await flush()
    expect(sockets()).toHaveLength(2)
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
  })

  it("does not reset the reconnect cap after repeated unacknowledged heartbeats", async () => {
    const session = await connected()
    let socket = session.socket

    for (let failedSocket = 0; failedSocket <= 10; failedSocket += 1) {
      socket.autoAcknowledgeHeartbeats = false
      socket.emitCloseEventOnClose = false
      if (failedSocket > 0) act(() => socket.onopen?.())

      await act(() => vi.advanceTimersByTimeAsync(40_000))

      expect(sentHeartbeats(socket)).toHaveLength(1)
      expect(socket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
      expect(socket.closeEventCount).toBe(0)
      expect(session.result.current.isConnected).toBe(false)
      await flush()

      if (failedSocket < 10) {
        await act(() => vi.advanceTimersByTimeAsync(1_000))
        await flush()
        expect(sockets()).toHaveLength(failedSocket + 2)
        socket = lastSocket()
      }
    }

    expect(sockets()).toHaveLength(11)
    expect(mocks.logError).toHaveBeenLastCalledWith(
      "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
      { attempts: 10, lastCode: 4000 }
    )
    expect(vi.getTimerCount()).toBe(0)
  })

  it("resets the reconnect budget after a stable matching heartbeat acknowledgement", async () => {
    const session = await connected()
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    act(() => session.socket.close(1006))

    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(sockets()).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(sockets()).toHaveLength(2)

    const stableSocket = lastSocket()
    stableSocket.autoAcknowledgeHeartbeats = false
    act(() => stableSocket.onopen?.())
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const ping = sentHeartbeats(stableSocket)[0]!
    act(() => stableSocket.receive({ type: "heartbeat_pong", nonce: ping.nonce }))
    // Disconnect invalidates ownership before its close callback, so only the
    // matching ACK can reset the retry budget for the next short-lived socket.
    act(() => session.result.current.disconnect())
    act(() => session.result.current.reconnect())
    await flush()
    expect(sockets()).toHaveLength(3)
    const shortLivedSocket = lastSocket()
    act(() => shortLivedSocket.onopen?.())
    act(() => shortLivedSocket.close(1006))

    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(sockets()).toHaveLength(3)
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(sockets()).toHaveLength(4)
  })

  it("tears down on send failure and schedules one retry through the capped path", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    session.socket.send.mockImplementationOnce(() => {
      throw new Error("simulated send failure")
    })

    await act(() => vi.advanceTimersByTimeAsync(30_000))

    expect(sentHeartbeats(session.socket)).toHaveLength(1)
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
    expect(session.socket.closeEventCount).toBe(1)
    expect(session.result.current.isConnected).toBe(false)
    // The synchronous close callback is stale after ownership is cleared;
    // exactly one capped-backoff timer remains for the retry.
    expect(vi.getTimerCount()).toBe(1)

    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(sockets()).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(sockets()).toHaveLength(2)
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("does not let a wrong nonce acknowledge the outstanding heartbeat", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const pings = sentHeartbeats(session.socket)
    expect(pings).toHaveLength(1)
    const ping = pings[0]!
    const wrongNonce = ping.nonce === "f".repeat(32) ? "e".repeat(32) : "f".repeat(32)
    act(() => session.socket.receive({ type: "heartbeat_pong", nonce: wrongNonce }))

    await act(() => vi.advanceTimersByTimeAsync(9_999))
    expect(session.socket.close).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
  })

  it("does not let a duplicate prior pong clear the next heartbeat deadline", async () => {
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const firstPing = sentHeartbeats(session.socket)[0]!
    act(() => session.socket.receive({ type: "heartbeat_pong", nonce: firstPing.nonce }))

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const heartbeatFrames = sentHeartbeats(session.socket)
    expect(heartbeatFrames).toHaveLength(2)
    const secondPing = heartbeatFrames[1]!
    expect(secondPing.nonce).not.toBe(firstPing.nonce)
    act(() => session.socket.receive({ type: "heartbeat_pong", nonce: firstPing.nonce }))

    await act(() => vi.advanceTimersByTimeAsync(9_999))
    expect(session.socket.close).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
  })

  it("does not let a superseded socket acknowledge its replacement", async () => {
    const session = await connected({ currentUserId: "user-a" })
    const oldSocket = session.socket
    oldSocket.autoAcknowledgeHeartbeats = false
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const oldPings = sentHeartbeats(oldSocket)
    expect(oldPings).toHaveLength(1)
    const oldPing = oldPings[0]!

    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    await flush()
    const currentSocket = lastSocket()
    act(() => currentSocket.onopen?.())
    currentSocket.autoAcknowledgeHeartbeats = false

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const currentPings = sentHeartbeats(currentSocket)
    expect(currentPings).toHaveLength(1)
    const currentPing = currentPings[0]!
    expect(currentPing.nonce).not.toBe(oldPing.nonce)

    act(() => oldSocket.receive({ type: "heartbeat_pong", nonce: oldPing.nonce }))
    await act(() => vi.advanceTimersByTimeAsync(9_999))
    expect(currentSocket.close).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(currentSocket.close).toHaveBeenCalledExactlyOnceWith(4000, "heartbeat_timeout")
  })

  it("pauses in a hidden page and sends a fresh nonce when visibility resumes", async () => {
    const originalVisibility = Object.getOwnPropertyDescriptor(document, "visibilityState")
    const session = await connected()
    session.socket.autoAcknowledgeHeartbeats = false

    const changeVisibility = (state: DocumentVisibilityState) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, value: state })
      act(() => document.dispatchEvent(new Event("visibilitychange")))
    }

    try {
      changeVisibility("hidden")
      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(sentHeartbeats(session.socket)).toHaveLength(0)
      expect(session.socket.close).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)

      changeVisibility("visible")
      const firstPings = sentHeartbeats(session.socket)
      expect(firstPings).toHaveLength(1)
      const firstPing = firstPings[0]!
      expect(firstPing.nonce).toMatch(/^[0-9a-f]{32}$/)
      changeVisibility("hidden")
      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(session.socket.close).not.toHaveBeenCalled()

      changeVisibility("visible")
      const resumedPings = sentHeartbeats(session.socket)
      expect(resumedPings).toHaveLength(2)
      const secondPing = resumedPings[1]!
      expect(secondPing.nonce).not.toBe(firstPing.nonce)
      act(() => session.socket.receive({ type: "heartbeat_pong", nonce: firstPing.nonce }))
      await act(() => vi.advanceTimersByTimeAsync(9_999))
      expect(session.socket.close).not.toHaveBeenCalled()
      act(() => session.socket.receive({ type: "heartbeat_pong", nonce: secondPing.nonce }))
      await act(() => vi.advanceTimersByTimeAsync(10_000))
      expect(session.socket.close).not.toHaveBeenCalled()
    } finally {
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility)
      } else {
        Reflect.deleteProperty(document, "visibilityState")
      }
    }
  })

  it.each(["server close", "manual disconnect", "disabled", "account change", "logout", "unmount"])(
    "clears the heartbeat timer on %s",
    async (transition) => {
      const session = await connected({ currentUserId: "user-a" })
      const socket = session.socket
      socket.autoAcknowledgeHeartbeats = false

      if (transition === "server close") act(() => socket.close(1000))
      else if (transition === "manual disconnect") act(() => session.result.current.disconnect())
      else if (transition === "disabled")
        session.rerender({ enabled: false, currentUserId: "user-a" })
      else if (transition === "account change")
        session.rerender({ enabled: true, currentUserId: "user-b" })
      else if (transition === "logout")
        session.rerender({ enabled: false, currentUserId: undefined })
      else session.unmount()

      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(sentHeartbeats(socket)).toHaveLength(0)
      expect(vi.getTimerCount()).toBe(0)
    }
  )
})
