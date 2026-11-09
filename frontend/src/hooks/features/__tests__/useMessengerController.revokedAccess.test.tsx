import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosError, type AxiosResponse } from "axios"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Chat, Message, MessagesListResponse } from "@/api/chat"
import { useMessengerController } from "../useMessengerController"

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    markRead: vi.fn(),
  },
  navigate: vi.fn(),
  messenger: {
    presenceMap: {},
    isConnected: true,
    sendJoin: vi.fn(),
    sendLeave: vi.fn(),
  },
  user: { id: "current-user", full_name: "Current User", role: "student" },
}))

vi.mock("@/api/chat", () => ({ chatApi: mocks.chatApi }))
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useParams: () => ({ chatId: "chat-1" }),
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mocks.user }) }))
vi.mock("@/contexts/MessengerContext", () => ({ useMessenger: () => mocks.messenger }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))
vi.mock("@/api/client", () => ({ default: { get: vi.fn() } }))

const cachedChat = {
  id: "chat-1",
  chat_type: "group",
  name: "Removed from this group",
  created_by: "owner",
  participants: [
    { id: "current-user", full_name: "Current User" },
    { id: "owner", full_name: "Owner" },
  ],
} as unknown as Chat
const cachedMessage: Message = {
  id: "secret-1",
  chat_id: "chat-1",
  sender_id: "owner",
  content: "history the removed member saw earlier",
  created_at: "2026-11-09T10:00:00Z",
  read_status: true,
  attachments: [],
}
const cachedPage: MessagesListResponse = {
  items: [cachedMessage],
  has_more: false,
  next_cursor: null,
}

function httpError(status: number): AxiosError {
  return new AxiosError("request failed", "ERR_BAD_REQUEST", undefined, undefined, {
    status,
  } as AxiosResponse)
}

let queryClient: QueryClient

// Restore the cache a reload brings back from IndexedDB, then answer as the server does.
function renderRestored(status: number, ageMs = 60 * 60_000) {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  // Restored data carries its original age, so it is stale and the hook refetches it.
  const restoredAt = Date.now() - ageMs
  queryClient.setQueryData(["chats", "chat-1"], cachedChat, { updatedAt: restoredAt })
  queryClient.setQueryData(["messages", "chat-1"], cachedPage, { updatedAt: restoredAt })
  mocks.chatApi.getChat.mockRejectedValue(httpError(status))
  mocks.chatApi.getMessages.mockRejectedValue(httpError(status))
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return renderHook(() => useMessengerController(), { wrapper: Wrapper })
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.chatApi.getChats.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
})

afterEach(() => {
  queryClient.clear()
})

describe("a chat the server no longer shows to this user", () => {
  it.each([403, 404])("drops the restored chat and history on %i", async (status) => {
    const { result, unmount } = renderRestored(status)

    await waitFor(() => expect(queryClient.getQueryData(["chats", "chat-1"])).toBeNull())
    await waitFor(() => expect(result.current.messages).toEqual([]))
    expect(result.current.activeChat).toBeNull()
    expect(mocks.chatApi.getChat).toHaveBeenCalled()
    expect(mocks.chatApi.getMessages).toHaveBeenCalled()
    expect(queryClient.getQueryData(["chats", "chat-1"])).toBeNull()
    expect(queryClient.getQueryData(["messages", "chat-1"])).toEqual({
      items: [],
      has_more: false,
      next_cursor: null,
    })
    expect(result.current.messagesError).toBe(false)
    unmount()
  })

  it("drops a restored chat that is still fresh when the server list lacks it", async () => {
    // A reload seconds after removal restores data younger than the stale time.
    const { result, unmount } = renderRestored(403, 0)

    await waitFor(() => expect(queryClient.getQueryData(["chats", "chat-1"])).toBeNull())
    await waitFor(() => expect(result.current.messages).toEqual([]))
    expect(result.current.activeChat).toBeNull()
    expect(mocks.chatApi.getChat).toHaveBeenCalled()
    unmount()
  })

  it("keeps the cached chat for offline reading when the server fails", async () => {
    const { result, unmount } = renderRestored(503)

    await waitFor(() => expect(result.current.messagesError).toBe(true))
    expect(result.current.activeChat?.id).toBe("chat-1")
    expect(result.current.messages.map(({ id }) => id)).toEqual(["secret-1"])
    expect(queryClient.getQueryData(["messages", "chat-1"])).toEqual(cachedPage)
    unmount()
  })
})
