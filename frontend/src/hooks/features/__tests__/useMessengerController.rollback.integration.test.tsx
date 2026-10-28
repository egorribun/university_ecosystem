import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Chat, Message, MessagesListResponse } from "@/api/chat"
import { MessengerProvider } from "@/contexts/MessengerContext"
import { useMessenger } from "@/contexts/MessengerContextCore"
import { MessengerShellProvider } from "@/contexts/MessengerShellProvider"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import { WebSocketProvider } from "@/hooks/useChatWebSocket"
import { createSessionMutationCache } from "@/app/sessionMutationCache"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

const ids = {
  chat: "11111111-1111-4111-8111-111111111111",
  message: "22222222-2222-4222-8222-222222222222",
  incoming: "33333333-3333-4333-8333-333333333333",
  me: "44444444-4444-4444-8444-444444444444",
  peer: "55555555-5555-4555-8555-555555555555",
}

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    markRead: vi.fn(),
    clearChat: vi.fn(),
    deleteChat: vi.fn(),
    editMessage: vi.fn(),
    deleteMessage: vi.fn(),
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
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
  useAuth: () => ({ isAuth: true, user: { id: ids.me, full_name: "Me", role: "admin" } }),
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

function deferred() {
  let resolve!: (value: unknown) => void
  let reject!: (error: Error) => void
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

const message: Message = {
  id: ids.message,
  chat_id: ids.chat,
  sender_id: ids.me,
  content: "original",
  created_at: "2026-10-22T12:00:00.000Z",
  read_status: false,
  attachments: [],
  reactions: [],
}
const incoming: Message = {
  ...message,
  id: ids.incoming,
  sender_id: ids.peer,
  content: "peer arrived",
  created_at: "2026-10-22T12:01:00.000Z",
}
const chat: Chat = {
  id: ids.chat,
  participants: [],
  unread_count: 1,
  last_message: message,
  created_at: message.created_at,
  updated_at: message.created_at,
}
let shellUnread = -1
function ShellProbe() {
  const unread = useMessenger().unreadCount
  useEffect(() => {
    shellUnread = unread
  }, [unread])
  return null
}

async function setup() {
  const queryClient = new QueryClient({
    mutationCache: createSessionMutationCache(),
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <MessengerProvider>{children}</MessengerProvider>
        </WebSocketProvider>
        <MessengerShellProvider>
          <ShellProbe />
        </MessengerShellProvider>
      </QueryClientProvider>
    )
  }
  const hook = renderHook(
    () => ({ controller: useMessengerController(), unread: useMessenger().unreadCount }),
    { wrapper: Wrapper }
  )
  await waitFor(() => expect(Socket.instances).toHaveLength(1))
  await act(async () => {
    Socket.instances[0]!.open()
  })
  await waitFor(() => expect(hook.result.current.controller.messages).toHaveLength(1))
  await waitFor(() => expect(shellUnread).toBe(1), { timeout: 3000 })
  return { ...hook, queryClient, socket: Socket.instances[0]! }
}

beforeEach(() => {
  vi.resetAllMocks()
  Socket.instances = []
  shellUnread = -1
  vi.stubGlobal("WebSocket", Socket)
  mocks.ticketPost.mockResolvedValue({ data: { ticket: "test-ticket", expires_in: 15 } })
  mocks.chatApi.getChats.mockResolvedValue({ items: [chat], has_more: false, next_cursor: null })
  mocks.chatApi.getChat.mockResolvedValue(chat)
  mocks.chatApi.getMessages.mockResolvedValue({
    items: [message],
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

describe("messenger mutation rollback with live transport", () => {
  it("keeps an accepted deletion when the optimistic deletion fails", async () => {
    const pending = deferred()
    mocks.chatApi.deleteMessage.mockReturnValue(pending.promise)
    const { result, socket, queryClient } = await setup()
    act(() => result.current.controller.handleDeleteMessage(ids.message))
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages[0]?.deletedAt).toBeTruthy())
    const deletedAt = result.current.controller.messages[0]!.deletedAt!
    act(() =>
      socket.frame({
        type: "message_deleted",
        chat_id: ids.chat,
        message_id: ids.message,
        deleted_at: deletedAt,
      })
    )
    await act(async () => {
      pending.reject(new Error("refused"))
      await pending.promise.catch(() => {})
    })
    await waitFor(() => expect(result.current.controller.messages[0]?.deletedAt).toBe(deletedAt))
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
    ).toBe("")
  })

  it("keeps a peer reaction when the actor's pending reaction fails", async () => {
    const pending = deferred()
    mocks.chatApi.addReaction.mockReturnValue(pending.promise)
    const { result, socket } = await setup()
    act(() => result.current.controller.handleToggleReaction(ids.message, "👍"))
    await waitFor(
      () =>
        expect(result.current.controller.messages[0]?.reactions).toEqual([
          { emoji: "👍", count: 1, reactedByMe: true },
        ]),
      { timeout: 2000 }
    )
    act(() =>
      socket.frame({
        type: "reaction_changed",
        chat_id: ids.chat,
        message_id: ids.message,
        user_id: ids.peer,
        emoji: "👍",
        action: "added",
      })
    )
    await act(async () => {
      pending.reject(new Error("refused"))
      await pending.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.reactions).toEqual([
        { emoji: "👍", count: 1, reactedByMe: false },
      ])
    )
  })

  it("keeps an acknowledged actor reaction when the HTTP request fails", async () => {
    const pending = deferred()
    mocks.chatApi.addReaction.mockReturnValue(pending.promise)
    const { result, socket, queryClient } = await setup()
    act(() => result.current.controller.handleToggleReaction(ids.message, "👍"))
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.reactions).toEqual([
        { emoji: "👍", count: 1, reactedByMe: true },
      ])
    )
    act(() =>
      socket.frame({
        type: "reaction_changed",
        chat_id: ids.chat,
        message_id: ids.message,
        user_id: ids.me,
        emoji: "👍",
        action: "added",
      })
    )
    await act(async () => {
      pending.reject(new Error("response lost"))
      await pending.promise.catch(() => {})
    })
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
    await waitFor(
      () =>
        expect(result.current.controller.messages[0]?.reactions).toEqual([
          { emoji: "👍", count: 1, reactedByMe: true },
        ]),
      { timeout: 2000 }
    )
  })

  it("reconciles reactions from a later server refresh", async () => {
    const { result } = await setup()
    mocks.chatApi.getMessages.mockResolvedValueOnce({
      items: [{ ...message, reactions: [{ emoji: "👍", count: 3, reacted_by_me: false }] }],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      await result.current.controller.refetchMessages()
    })
    await waitFor(
      () =>
        expect(result.current.controller.messages[0]?.reactions).toEqual([
          { emoji: "👍", count: 3, reactedByMe: false },
        ]),
      { timeout: 2000 }
    )
  })

  it("keeps a peer reaction delivered during an older server refresh", async () => {
    const refresh = deferred()
    const { result, socket } = await setup()
    const previousFetches = mocks.chatApi.getMessages.mock.calls.length
    mocks.chatApi.getMessages.mockReturnValueOnce(refresh.promise)
    act(() => {
      void result.current.controller.refetchMessages()
    })
    await waitFor(() =>
      expect(mocks.chatApi.getMessages.mock.calls.length).toBeGreaterThan(previousFetches)
    )
    act(() =>
      socket.frame({
        type: "reaction_changed",
        chat_id: ids.chat,
        message_id: ids.message,
        user_id: ids.peer,
        emoji: "👍",
        action: "added",
      })
    )
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.reactions).toEqual([
        { emoji: "👍", count: 1, reactedByMe: false },
      ])
    )
    await act(async () => {
      refresh.resolve({ items: [message], has_more: false, next_cursor: null })
      await refresh.promise
    })
    expect(result.current.controller.messages[0]?.reactions).toEqual([
      { emoji: "👍", count: 1, reactedByMe: false },
    ])
  })

  it("keeps new messages and consistent provider badges after a failed clear", async () => {
    const pending = deferred()
    mocks.chatApi.clearChat.mockReturnValue(pending.promise)
    const { result, socket } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([0, 0]))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toContain(ids.incoming)
    )
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([1, 1]))
    await act(async () => {
      pending.reject(new Error("refused"))
      await pending.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toEqual([
        ids.message,
        ids.incoming,
      ])
    )
    expect([result.current.unread, shellUnread]).toEqual([2, 2])
  })

  it("restores an accepted edit after overlapping edit and delete failures", async () => {
    const edit = deferred()
    const deletion = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    mocks.chatApi.deleteMessage.mockReturnValue(deletion.promise)
    const { result, socket } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("failed draft"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("failed draft"))
    act(() => result.current.controller.handleDeleteMessage(ids.message))
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages[0]?.deletedAt).toBeTruthy())
    act(() =>
      socket.frame({
        type: "message_edited",
        chat_id: ids.chat,
        message_id: ids.message,
        content: "accepted elsewhere",
        edited_at: "2026-10-23T12:00:00.000Z",
      })
    )
    await act(async () => {
      edit.reject(new Error("refused"))
      await edit.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.editingMessageContent).toBe("failed draft")
    )
    await act(async () => {
      deletion.reject(new Error("refused"))
      await deletion.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.messages[0]).toMatchObject({
        text: "accepted elsewhere",
        deletedAt: null,
      })
    )
  })

  it("keeps a live edit when starting a mutation cancels an in-flight refresh", async () => {
    const refresh = deferred()
    const deletion = deferred()
    mocks.chatApi.deleteMessage.mockReturnValue(deletion.promise)
    const { result, socket, queryClient } = await setup()
    mocks.chatApi.getMessages.mockReturnValueOnce(refresh.promise)
    act(() => {
      void result.current.controller.refetchMessages()
    })
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(1)
    )
    act(() =>
      socket.frame({
        type: "message_edited",
        chat_id: ids.chat,
        message_id: ids.message,
        content: "live while fetching",
        edited_at: "2026-10-23T12:00:00.000Z",
      })
    )
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.text).toBe("live while fetching")
    )
    act(() => result.current.controller.handleDeleteMessage(ids.message))
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages[0]?.deletedAt).toBeTruthy())
    await act(async () => {
      deletion.reject(new Error("refused"))
      await deletion.promise.catch(() => {})
    })
    await waitFor(
      () => expect(result.current.controller.messages[0]?.text).toBe("live while fetching"),
      { timeout: 2000 }
    )
  })

  it("restores a hidden chat with its live peer message when delete fails", async () => {
    const deletion = deferred()
    mocks.chatApi.deleteChat.mockReturnValue(deletion.promise)
    const { result, socket, queryClient } = await setup()
    // Keep the post-arrival read request pending so its unrelated refetch cannot
    // replace the transport state under test with the fixed REST fixture.
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleDeleteChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.contacts).toHaveLength(0))
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([0, 0]))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() =>
      expect(
        queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items
      ).toHaveLength(2)
    )
    expect(
      queryClient.getQueryData<{ items: Chat[] }>(["chats"])?.items[0]?.last_message?.content
    ).toBe("peer arrived")
    await act(async () => {
      deletion.reject(new Error("refused"))
      await deletion.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.contacts[0]?.lastMessage).toBe("peer arrived")
    )
    expect([result.current.unread, shellUnread]).toEqual([2, 2])
  })

  it("hides the direct-link chat fallback while deletion is pending", async () => {
    const deletion = deferred()
    mocks.chatApi.deleteChat.mockReturnValue(deletion.promise)
    const { result, queryClient } = await setup()
    act(() =>
      queryClient.setQueryData(["chats"], { items: [], has_more: false, next_cursor: null })
    )
    await waitFor(() => expect(result.current.controller.activeChat?.id).toBe(ids.chat))
    act(() => result.current.controller.handleDeleteChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.activeChat).toBeNull(), { timeout: 2000 })
    await act(async () => {
      deletion.reject(new Error("refused"))
      await deletion.promise.catch(() => {})
    })
    await waitFor(() => expect(result.current.controller.activeChat?.id).toBe(ids.chat))
  })

  it("retires a successful clear at its cutoff while preserving later peer messages", async () => {
    const clear = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket, queryClient } = await setup()
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toEqual([ids.incoming])
    )
    mocks.chatApi.getMessages.mockResolvedValueOnce({
      items: [incoming],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(() =>
      expect(
        queryClient
          .getQueryData<MessagesListResponse>(["messages", ids.chat])
          ?.items.map((item) => item.id)
      ).toEqual([ids.incoming])
    )
    // A later authoritative cache write is no longer masked by a retired clear.
    act(() =>
      queryClient.setQueryData(["messages", ids.chat], {
        items: [message, incoming],
        has_more: false,
        next_cursor: null,
      })
    )
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toEqual([
        ids.message,
        ids.incoming,
      ])
    )
  })

  it("reconciles messages that the server cleared after they arrived locally", async () => {
    const clear = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toEqual([ids.incoming])
    )
    mocks.chatApi.getMessages.mockResolvedValueOnce({
      items: [],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0), {
      timeout: 2000,
    })
  })

  it("reconciles both unread badges when the server cleared an in-flight peer message", async () => {
    const clear = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket, queryClient } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([1, 1]))
    mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
    mocks.chatApi.getChats.mockResolvedValue({
      items: [{ ...chat, unread_count: 0, last_message: undefined }],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(0)
    )
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([0, 0]), {
      timeout: 2000,
    })
    expect(result.current.controller.contacts[0]?.lastMessage).toBe("")
  })

  it("retries the chat refresh if a peer message arrives during that refresh", async () => {
    const clear = deferred()
    const chatsRefresh = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
    const previousFetches = mocks.chatApi.getChats.mock.calls.length
    mocks.chatApi.getChats.mockReturnValueOnce(chatsRefresh.promise).mockResolvedValueOnce({
      items: [{ ...chat, unread_count: 1, last_message: incoming }],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(
      () => expect(mocks.chatApi.getChats.mock.calls.length).toBeGreaterThan(previousFetches),
      { timeout: 2000 }
    )
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([1, 1]))
    await act(async () => {
      chatsRefresh.resolve({
        items: [{ ...chat, unread_count: 0, last_message: undefined }],
        has_more: false,
        next_cursor: null,
      })
      await chatsRefresh.promise
    })
    await waitFor(
      () => expect(mocks.chatApi.getChats.mock.calls.length).toBeGreaterThan(previousFetches + 1),
      { timeout: 2000 }
    )
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([1, 1]))
    expect(result.current.controller.contacts[0]?.lastMessage).toBe("peer arrived")
  })

  it("reconciles after repeated chat refresh collisions once peer traffic becomes quiet", async () => {
    const clear = deferred()
    const refreshes = [deferred(), deferred(), deferred()]
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([1, 1]))
    mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
    const later = [
      { ...incoming, id: "66666666-6666-4666-8666-666666666666", created_at: "2026-10-22T12:02:00.000Z" },
      { ...incoming, id: "77777777-7777-4777-8777-777777777777", created_at: "2026-10-22T12:03:00.000Z" },
      { ...incoming, id: "88888888-8888-4888-8888-888888888888", created_at: "2026-10-22T12:04:00.000Z" },
    ]
    const previousFetches = mocks.chatApi.getChats.mock.calls.length
    for (const refresh of refreshes) mocks.chatApi.getChats.mockReturnValueOnce(refresh.promise)
    mocks.chatApi.getChats.mockResolvedValueOnce({ items: [{ ...chat, unread_count: 3, last_message: later[2] }], has_more: false, next_cursor: null })
    await act(async () => { clear.resolve({ status: "cleared" }); await clear.promise })
    for (let index = 0; index < refreshes.length; index += 1) {
      await waitFor(() => expect(mocks.chatApi.getChats.mock.calls.length).toBeGreaterThan(previousFetches + index), { timeout: 2000 })
      act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: later[index] }))
      await act(async () => {
        refreshes[index]!.resolve({ items: [{ ...chat, unread_count: 0, last_message: undefined }], has_more: false, next_cursor: null })
        await refreshes[index]!.promise
      })
    }
    await waitFor(() => expect(mocks.chatApi.getChats.mock.calls.length).toBeGreaterThan(previousFetches + 3), { timeout: 3000 })
    await waitFor(() => expect([result.current.unread, shellUnread]).toEqual([3, 3]), { timeout: 3000 })
  })

  it("does not resurrect pre-clear messages from a stale post-clear response", async () => {
    const clear = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, queryClient } = await setup()
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    // The server response is stale and still contains the already-cleared row.
    const previousFetches = mocks.chatApi.getMessages.mock.calls.length
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [message],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(() =>
      expect(mocks.chatApi.getMessages.mock.calls.length).toBeGreaterThan(previousFetches)
    )
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(0)
    )
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0), {
      timeout: 2000,
    })
  })

  it("keeps the first clear cutoff when another clear succeeds before stale history recovers", async () => {
    const first = deferred()
    const second = deferred()
    mocks.chatApi.clearChat.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result, queryClient } = await setup()
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [message],
      has_more: false,
      next_cursor: null,
    })
    mocks.chatApi.getChats.mockResolvedValue({
      items: [{ ...chat, unread_count: 0, last_message: undefined }],
      has_more: false,
      next_cursor: null,
    })
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    const initialFetches = mocks.chatApi.getMessages.mock.calls.length
    await act(async () => {
      first.resolve({ status: "cleared" })
      await first.promise
    })
    await waitFor(() =>
      expect(mocks.chatApi.getMessages.mock.calls.length).toBeGreaterThan(initialFetches)
    )
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(0)
    )
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
    expect(result.current.controller.messages).toHaveLength(0)
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(mocks.chatApi.clearChat).toHaveBeenCalledTimes(2))
    const secondFetches = mocks.chatApi.getMessages.mock.calls.length
    await act(async () => {
      second.resolve({ status: "cleared" })
      await second.promise
    })
    await waitFor(() =>
      expect(mocks.chatApi.getMessages.mock.calls.length).toBeGreaterThan(secondFetches)
    )
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(0)
    )
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0), {
      timeout: 2000,
    })
  })

  it("keeps messages received while the post-clear refresh is in flight", async () => {
    const clear = deferred()
    const refresh = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, socket, queryClient } = await setup()
    mocks.chatApi.markRead.mockReturnValue(new Promise(() => {}))
    act(() => result.current.controller.handleClearChat())
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
    mocks.chatApi.getMessages.mockReturnValueOnce(refresh.promise)
    await act(async () => {
      clear.resolve({ status: "cleared" })
      await clear.promise
    })
    await waitFor(
      () => expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(1),
      { timeout: 2000 }
    )
    act(() => socket.frame({ type: "new_message", chat_id: ids.chat, message: incoming }))
    await waitFor(() =>
      expect(result.current.controller.messages.map((item) => item.id)).toEqual([ids.incoming])
    )
    await act(async () => {
      refresh.resolve({ items: [], has_more: false, next_cursor: null })
      await refresh.promise
    })
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["messages", ids.chat] })).toBe(0)
    )
    expect(result.current.controller.messages.map((item) => item.id)).toEqual([ids.incoming])
  })

  it("keeps a pending projection after mutation-cache removal and retires it on failure", async () => {
    const deletion = deferred()
    mocks.chatApi.deleteMessage.mockReturnValue(deletion.promise)
    const { result, queryClient, socket } = await setup()
    act(() => result.current.controller.handleDeleteMessage(ids.message))
    act(() => result.current.controller.confirmDialog!.onConfirm())
    await waitFor(() => expect(result.current.controller.messages[0]?.deletedAt).toBeTruthy())
    act(() => queryClient.getMutationCache().clear())
    act(() =>
      socket.frame({
        type: "message_edited",
        chat_id: ids.chat,
        message_id: ids.message,
        content: "new authoritative text",
        edited_at: "2026-10-23T12:00:00.000Z",
      })
    )
    await act(async () => {
      deletion.reject(new Error("refused"))
      await deletion.promise.catch(() => {})
    })
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.text).toBe("new authoritative text")
    )
  })

  it("sends opposing same-tick reactions in order and preserves the peer delta", async () => {
    const add = deferred()
    const remove = deferred()
    mocks.chatApi.addReaction.mockReturnValue(add.promise)
    mocks.chatApi.removeReaction.mockReturnValue(remove.promise)
    const { result, socket } = await setup()
    act(() => {
      result.current.controller.handleToggleReaction(ids.message, "👍")
      result.current.controller.handleToggleReaction(ids.message, "👍")
    })
    await waitFor(() => expect(mocks.chatApi.addReaction).toHaveBeenCalledOnce())
    expect(mocks.chatApi.removeReaction).not.toHaveBeenCalled()
    act(() =>
      socket.frame({
        type: "reaction_changed",
        chat_id: ids.chat,
        message_id: ids.message,
        user_id: ids.peer,
        emoji: "👍",
        action: "added",
      })
    )
    await act(async () => {
      add.resolve({ status: "ok" })
      await add.promise
    })
    await waitFor(() => expect(mocks.chatApi.removeReaction).toHaveBeenCalledOnce())
    await act(async () => {
      remove.resolve({ status: "ok" })
      await remove.promise
    })
    await waitFor(() =>
      expect(result.current.controller.messages[0]?.reactions).toEqual([
        { emoji: "👍", count: 1, reactedByMe: false },
      ])
    )
  })

  it("sends overlapping edits in the order the user submitted them", async () => {
    const first = deferred()
    const second = deferred()
    mocks.chatApi.editMessage.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result, queryClient } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("first"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("first"))
    act(() => result.current.controller.handleEditMessage(ids.message, "first"))
    act(() => result.current.controller.setEditingMessageContent("second"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("second"))
    expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(1)
    for (const mutation of queryClient.getMutationCache().getAll()) {
      expect(JSON.stringify(mutation.state.variables)).not.toContain("receipt")
    }
    await act(async () => {
      first.resolve({ status: "ok" })
      await first.promise
    })
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.resolve({ status: "ok" })
      await second.promise
    })
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("second"))
  })

  it("keeps a later queued edit visible when the earlier edit is echoed", async () => {
    const first = deferred()
    const second = deferred()
    mocks.chatApi.editMessage.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result, socket, queryClient } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("first"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(1))
    act(() => result.current.controller.handleEditMessage(ids.message, "first"))
    act(() => result.current.controller.setEditingMessageContent("second"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("second"))
    act(() =>
      socket.frame({
        type: "message_edited",
        chat_id: ids.chat,
        message_id: ids.message,
        content: "first",
        edited_at: "2026-10-23T12:00:00.000Z",
      })
    )
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("second"), {
      timeout: 2000,
    })
    await act(async () => {
      first.resolve({ status: "ok" })
      await first.promise
    })
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.resolve({ status: "ok" })
      await second.promise
    })
    await waitFor(
      () =>
        expect(
          queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
        ).toBe("second"),
      { timeout: 2000 }
    )
  })

  it("uses refreshed server text as the baseline when a queued edit starts", async () => {
    const first = deferred()
    const second = deferred()
    mocks.chatApi.editMessage.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result, queryClient } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("first"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(1))
    act(() => result.current.controller.handleEditMessage(ids.message, "first"))
    act(() => result.current.controller.setEditingMessageContent("second"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("second"))
    mocks.chatApi.getMessages.mockResolvedValueOnce({
      items: [{ ...message, content: "server edit", edited_at: "2026-10-23T12:00:00.000Z" }],
      has_more: false,
      next_cursor: null,
    })
    await act(async () => {
      await result.current.controller.refetchMessages()
    })
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
    ).toBe("server edit")
    await act(async () => {
      first.reject(new Error("refused"))
      await first.promise.catch(() => {})
    })
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.resolve({ status: "ok" })
      await second.promise
    })
    await waitFor(
      () =>
        expect(
          queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
        ).toBe("second"),
      { timeout: 2000 }
    )
  })

  it("accepts a later server edit when the browser clock is ahead", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, socket, queryClient } = await setup()
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2030-01-01T00:00:00.000Z"))
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("committed edit"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() =>
        expect(result.current.controller.messages[0]?.text).toBe("committed edit")
      )
      await act(async () => {
        edit.resolve({ status: "ok" })
        await edit.promise
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      mocks.chatApi.getMessages.mockResolvedValue({
        items: [
          { ...message, content: "later server edit", edited_at: "2026-10-23T12:01:00.000Z" },
        ],
        has_more: false,
        next_cursor: null,
      })
      act(() =>
        socket.frame({
          type: "message_edited",
          chat_id: ids.chat,
          message_id: ids.message,
          content: "later server edit",
          edited_at: "2026-10-23T12:01:00.000Z",
        })
      )
      await waitFor(
        () => expect(result.current.controller.messages[0]?.text).toBe("later server edit"),
        { timeout: 2000 }
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it("reconciles an ambiguous delayed edit instead of displaying stale text", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [{ ...message, edited_at: "2026-10-23T12:00:00.000Z" }],
      has_more: false,
      next_cursor: null,
    })
    const { result, socket, queryClient } = await setup()
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2030-01-01T00:00:00.000Z"))
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("committed edit"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() =>
        expect(result.current.controller.messages[0]?.text).toBe("committed edit")
      )
      await act(async () => {
        edit.resolve({ status: "ok" })
        await edit.promise
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      const previousFetches = mocks.chatApi.getMessages.mock.calls.length
      mocks.chatApi.getMessages.mockResolvedValue({
        items: [{ ...message, content: "committed edit", edited_at: "2026-10-23T12:01:00.000Z" }],
        has_more: false,
        next_cursor: null,
      })
      act(() =>
        socket.frame({
          type: "message_edited",
          chat_id: ids.chat,
          message_id: ids.message,
          content: "delayed prior edit",
          edited_at: "2026-10-23T12:00:30.000Z",
        })
      )
      expect(result.current.controller.messages[0]?.text).toBe("committed edit")
      await waitFor(
        () => expect(mocks.chatApi.getMessages.mock.calls.length).toBeGreaterThan(previousFetches),
        { timeout: 2000 }
      )
      await waitFor(
        () =>
          expect(result.current.controller.messages[0]).toMatchObject({
            text: "committed edit",
            editedAt: "2026-10-23T12:01:00.000Z",
          }),
        { timeout: 2000 }
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it("does not replace a successful edit with a server frame older than its confirmed baseline", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [{ ...message, edited_at: "2026-10-23T12:00:00.000Z" }],
      has_more: false,
      next_cursor: null,
    })
    const { result, socket, queryClient } = await setup()
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2030-01-01T00:00:00.000Z"))
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("committed edit"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() =>
        expect(result.current.controller.messages[0]?.text).toBe("committed edit")
      )
      await act(async () => {
        edit.resolve({ status: "ok" })
        await edit.promise
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      act(() =>
        socket.frame({
          type: "message_edited",
          chat_id: ids.chat,
          message_id: ids.message,
          content: "older server edit",
          edited_at: "2026-10-23T11:59:00.000Z",
        })
      )
      expect(result.current.controller.messages[0]?.text).toBe("committed edit")
    } finally {
      vi.useRealTimers()
    }
  })

  it("retires a new edit without waiting for a removed query's pending edit", async () => {
    const oldEdit = deferred()
    const newEdit = deferred()
    mocks.chatApi.editMessage
      .mockReturnValueOnce(oldEdit.promise)
      .mockReturnValueOnce(newEdit.promise)
    const { result, queryClient } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("old attempt"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("old attempt"))
    act(() => {
      queryClient.removeQueries({ queryKey: ["messages", ids.chat], exact: true })
      queryClient.setQueryData(["messages", ids.chat], {
        items: [message],
        has_more: false,
        next_cursor: null,
      })
    })
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"))
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("new attempt"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("new attempt"))
    await act(async () => {
      newEdit.resolve({ status: "ok" })
      await newEdit.promise
    })
    await waitFor(() =>
      expect(
        queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
      ).toBe("new attempt")
    )
    await act(async () => {
      oldEdit.reject(new Error("refused"))
      await oldEdit.promise.catch(() => {})
    })
    expect(
      queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
    ).toBe("new attempt")
  })

  it("retires an old session's projection even when its fenced callback never runs", async () => {
    const oldEdit = deferred()
    const newEdit = deferred()
    mocks.chatApi.editMessage
      .mockReturnValueOnce(oldEdit.promise)
      .mockReturnValueOnce(newEdit.promise)
    const { result, queryClient, rerender } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("old session"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("old session"))
    act(() => {
      invalidateSessionEpoch()
      rerender()
    })
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"))
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("new session"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("new session"))
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledTimes(2), {
      timeout: 2000,
    })
    await act(async () => {
      newEdit.resolve({ status: "ok" })
      await newEdit.promise
    })
    await waitFor(() =>
      expect(
        queryClient.getQueryData<MessagesListResponse>(["messages", ids.chat])?.items[0]?.content
      ).toBe("new session")
    )
    await act(async () => {
      oldEdit.reject(new Error("refused"))
      await oldEdit.promise.catch(() => {})
    })
    expect(result.current.controller.editingMessageId).toBeNull()
  })

  it("hides a pending projection when another tab rotates the browser session", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, queryClient, rerender } = await setup()
    const key = "ecosystem.session.generation.v1"
    const previous = localStorage.getItem(key)
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("old session draft"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() =>
        expect(result.current.controller.messages[0]?.text).toBe("old session draft")
      )
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())
      act(() => {
        localStorage.setItem(key, JSON.stringify({ nonce: "cross-tab-session", hash: null }))
        rerender()
      })
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"), {
        timeout: 2000,
      })
    } finally {
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
    }
  })

  it("does not revive an old draft when a cross-tab session changes and then returns", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, queryClient } = await setup()
    const key = "ecosystem.session.generation.v1"
    const previous = localStorage.getItem(key)
    const replacement = JSON.stringify({ nonce: "temporary-remote-session", hash: null })
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("retired draft"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("retired draft"))
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())
      act(() => {
        localStorage.setItem(key, replacement)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: previous, newValue: replacement })
        )
      })
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"), {
        timeout: 2000,
      })
      act(() => {
        if (previous === null) localStorage.removeItem(key)
        else localStorage.setItem(key, previous)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: replacement, newValue: previous })
        )
      })
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      expect(result.current.controller.messages[0]?.text).toBe("original")
      expect(result.current.controller.editingMessageId).toBeNull()
    } finally {
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
    }
  })

  it("keeps an observed stale projection retired when the original nonce returns", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, queryClient, rerender } = await setup()
    const key = "ecosystem.session.generation.v1"
    const previous = localStorage.getItem(key)
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("retired draft"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("retired draft"))
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())
      act(() => {
        localStorage.setItem(key, JSON.stringify({ nonce: "temporary-remote-session", hash: null }))
        rerender()
      })
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"))
      act(() => {
        if (previous === null) localStorage.removeItem(key)
        else localStorage.setItem(key, previous)
        rerender()
      })
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"), {
        timeout: 2000,
      })
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      await waitFor(() => expect(queryClient.isMutating()).toBe(0))
      expect(result.current.controller.editingMessageId).toBeNull()
    } finally {
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
    }
  })

  it("does not retire a pending edit for an unrelated sessionStorage clear", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, queryClient } = await setup()
    act(() => result.current.controller.handleEditMessage(ids.message, "original"))
    act(() => result.current.controller.setEditingMessageContent("draft remains"))
    act(() => result.current.controller.handleSaveEdit(ids.message))
    await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("draft remains"))
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())
    act(() =>
      window.dispatchEvent(new StorageEvent("storage", { key: null, storageArea: sessionStorage }))
    )
    expect(result.current.controller.messages[0]?.text).toBe("draft remains")
    await act(async () => {
      edit.reject(new Error("refused"))
      await edit.promise.catch(() => {})
    })
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
    await waitFor(() =>
      expect(result.current.controller.editingMessageContent).toBe("draft remains")
    )
  })

  it("keeps a removed pending mutation fenced across a cross-tab session transition", async () => {
    const edit = deferred()
    mocks.chatApi.editMessage.mockReturnValue(edit.promise)
    const { result, queryClient } = await setup()
    const key = "ecosystem.session.generation.v1"
    const previous = localStorage.getItem(key)
    const replacement = JSON.stringify({ nonce: "temporary-remote-session", hash: null })
    try {
      act(() => result.current.controller.handleEditMessage(ids.message, "original"))
      act(() => result.current.controller.setEditingMessageContent("removed mutation draft"))
      act(() => result.current.controller.handleSaveEdit(ids.message))
      await waitFor(() =>
        expect(result.current.controller.messages[0]?.text).toBe("removed mutation draft")
      )
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())
      act(() => queryClient.getMutationCache().clear())
      act(() => {
        localStorage.setItem(key, replacement)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: previous, newValue: replacement })
        )
        if (previous === null) localStorage.removeItem(key)
        else localStorage.setItem(key, previous)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: replacement, newValue: previous })
        )
      })
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      await waitFor(() => expect(result.current.controller.messages[0]?.text).toBe("original"))
      expect(result.current.controller.editingMessageId).toBeNull()
    } finally {
      await act(async () => {
        edit.reject(new Error("retired session"))
        await edit.promise.catch(() => {})
      })
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
    }
  })

  it("fences a successful clear's delayed chat refresh after a cross-tab round trip", async () => {
    const clear = deferred()
    const refresh = deferred()
    mocks.chatApi.clearChat.mockReturnValue(clear.promise)
    const { result, queryClient } = await setup()
    const key = "ecosystem.session.generation.v1"
    const previous = localStorage.getItem(key)
    const replacement = JSON.stringify({ nonce: "temporary-remote-session", hash: null })
    try {
      mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
      const previousFetches = mocks.chatApi.getChats.mock.calls.length
      mocks.chatApi.getChats.mockReturnValueOnce(refresh.promise)
      act(() => result.current.controller.handleClearChat())
      act(() => result.current.controller.confirmDialog!.onConfirm())
      await waitFor(() => expect(result.current.controller.messages).toHaveLength(0))
      await act(async () => {
        clear.resolve({ status: "cleared" })
        await clear.promise
      })
      await waitFor(() =>
        expect(mocks.chatApi.getChats.mock.calls.length).toBeGreaterThan(previousFetches)
      )
      await waitFor(() => expect(result.current.unread).toBe(0))
      act(() => {
        localStorage.setItem(key, replacement)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: previous, newValue: replacement })
        )
        if (previous === null) localStorage.removeItem(key)
        else localStorage.setItem(key, previous)
        window.dispatchEvent(
          new StorageEvent("storage", { key, oldValue: replacement, newValue: previous })
        )
      })
      await act(async () => {
        refresh.resolve({
          items: [{ ...chat, unread_count: 9 }],
          has_more: false,
          next_cursor: null,
        })
        await refresh.promise
      })
      await waitFor(
        () =>
          expect(
            queryClient.getQueryData<{ items: Chat[] }>(["chats"])?.items[0]?.unread_count
          ).toBe(0),
        { timeout: 2000 }
      )
    } finally {
      refresh.resolve({ items: [], has_more: false, next_cursor: null })
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
    }
  })
})
