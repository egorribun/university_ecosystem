import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LazyMotion, domAnimation } from "framer-motion"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { chatApi, type Chat, type ChatsListResponse, type Message } from "@/api/chat"
import { MessengerProvider } from "@/contexts/MessengerContext"
import MessengerFeature from "@/features/messenger/MessengerFeature"
import { useMessengerController } from "@/hooks/features/useMessengerController"

const state = vi.hoisted(() => ({
  chatId: undefined as string | undefined,
  navigate: vi.fn(),
  translate: (key: string) => key,
  user: {
    id: "current-user",
    email: "current@example.test",
    full_name: "Current User",
    is_active: true,
    role: "student" as const,
  },
  socket: {
    isConnected: true,
    sendTyping: vi.fn(),
    sendJoin: vi.fn(),
    sendLeave: vi.fn(),
    getTypingUsersForChat: () => [],
  },
}))

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ chatId: state.chatId }),
  useNavigate: () => state.navigate,
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: state.user, isAuth: true, loading: false }),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: state.translate, i18n: { language: "en" } }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => query === "(prefers-reduced-motion: reduce)",
}))
vi.mock("@/hooks/useChatWebSocket", () => ({
  WebSocketProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useChatWebSocket: () => state.socket,
}))

// Keep the real provider, controller, feature wiring, sidebar and contact list.
// Closed overlays and the unrelated message view are outside this list contract;
// the final control exercises real message paging through the controller.
vi.mock("@/components/messenger", async () => {
  const actual =
    await vi.importActual<typeof import("@/components/messenger")>("@/components/messenger")
  return {
    ...actual,
    ChatArea: () => null,
    MessengerBackdrop: () => null,
    NewChatModal: () => null,
    ForwardModal: () => null,
    GroupInfoPanel: () => null,
  }
})
vi.mock("@/components/messenger/ProfileModal", () => ({ ProfileModal: () => null }))

const peer = {
  id: "peer-user",
  email: "peer@example.test",
  full_name: "Peer User",
  is_active: true,
}
const chats: Chat[] = Array.from({ length: 21 }, (_, index): Chat => ({
  id: "chat-" + String(index + 1),
  chat_type: "group",
  name: "Conversation " + String(index + 1),
  created_by: state.user.id,
  participants: [state.user, peer],
  unread_count: 0,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
}))
const firstPage: ChatsListResponse = {
  items: chats.slice(0, 20),
  has_more: true,
  next_cursor: "chat-page-2",
}
const lastPage: ChatsListResponse = {
  items: [chats[20]!],
  has_more: false,
  next_cursor: null,
}
const clients: QueryClient[] = []
const moreLabel = "messenger:pagination.loadMoreChats"
const retryLabel = "messenger:error.retry"

function environment() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 30_000 },
      mutations: { retry: false },
    },
  })
  clients.push(client)
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <LazyMotion features={domAnimation}>{children}</LazyMotion>
    </QueryClientProvider>
  )
  return { client, Wrapper }
}

function visibleContacts() {
  return within(screen.getByRole("list", { name: "messenger:aria.conversationList" })).getAllByRole(
    "listitem"
  )
}

beforeEach(() => {
  state.chatId = undefined
  state.navigate.mockReset()
  vi.spyOn(chatApi, "getChat").mockResolvedValue(chats[20]!)
  vi.spyOn(chatApi, "getMessages").mockResolvedValue({
    items: [],
    has_more: false,
    next_cursor: null,
  })
  vi.spyOn(chatApi, "markRead").mockResolvedValue({ success: true })
})

afterEach(async () => {
  cleanup()
  try {
    for (const client of clients) await client.cancelQueries()
  } finally {
    clients.splice(0).forEach((client) => client.clear())
    vi.restoreAllMocks()
  }
})

describe("AUD030 chat-list cursor reachability", () => {
  it("reaches the twenty-first chat once and stops when the cursor is exhausted", async () => {
    let resolveNext!: (page: ChatsListResponse) => void
    const nextPage = new Promise<ChatsListResponse>((resolve) => {
      resolveNext = resolve
    })
    const requests: Array<{ cursor: string | undefined; limit: number }> = []
    vi.spyOn(chatApi, "getChats").mockImplementation((cursor, limit = 20) => {
      requests.push({ cursor, limit })
      if (cursor === undefined) return Promise.resolve(firstPage)
      if (cursor === "chat-page-2") return nextPage
      return Promise.reject(new Error("Unexpected chat cursor"))
    })
    const { client, Wrapper } = environment()
    const view = render(<MessengerFeature />, { wrapper: Wrapper })
    try {
      await screen.findByRole("button", { name: "Conversation 20" })
      expect(visibleContacts()).toHaveLength(20)
      expect(screen.queryByRole("button", { name: "Conversation 21" })).toBeNull()
      const more = screen.getByRole("button", { name: moreLabel })
      fireEvent.click(more)
      await waitFor(() => expect(more).toBeDisabled())
      fireEvent.click(more)
      expect(requests.filter(({ cursor }) => cursor === "chat-page-2")).toHaveLength(1)
      expect(visibleContacts()).toHaveLength(20)

      await act(async () => resolveNext(lastPage))
      const twentyFirst = await screen.findByRole("button", { name: "Conversation 21" })
      expect(visibleContacts()).toHaveLength(21)
      expect(screen.queryByRole("button", { name: moreLabel })).toBeNull()
      expect(requests.every(({ limit }) => limit === 20)).toBe(true)
      view.rerender(<MessengerFeature />)
      await waitFor(() => expect(client.isFetching()).toBe(0))
      expect(requests.filter(({ cursor }) => cursor === "chat-page-2")).toHaveLength(1)
      fireEvent.click(twentyFirst)
      expect(state.navigate).toHaveBeenCalledWith({
        to: "/messenger/$chatId",
        params: { chatId: "chat-21" },
        replace: false,
        state: { messengerOpenedFromList: true },
      })
    } finally {
      try {
        view.unmount()
        await client.cancelQueries()
      } finally {
        resolveNext(lastPage)
      }
    }
  })

  it("retains the first page after terminal failure until an explicit retry", async () => {
    let allowRetry = false
    let nextRequests = 0
    vi.spyOn(chatApi, "getChats").mockImplementation((cursor) => {
      if (cursor === undefined) return Promise.resolve(firstPage)
      if (cursor !== "chat-page-2") return Promise.reject(new Error("Unexpected chat cursor"))
      nextRequests += 1
      return allowRetry
        ? Promise.resolve(lastPage)
        : Promise.reject(new Error("Synthetic chat-page transport failure"))
    })
    const { client, Wrapper } = environment()
    const view = render(<MessengerFeature />, { wrapper: Wrapper })
    await screen.findByRole("button", { name: "Conversation 20" })
    fireEvent.click(screen.getByRole("button", { name: moreLabel }))
    await screen.findByRole("button", { name: retryLabel }, { timeout: 5000 })
    expect(screen.getByRole("alert")).toBeVisible()
    expect(visibleContacts()).toHaveLength(20)
    expect(nextRequests).toBeGreaterThanOrEqual(1)
    expect(nextRequests).toBeLessThanOrEqual(3)
    const exhaustedAttempts = nextRequests
    expect(client.getQueryData<ChatsListResponse>(["chats"])?.next_cursor).toBe("chat-page-2")

    view.rerender(<MessengerFeature />)
    fireEvent.change(screen.getByPlaceholderText("messenger:search"), {
      target: { value: "Conversation" },
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(visibleContacts()).toHaveLength(20)
    expect(nextRequests).toBe(exhaustedAttempts)

    allowRetry = true
    fireEvent.click(screen.getByRole("button", { name: retryLabel }))
    await screen.findByRole("button", { name: "Conversation 21" })
    expect(visibleContacts()).toHaveLength(21)
    expect(nextRequests).toBe(exhaustedAttempts + 1)
    expect(screen.queryByRole("alert")).toBeNull()
    expect(screen.queryByRole("button", { name: moreLabel })).toBeNull()
    expect(screen.queryByRole("button", { name: retryLabel })).toBeNull()
  })

  it("keeps direct links and message cursors independent of the chat-list cursor", async () => {
    state.chatId = "chat-21"
    const list = vi.spyOn(chatApi, "getChats").mockResolvedValue(firstPage)
    const recent: Message = {
      id: "recent-message",
      chat_id: "chat-21",
      sender_id: peer.id,
      content: "Recent message",
      created_at: "2026-10-30T10:00:00Z",
      read_status: true,
      attachments: [],
    }
    const older: Message = {
      ...recent,
      id: "older-message",
      content: "Older message",
      created_at: "2026-10-30T09:00:00Z",
    }
    const messages = vi
      .mocked(chatApi.getMessages)
      .mockImplementation((_id, cursor) =>
        Promise.resolve(
          cursor === undefined
            ? { items: [recent], has_more: true, next_cursor: "older-message-page" }
            : { items: [older], has_more: false, next_cursor: null }
        )
      )
    const { client, Wrapper } = environment()
    const HookWrapper = ({ children }: { children: ReactNode }) => (
      <Wrapper>
        <MessengerProvider>{children}</MessengerProvider>
      </Wrapper>
    )
    const { result } = renderHook(() => useMessengerController(), { wrapper: HookWrapper })
    await waitFor(() => {
      expect(result.current.activeChat?.id).toBe("chat-21")
      expect(result.current.contacts).toHaveLength(20)
      expect(result.current.messages.map(({ id }) => id)).toEqual(["recent-message"])
    })
    expect(chatApi.getChat).toHaveBeenCalledWith("chat-21", expect.any(AbortSignal))
    await act(async () => {
      await result.current.handleLoadOlderMessages()
    })
    await waitFor(() =>
      expect(result.current.messages.map(({ id }) => id)).toEqual([
        "older-message",
        "recent-message",
      ])
    )
    expect(messages).toHaveBeenCalledWith(
      "chat-21",
      "older-message-page",
      50,
      expect.any(AbortSignal)
    )
    expect(result.current.hasMoreMessages).toBe(false)
    expect(result.current.contacts).toHaveLength(20)
    expect(list.mock.calls.every(([cursor]) => cursor === undefined)).toBe(true)
    expect(client.getQueryData<ChatsListResponse>(["chats"])?.next_cursor).toBe("chat-page-2")
  })
})

describe("AUD030 loaded chat-list lifetime", () => {
  it("refetches the loaded extent without dropping the tail during read invalidation", async () => {
    const refreshedFirst: ChatsListResponse = {
      ...firstPage,
      items: firstPage.items.map((chat, index) =>
        index === 0 ? { ...chat, name: "Updated conversation" } : chat
      ),
    }
    const cursors: Array<string | undefined> = []
    vi.spyOn(chatApi, "getChats").mockImplementation((cursor) => {
      cursors.push(cursor)
      if (cursor === undefined) return Promise.resolve(refreshedFirst)
      if (cursor === "chat-page-2") return Promise.resolve(lastPage)
      return Promise.reject(new Error("Unexpected chat cursor"))
    })
    const { client, Wrapper } = environment()
    // This is a valid loaded aggregate, not evidence that current UI can create it.
    client.setQueryData<ChatsListResponse>(["chats"], {
      items: chats,
      has_more: false,
      next_cursor: null,
    })
    const HookWrapper = ({ children }: { children: ReactNode }) => (
      <Wrapper>
        <MessengerProvider>{children}</MessengerProvider>
      </Wrapper>
    )
    const { result, rerender } = renderHook(() => useMessengerController(), {
      wrapper: HookWrapper,
    })
    await waitFor(() => expect(result.current.contacts).toHaveLength(21))
    expect(cursors).toEqual([])

    await act(async () => {
      await result.current.refetchChats()
    })
    await waitFor(() => expect(result.current.contacts).toHaveLength(21))
    expect(result.current.contacts[0]?.name).toBe("Updated conversation")
    expect(cursors).toEqual([undefined, "chat-page-2"])
    expect(client.getQueryData<ChatsListResponse>(["chats"])).toMatchObject({
      has_more: false,
      next_cursor: null,
    })

    // Selecting the tail chat invokes the real markRead mutation, which invalidates
    // the shared list observed by both the controller and MessengerProvider.
    state.chatId = "chat-21"
    rerender()
    await waitFor(() => expect(chatApi.markRead).toHaveBeenCalledWith("chat-21"))
    await waitFor(() =>
      expect(cursors).toEqual([undefined, "chat-page-2", undefined, "chat-page-2"])
    )
    await waitFor(() => expect(client.isFetching()).toBe(0))
    expect(result.current.activeChat?.id).toBe("chat-21")
    expect(result.current.contacts.map(({ id }) => id)).toEqual(chats.map(({ id }) => id))
  })

  it("retires the old account's pending page before its late response", async () => {
    const previousUser = state.user
    const nextUser = { ...previousUser, id: "next-user", email: "next@example.test" }
    const nextAccountChat: Chat = {
      ...chats[0]!,
      id: "next-account-chat",
      name: "Next account conversation",
      created_by: nextUser.id,
      participants: [nextUser, peer],
    }
    const nextAccountPage: ChatsListResponse = {
      items: [nextAccountChat],
      has_more: false,
      next_cursor: null,
    }
    let resolveNext!: (page: ChatsListResponse) => void
    const pendingPage = new Promise<ChatsListResponse>((resolve) => {
      resolveNext = resolve
    })
    const oldRequest: { signal?: AbortSignal } = {}
    vi.spyOn(chatApi, "getChats").mockImplementation((cursor, _limit, signal) => {
      if (state.user.id === nextUser.id) return Promise.resolve(nextAccountPage)
      if (cursor === undefined) return Promise.resolve(firstPage)
      if (cursor === "chat-page-2") {
        oldRequest.signal = signal
        // Deliberately ignore cancellation: ownership must reject a late response.
        return pendingPage
      }
      return Promise.reject(new Error("Unexpected chat cursor"))
    })
    const { client, Wrapper } = environment()
    const view = render(<MessengerFeature />, { wrapper: Wrapper })
    try {
      await screen.findByRole("button", { name: "Conversation 20" })
      fireEvent.click(screen.getByRole("button", { name: moreLabel }))
      await waitFor(() => expect(oldRequest.signal).toBeInstanceOf(AbortSignal))

      await act(async () => {
        await client.cancelQueries()
        client.clear()
        state.user = nextUser
        client.setQueryData(["chats"], nextAccountPage)
        view.rerender(<MessengerFeature />)
      })
      await screen.findByRole("button", { name: "Next account conversation" })
      expect(oldRequest.signal?.aborted).toBe(true)

      await act(async () => resolveNext(lastPage))
      expect(visibleContacts()).toHaveLength(1)
      expect(screen.queryByRole("button", { name: "Conversation 21" })).toBeNull()
      expect(client.getQueryData<ChatsListResponse>(["chats"])).toEqual(nextAccountPage)
    } finally {
      try {
        view.unmount()
        await client.cancelQueries()
      } finally {
        state.user = previousUser
        resolveNext(lastPage)
      }
    }
  })
})
