import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MessengerProvider } from "@/contexts/MessengerContext"
import { useMessenger } from "@/contexts/MessengerContextCore"
import { WebSocketProvider } from "@/hooks/useChatWebSocket"
import type { Chat, Message, MessagesListResponse } from "@/api/chat"
import { useMessengerController } from "@/hooks/features/useMessengerController"

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    sendMessage: vi.fn(),
    markRead: vi.fn(),
    createChat: vi.fn(),
    createGroup: vi.fn(),
    forwardMessages: vi.fn(),
    renameChat: vi.fn(),
    clearChat: vi.fn(),
    deleteChat: vi.fn(),
    editMessage: vi.fn(),
    deleteMessage: vi.fn(),
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
    getReactors: vi.fn(),
    sendTyping: vi.fn(),
    renameGroup: vi.fn(),
    addParticipant: vi.fn(),
    removeParticipant: vi.fn(),
  },
  ticketPost: vi.fn(),
  navigate: vi.fn(),
  user: {
    id: "user-1",
    email: "user@example.test",
    full_name: "Current User",
    avatar_url: null,
    is_active: true,
    role: "student",
  },
}))

vi.mock("@/api/chat", () => ({ chatApi: mocks.chatApi }))
vi.mock("@/api/client", () => ({
  default: {
    post: mocks.ticketPost,
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, isAuth: true, loading: false }),
}))
vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ chatId: "chat-current" }),
  useNavigate: () => mocks.navigate,
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))

class ControlledWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: ControlledWebSocket[] = []

  readyState = ControlledWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  readonly sent: string[] = []

  constructor(readonly url: string) {
    ControlledWebSocket.instances.push(this)
  }

  send(data: string) {
    if (this.readyState !== ControlledWebSocket.OPEN) throw new Error("socket is not open")
    this.sent.push(data)
  }

  open() {
    this.readyState = ControlledWebSocket.OPEN
    this.onopen?.(new Event("open"))
  }

  loseConnection(code = 1006) {
    this.readyState = ControlledWebSocket.CLOSED
    this.onclose?.({ code, reason: "network interruption", wasClean: false } as CloseEvent)
  }

  close(code = 1000, reason = "") {
    if (this.readyState === ControlledWebSocket.CLOSED) return
    this.readyState = ControlledWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: true } as CloseEvent)
  }
}

const chat: Chat = {
  id: "chat-current",
  participants: [
    { id: "user-1", full_name: "Current User" } as Chat["participants"][number],
    { id: "peer-1", full_name: "Peer" } as Chat["participants"][number],
  ],
  unread_count: 0,
  created_at: "2026-10-22T12:00:00.000Z",
  updated_at: "2026-10-22T12:00:00.000Z",
}

const initialMessage: Message = {
  id: "msg-before-disconnect",
  chat_id: chat.id,
  sender_id: "peer-1",
  content: "Before interruption",
  created_at: "2026-10-22T12:01:00.000Z",
  read_status: false,
  attachments: [],
}
const missedMessage: Message = {
  id: "msg-delivered-by-rest",
  chat_id: chat.id,
  sender_id: "peer-1",
  content: "Sent while disconnected",
  created_at: "2026-10-22T12:02:00.000Z",
  read_status: false,
  attachments: [],
}

let exposeMissedMessage = false
let isTransportConnected = false
let originalWebSocket: PropertyDescriptor | undefined
let originalOnline: PropertyDescriptor | undefined

function ConnectionProbe() {
  const { isConnected } = useMessenger()
  useEffect(() => {
    isTransportConnected = isConnected
  }, [isConnected])
  return null
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <MessengerProvider>
            <ConnectionProbe />
            {children}
          </MessengerProvider>
        </WebSocketProvider>
      </QueryClientProvider>
    )
  }
}

const framesOfType = (socket: ControlledWebSocket, type: string) =>
  socket.sent
    .map((value) => JSON.parse(value) as { type: string; room?: string })
    .filter((frame) => frame.type === type)

beforeEach(() => {
  exposeMissedMessage = false
  isTransportConnected = false
  ControlledWebSocket.instances = []
  originalWebSocket = Object.getOwnPropertyDescriptor(globalThis, "WebSocket")
  originalOnline = Object.getOwnPropertyDescriptor(navigator, "onLine")
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    writable: true,
    value: ControlledWebSocket,
  })
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true })
  vi.spyOn(Math, "random").mockReturnValue(0)

  mocks.ticketPost.mockResolvedValue({ data: { ticket: "single-use-test-ticket", expires_in: 15 } })
  mocks.chatApi.getChats.mockResolvedValue({ items: [chat], has_more: false, next_cursor: null })
  mocks.chatApi.getMessages.mockImplementation(async (): Promise<MessagesListResponse> => ({
    items: exposeMissedMessage ? [initialMessage, missedMessage] : [initialMessage],
    has_more: false,
    next_cursor: null,
  }))
  mocks.chatApi.getChat.mockResolvedValue(chat)
  mocks.chatApi.sendMessage.mockResolvedValue({ ...initialMessage, id: "msg-sent" })
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
  mocks.chatApi.createChat.mockResolvedValue(chat)
  mocks.chatApi.clearChat.mockResolvedValue({ status: "ok" })
  mocks.chatApi.deleteChat.mockResolvedValue({ status: "ok" })
  mocks.chatApi.editMessage.mockResolvedValue({ status: "ok" })
  mocks.chatApi.deleteMessage.mockResolvedValue({ status: "ok" })
  mocks.chatApi.addReaction.mockResolvedValue({ status: "ok" })
  mocks.chatApi.removeReaction.mockResolvedValue({ status: "ok" })
  mocks.chatApi.getReactors.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  if (originalOnline) Object.defineProperty(navigator, "onLine", originalOnline)
  else Reflect.deleteProperty(navigator, "onLine")
  if (originalWebSocket) {
    Object.defineProperty(globalThis, "WebSocket", originalWebSocket)
  } else {
    Reflect.deleteProperty(globalThis, "WebSocket")
  }
})

describe("MessengerProvider + controller + WebSocket reconnect", () => {
  it("clears the disconnected room, rejoins the current chat once, and refetches messages missed during downtime", async () => {
    const { result } = renderHook(() => useMessengerController(), { wrapper: createWrapper() })

    await waitFor(() => expect(ControlledWebSocket.instances).toHaveLength(1))
    const firstSocket = ControlledWebSocket.instances[0]!
    await act(async () => {
      firstSocket.open()
      await Promise.resolve()
    })
    await waitFor(() => expect(isTransportConnected).toBe(true))
    await waitFor(() =>
      expect(result.current.messages.map((message) => message.id)).toContain(initialMessage.id)
    )
    const initialFetchCount = mocks.chatApi.getMessages.mock.calls.length
    expect(initialFetchCount).toBeGreaterThan(0)
    const initialJoins = framesOfType(firstSocket, "join")
    expect(initialJoins.length).toBeGreaterThan(0)
    expect(initialJoins.every((frame) => frame.room === chat.id)).toBe(true)

    exposeMissedMessage = true
    await act(async () => {
      firstSocket.loseConnection()
      await Promise.resolve()
    })
    await waitFor(() => expect(isTransportConnected).toBe(false))
    await waitFor(() => expect(ControlledWebSocket.instances).toHaveLength(2))
    const reconnectSocket = ControlledWebSocket.instances[1]!
    await act(async () => {
      reconnectSocket.open()
      await Promise.resolve()
    })

    await waitFor(() => expect(isTransportConnected).toBe(true))
    await waitFor(() =>
      expect(result.current.messages.map((message) => message.id)).toContain(missedMessage.id)
    )

    const reconnectJoins = framesOfType(reconnectSocket, "join")
    expect(reconnectJoins).toEqual([{ type: "join", room: chat.id }])
    const reconnectFetches = mocks.chatApi.getMessages.mock.calls.slice(initialFetchCount)
    expect(reconnectFetches.some(([chatId]) => chatId === chat.id)).toBe(true)
  })
})

it("recovers missed messages after disabled replay rejects the saved cursor", async () => {
  const { clearReplayCheckpoints, peekReplayCheckpoint, writeReplayCheckpoint } =
    await import("@/hooks/chatReplayCheckpoints")
  const { withExpectedConsole } = await import("@/tests/strictConsole")
  const session = renderHook(
    () => ({ controller: useMessengerController(), messenger: useMessenger() }),
    { wrapper: createWrapper() }
  )
  try {
    // Core-NATS mode rejects the old stream token but retains authorized live membership.
    writeReplayCheckpoint(mocks.user.id, chat.id, 12, "saved-cursor", chat.id)
    await waitFor(() => expect(ControlledWebSocket.instances).toHaveLength(1))
    const socket = ControlledWebSocket.instances[0]!
    await act(async () => {
      socket.open()
      await Promise.resolve()
    })
    await waitFor(() => expect(isTransportConnected).toBe(true))
    await waitFor(() =>
      expect(session.result.current.controller.messages.map(({ id }) => id)).toEqual([
        initialMessage.id,
      ])
    )
    expect(framesOfType(socket, "join")).toContainEqual({
      type: "join",
      room: chat.id,
      resume_token: "saved-cursor",
    })
    expect(peekReplayCheckpoint(mocks.user.id, chat.id)).toEqual({
      sequence: 12,
      resumeToken: "saved-cursor",
    })
    const initialFetchCount = mocks.chatApi.getMessages.mock.calls.length
    expect(initialFetchCount).toBeGreaterThan(0)

    // No reconnect or explicit refetch: the real parsed server error must cause recovery.
    exposeMissedMessage = true
    await withExpectedConsole(
      "error",
      (args) => {
        expect(args).toStrictEqual([
          "[WebSocket] Server error:",
          {
            type: "error",
            room: chat.id,
            code: "invalid_resume_token",
            detail: "resume token is invalid or expired",
          },
        ])
        return true
      },
      () =>
        act(async () => {
          socket.onmessage?.({
            data: JSON.stringify({
              type: "error",
              room: chat.id,
              code: "invalid_resume_token",
              detail: "resume token is invalid or expired",
            }),
          } as MessageEvent)
          await Promise.resolve()
        }),
      1
    )
    await waitFor(() =>
      expect(session.result.current.controller.messages.map(({ id }) => id)).toEqual([
        initialMessage.id,
        missedMessage.id,
      ])
    )
    expect(
      session.result.current.controller.messages.filter(({ id }) => id === missedMessage.id)
    ).toHaveLength(1)
    expect(
      session.result.current.controller.messages.find(({ id }) => id === missedMessage.id)?.text
    ).toBe(missedMessage.content)
    expect(mocks.chatApi.getMessages.mock.calls.slice(initialFetchCount)).toContainEqual([
      chat.id,
      undefined,
      50,
      expect.any(AbortSignal),
    ])
    expect(peekReplayCheckpoint(mocks.user.id, chat.id)).toBeUndefined()
    expect(ControlledWebSocket.instances).toEqual([socket])
    expect(socket.readyState).toBe(ControlledWebSocket.OPEN)
    expect(isTransportConnected).toBe(true)

    act(() => session.result.current.messenger.sendJoin(chat.id))
    expect(framesOfType(socket, "join").at(-1)).toEqual({ type: "join", room: chat.id })
  } finally {
    try {
      clearReplayCheckpoints(mocks.user.id)
    } finally {
      session.unmount()
    }
  }
})
