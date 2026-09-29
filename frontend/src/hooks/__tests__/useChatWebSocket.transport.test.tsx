import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode, useContext, useLayoutEffect, type ReactNode } from "react"
import { flushSync } from "react-dom"
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

  constructor(url: string) {
    this.url = url
    ScriptedWebSocket.instances.push(this)
  }

  send = vi.fn()

  close = vi.fn((code = 1000) => {
    this.readyState = ScriptedWebSocket.CLOSED
    this.onclose?.({ code } as CloseEvent)
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
  useChatWebSocket,
  WebSocketProvider,
  WebSocketStoreContext,
  type UseChatWebSocketOptions,
} from "../useChatWebSocket"

const CHAT = "chat-a"
const OTHER_CHAT = "chat-b"
const TICKET = { data: { ticket: "ticket-1", expires_in: 15 } }

const flush = () => act(() => vi.advanceTimersByTimeAsync(0))
const sockets = () => ScriptedWebSocket.instances
const lastSocket = () => sockets().at(-1)!

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
      expect(vi.getTimerCount()).toBe(baselineTimers)
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
    ["message_deleted", { message_id: "m-1", deleted_at: "2026-08-25T12:00:00Z" }],
    ["reaction_changed", { message_id: "m-1", emoji: "👍", action: "added", user_id: "peer" }],
  ])("marks the chat history stale without refetching on %s", async (type, fields) => {
    const { socket, invalidateQueries } = await connected()

    act(() => socket.receive({ type, chat_id: CHAT, ...fields }))

    expect(invalidateQueries).toHaveBeenCalledExactlyOnceWith({
      queryKey: ["messages", CHAT],
      refetchType: "none",
    })
  })

  it("handles read, online and presence frames without optional handlers", async () => {
    const { socket } = await connected()

    act(() => {
      socket.receive({ type: "read", chat_id: CHAT, user_id: "peer", read_at: null })
      socket.receive({ type: "online", user_id: "peer", status: true })
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

    act(() => socket.receive({ type: "error", ...fields }))

    expect(invalidateQueries).not.toHaveBeenCalled()
    act(() => result.current.sendJoin(CHAT))
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({ type: "join", room: CHAT, resume_token: "t3" })
    )
  })

  it.each([
    ["no stream sequence", { chat_id: CHAT, resume_token: "t9" }],
    ["no resume token", { chat_id: CHAT, stream_seq: 9 }],
    ["no chat", { stream_seq: 9, resume_token: "t9" }],
  ])("stores no checkpoint for a frame with %s", async (_label, fields) => {
    const { socket, result } = await connected({ currentUserId: "me" })

    act(() => socket.receive({ type: "online", user_id: "peer", status: true, ...fields }))

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
