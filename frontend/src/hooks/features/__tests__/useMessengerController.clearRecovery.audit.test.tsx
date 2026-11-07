import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { focusManager, onlineManager, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, type ReactNode } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { Chat, ChatsListResponse, Message } from "@/api/chat"
import { createQueryClient } from "@/app/queryClient"
import { MessengerProvider } from "@/contexts/MessengerContext"
import { useMessenger } from "@/contexts/MessengerContextCore"
import { MessengerShellProvider } from "@/contexts/MessengerShellProvider"
import { WebSocketProvider } from "@/hooks/useChatWebSocket"
import { useMessengerController } from "../useMessengerController"

const ids = {
  chat: "11111111-1111-4111-8111-111111111111",
  message: "22222222-2222-4222-8222-222222222222",
  incoming: "33333333-3333-4333-8333-333333333333",
  me: "44444444-4444-4444-8444-444444444444",
  peer: "55555555-5555-4555-8555-555555555555",
  otherChat: "66666666-6666-4666-8666-666666666666",
  otherMessage: "77777777-7777-4777-8777-777777777777",
}

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    clearChat: vi.fn(),
    markRead: vi.fn(),
  },
  ticketPost: vi.fn(),
  navigate: vi.fn(),
}))
vi.mock("@/api/chat", () => ({ chatApi: mocks.chatApi }))
vi.mock("@/api/client", () => ({ default: { post: mocks.ticketPost, get: vi.fn() } }))
vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: async () => ({ messages: { upsert: async () => {} } }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ isAuth: true, user: { id: ids.me, full_name: "Me", role: "student" } }),
}))
vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ chatId: ids.chat }),
  useNavigate: () => mocks.navigate,
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))

class Socket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static instances: Socket[] = []
  readyState = Socket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  constructor(readonly url: string) {
    Socket.instances.push(this)
  }
  send() {}
  open() {
    this.readyState = Socket.OPEN
    this.onopen?.(new Event("open"))
  }
  frame(value: object) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent)
  }
  close() {
    this.readyState = Socket.CLOSED
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const original: Message = {
  id: ids.message,
  chat_id: ids.chat,
  sender_id: ids.me,
  content: "original",
  created_at: "2026-10-22T12:00:00.000Z",
  read_status: false,
  attachments: [],
}
const incoming: Message = {
  ...original,
  id: ids.incoming,
  sender_id: ids.peer,
  content: "received during clear",
  created_at: "2026-10-22T12:01:00.000Z",
}
const chat: Chat = {
  id: ids.chat,
  participants: [{ id: ids.peer, email: "peer@example.test", is_active: true }],
  unread_count: 1,
  last_message: original,
  created_at: original.created_at,
  updated_at: original.created_at,
}
const otherMessage = { ...original, id: ids.otherMessage, chat_id: ids.otherChat }
const otherChat: Chat = { ...chat, id: ids.otherChat, unread_count: 0, last_message: otherMessage }
const page = (items: Chat[]): ChatsListResponse => ({ items, has_more: false, next_cursor: null })
let shellUnread = -1
function ShellProbe() {
  const unread = useMessenger().unreadCount
  useEffect(() => {
    shellUnread = unread
  }, [unread])
  return null
}

beforeEach(() => {
  vi.resetAllMocks()
  Socket.instances = []
  shellUnread = -1
  vi.stubGlobal("WebSocket", Socket)
  mocks.ticketPost.mockResolvedValue({ data: { ticket: crypto.randomUUID(), expires_in: 15 } })
  mocks.chatApi.getChats.mockResolvedValue(page([chat, otherChat]))
  mocks.chatApi.getChat.mockResolvedValue(chat)
  mocks.chatApi.getMessages.mockResolvedValue({
    items: [original],
    has_more: false,
    next_cursor: null,
  })
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it.each([false, true])(
  "reconciles a committed clear after a failed refresh (presence update: %s)",
  async (withPresence) => {
    const wasFocused = focusManager.isFocused()
    const wasOnline = onlineManager.isOnline()
    focusManager.setFocused(false)
    onlineManager.setOnline(true)
    const client = createQueryClient()
    const clear = deferred<unknown>()
    const directRefresh = deferred<ChatsListResponse>()
    const heldMarkRead = deferred<unknown>()
    const otherMessages = { items: [otherMessage], has_more: false, next_cursor: null }
    let unmount: (() => void) | undefined
    try {
      const Wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>
          <WebSocketProvider>
            <MessengerProvider>{children}</MessengerProvider>
          </WebSocketProvider>
          <MessengerShellProvider>
            <ShellProbe />
          </MessengerShellProvider>
        </QueryClientProvider>
      )
      const hook = renderHook(
        () => ({ controller: useMessengerController(), messenger: useMessenger() }),
        { wrapper: Wrapper }
      )
      unmount = hook.unmount
      const { result } = hook
      await waitFor(() => expect(Socket.instances).toHaveLength(1))
      const socket = Socket.instances[0]!
      act(() => socket.open())
      await waitFor(() => expect(result.current.controller.messages).toHaveLength(1))
      await waitFor(() => expect(shellUnread).toBe(1), { timeout: 3000 })
      await waitFor(() => expect(client.isMutating()).toBe(0))
      await waitFor(() => expect(client.isFetching()).toBe(0))
      act(() => client.setQueryData(["messages", ids.otherChat], otherMessages))
      mocks.chatApi.clearChat.mockReturnValue(clear.promise)
      mocks.chatApi.markRead.mockReturnValue(heldMarkRead.promise)
      act(() => result.current.controller.handleClearChat())
      act(() => result.current.controller.confirmDialog!.onConfirm())
      await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
      act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
      await waitFor(() =>
        expect([result.current.messenger.unreadCount, shellUnread]).toEqual([1, 1])
      )

      // The server clears the message that arrived while the request was pending.
      mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
      const previousFetches = mocks.chatApi.getChats.mock.calls.length
      mocks.chatApi.getChats
        .mockReturnValueOnce(directRefresh.promise)
        .mockResolvedValue(page([{ ...chat, unread_count: 0, last_message: undefined }, otherChat]))
      await act(async () => {
        clear.resolve({ status: "cleared" })
        await clear.promise
      })
      await waitFor(() => expect(mocks.chatApi.getChats).toHaveBeenCalledTimes(previousFetches + 1))
      await act(async () => {
        directRefresh.reject(new Error("temporary chat refresh failure"))
        await directRefresh.promise.catch(() => {})
      })
      if (withPresence) {
        act(() =>
          socket.frame({ type: "presence", user_id: ids.peer, active: true, last_seen: null })
        )
        await waitFor(() =>
          expect(result.current.messenger.presenceMap[ids.peer]?.active).toBe(true)
        )
      }

      await act(async () => focusManager.setFocused(true))
      await waitFor(
        () => expect([result.current.messenger.unreadCount, shellUnread]).toEqual([0, 0]),
        { timeout: 2000 }
      )
      expect(
        result.current.controller.contacts.find((contact) => contact.id === ids.chat)?.lastMessage
      ).toBe("")
      expect(client.getQueryData<ChatsListResponse>(["chats"])?.items[1]?.id).toBe(ids.otherChat)
      expect(client.getQueryData(["messages", ids.otherChat])).toEqual(otherMessages)
    } finally {
      unmount?.()
      await act(async () => {
        clear.resolve({ status: "cleared" })
        directRefresh.resolve(page([chat, otherChat]))
        heldMarkRead.resolve({ success: true })
        await Promise.allSettled([clear.promise, directRefresh.promise, heldMarkRead.promise])
      })
      await client.cancelQueries()
      client.clear()
      focusManager.setFocused(wasFocused)
      onlineManager.setOnline(wasOnline)
    }
  }
)
