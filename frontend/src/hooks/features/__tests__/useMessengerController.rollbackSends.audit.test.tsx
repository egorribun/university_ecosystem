import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { beforeEach, expect, it, vi } from "vitest"
import type { Message, MessagesListResponse } from "@/api/chat"
import { useMessengerController } from "../useMessengerController"

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    sendMessage: vi.fn(),
    editMessage: vi.fn(),
    markRead: vi.fn(),
  },
  navigate: vi.fn(),
  messenger: {
    presenceMap: {},
    isConnected: true,
    sendJoin: vi.fn(),
    sendLeave: vi.fn(),
  },
}))

vi.mock("@/api/chat", () => ({ chatApi: mocks.chatApi }))
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useParams: () => ({ chatId: "chat-1" }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "me", full_name: "Me", role: "student" } }),
}))
vi.mock("@/contexts/MessengerContext", () => ({ useMessenger: () => mocks.messenger }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))
vi.mock("@/api/client", () => ({ default: { get: vi.fn() } }))

const messageKey = ["messages", "chat-1"] as const

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function message(id: string, createdAt: string, content = id): Message {
  return {
    id,
    chat_id: "chat-1",
    sender_id: "me",
    content,
    created_at: createdAt,
    read_status: false,
    attachments: [],
  }
}

function page(items: Message[], hasMore = false): MessagesListResponse {
  return { items, has_more: hasMore, next_cursor: hasMore ? "older-cursor" : null }
}

function setup(current: MessagesListResponse) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  queryClient.setQueryData(messageKey, current)
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useMessengerController(), { wrapper: Wrapper })
  return { ...hook, queryClient }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.chatApi.getChats.mockResolvedValue({
    items: [{ id: "chat-1", participants: [], unread_count: 0 }],
    has_more: false,
    next_cursor: null,
  })
  mocks.chatApi.getChat.mockResolvedValue(null)
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
})

it("keeps reverse-completed sends when an unrelated optimistic edit fails", async () => {
  const original = message("original", "2026-08-25T11:00:00Z", "original text")
  const earlier = message(
    "ffffffff-ffff-4fff-8fff-ffffffffffff",
    "2026-08-25T12:00:00.123001Z",
    "first send"
  )
  const later = message(
    "11111111-1111-4111-8111-111111111111",
    "2026-08-25T12:00:00.123999Z",
    "second send"
  )
  const first = deferred<Message>()
  const second = deferred<Message>()
  const edit = deferred<unknown>()
  mocks.chatApi.getMessages.mockResolvedValue(page([original], true))
  mocks.chatApi.editMessage.mockReturnValue(edit.promise)
  mocks.chatApi.sendMessage.mockImplementation((_chatId: string, content: string) =>
    content === "first send" ? first.promise : second.promise
  )
  const { result, unmount, queryClient } = setup(page([original], true))
  const deliveries: Promise<boolean>[] = []
  try {
    await waitFor(() => expect(result.current.messages).toHaveLength(1))
    act(() => result.current.handleEditMessage(original.id, original.content))
    act(() => result.current.setEditingMessageContent("pending edit"))
    act(() => result.current.handleSaveEdit(original.id))
    await waitFor(() => expect(result.current.messages[0]?.text).toBe("pending edit"))
    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalledOnce())

    act(() => {
      deliveries.push(result.current.handleSendMessage("first send", []))
      deliveries.push(result.current.handleSendMessage("second send", []))
    })
    await waitFor(() => expect(mocks.chatApi.sendMessage).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.resolve(later)
      await second.promise
    })
    await waitFor(() =>
      expect(queryClient.getQueryData<MessagesListResponse>(messageKey)?.items).toEqual([
        original,
        later,
      ])
    )
    await act(async () => {
      first.resolve(earlier)
      await Promise.all(deliveries)
    })
    expect(deliveries).toHaveLength(2)
    await waitFor(() =>
      expect(result.current.messages.map(({ id }) => id)).toEqual([
        original.id,
        earlier.id,
        later.id,
      ])
    )
    expect(result.current.messages[0]?.text).toBe("pending edit")

    await act(async () => {
      edit.reject(new Error("edit rejected"))
      await edit.promise.catch(() => {})
    })
    await waitFor(() => expect(result.current.messages[0]?.text).toBe("original text"))
    expect(result.current.messages.map(({ id }) => id)).toEqual([original.id, earlier.id, later.id])
    expect(queryClient.getQueryData(messageKey)).toEqual(page([original, earlier, later], true))
  } finally {
    unmount()
    first.resolve(earlier)
    second.resolve(later)
    edit.resolve(undefined)
    await Promise.allSettled([...deliveries, edit.promise])
    await queryClient.cancelQueries()
    queryClient.clear()
  }
})
