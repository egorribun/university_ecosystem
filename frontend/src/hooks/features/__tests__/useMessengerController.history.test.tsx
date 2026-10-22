import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Message, MessagesListResponse } from "@/api/chat"
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

const messageKey = ["messages", "chat-1"] as const
const message = (id: string, overrides: Partial<Message> = {}): Message => ({
  id,
  chat_id: "chat-1",
  sender_id: "peer",
  content: id,
  created_at: "2026-08-25T10:00:00Z",
  read_status: false,
  attachments: [],
  ...overrides,
})
const page = (items: Message[]): MessagesListResponse => ({
  items,
  has_more: true,
  next_cursor: "older-cursor",
})
const attachment = {
  id: "attachment-1",
  url: "/uploads/message-attachment.png",
  file_type: "image" as const,
  filename: "message-attachment.png",
  size: 128,
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.chatApi.getChats.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
  mocks.chatApi.getChat.mockResolvedValue(null)
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
})

type PageRequest = "hydration" | "older history"

// Use the same public operations as reconnect refetches and history paging.
// Every request belongs to this invocation and is settled even if an assertion fails.
const withMergedPage = async (
  requestKind: PageRequest,
  current: MessagesListResponse,
  fetched: MessagesListResponse,
  check: (state: ReturnType<typeof useMessengerController>, cache: MessagesListResponse) => void,
  whilePending?: (queryClient: QueryClient) => void
) => {
  let resolvePage!: (value: MessagesListResponse) => void
  const pendingPage = new Promise<MessagesListResponse>((resolve) => {
    resolvePage = resolve
  })
  mocks.chatApi.getMessages.mockReturnValue(pendingPage)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  queryClient.setQueryData(messageKey, current)
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const { result, unmount } = renderHook(() => useMessengerController(), { wrapper: Wrapper })
  let request: Promise<unknown> | undefined
  try {
    await waitFor(
      () =>
        expect(result.current.messages.map(({ id }) => id)).toEqual(
          current.items.map(({ id }) => id)
        ),
      { timeout: 1000 }
    )
    act(() => {
      request =
        requestKind === "hydration"
          ? result.current.refetchMessages()
          : result.current.handleLoadOlderMessages()
    })
    await waitFor(
      () => {
        if (requestKind === "hydration") {
          expect(queryClient.getQueryState(messageKey)?.fetchStatus).toBe("fetching")
        } else {
          expect(result.current.isLoadingOlderMessages).toBe(true)
        }
      },
      { timeout: 1000 }
    )
    act(() => whilePending?.(queryClient))
    await act(async () => {
      resolvePage(fetched)
      await request
    })
    await waitFor(
      () => {
        const cache = queryClient.getQueryData<MessagesListResponse>(messageKey)
        expect(cache).toBeDefined()
        if (cache) check(result.current, cache)
      },
      { timeout: 1000 }
    )
  } finally {
    try {
      unmount()
    } finally {
      resolvePage(fetched)
      try {
        await request
      } finally {
        try {
          await queryClient.cancelQueries()
        } finally {
          queryClient.clear()
        }
      }
    }
  }
}

describe.each<PageRequest>(["hydration", "older history"])("message versions during %s", (kind) => {
  it.each([
    {
      name: "accepts the first server edit of an unedited message",
      liveEdit: null,
      fetchedEdit: "2026-08-25T12:00:00Z",
      expectedContent: "server content",
      expectedEdit: "2026-08-25T12:00:00Z",
    },
    {
      name: "accepts a newer server edit without reverting live read or reaction state",
      liveEdit: "2026-08-25T11:00:00Z",
      fetchedEdit: "2026-08-25T12:00:00Z",
      expectedContent: "server content",
      expectedEdit: "2026-08-25T12:00:00Z",
    },
    {
      name: "keeps a newer live edit when a delayed page has an older edit",
      liveEdit: "2026-08-25T12:00:00Z",
      fetchedEdit: "2026-08-25T11:00:00Z",
      expectedContent: "live content",
      expectedEdit: "2026-08-25T12:00:00Z",
    },
    {
      name: "keeps live content when overlapping edit timestamps tie",
      liveEdit: "2026-08-25T12:00:00Z",
      fetchedEdit: "2026-08-25T12:00:00Z",
      expectedContent: "live content",
      expectedEdit: "2026-08-25T12:00:00Z",
    },
  ])("$name", async ({ liveEdit, fetchedEdit, expectedContent, expectedEdit }) => {
    const live = message("shared", { content: "live content", edited_at: liveEdit })
    const fetched = message("shared", {
      content: "server content",
      edited_at: fetchedEdit,
      reactions: [{ emoji: "👍", count: 1, reacted_by_me: false }],
    })
    const liveRead = "2026-08-25T12:03:00Z"
    const liveReactions = [{ emoji: "👍", count: 3, reacted_by_me: true }]
    await withMergedPage(
      kind,
      page([live]),
      { items: [fetched], has_more: false, next_cursor: null },
      (state, cache) => {
        expect(cache).toEqual({
          items: [
            {
              ...live,
              content: expectedContent,
              edited_at: expectedEdit,
              read_status: true,
              read_at: liveRead,
              reactions: liveReactions,
            },
          ],
          has_more: false,
          next_cursor: null,
        })
        expect(state.messages).toHaveLength(1)
        expect(state.messages[0]).toMatchObject({
          id: "shared",
          text: expectedContent,
          editedAt: expectedEdit,
          status: "read",
          readAt: liveRead,
          reactions: [{ emoji: "👍", count: 3, reactedByMe: true }],
        })
        expect(state.hasMoreMessages).toBe(false)
      },
      (client) => {
        client.setQueryData(
          messageKey,
          page([{ ...live, read_status: true, read_at: liveRead, reactions: liveReactions }])
        )
      }
    )
  })

  it.each(["live", "server"] as const)(
    "preserves a %s deletion tombstone and removes attachments",
    async (deletedSide) => {
      const deletedAt = "2026-08-25T12:02:00Z"
      const visible = message("shared", { content: "old message", attachments: [attachment] })
      const deleted = { ...visible, content: "", attachments: [], deleted_at: deletedAt }
      const live = deletedSide === "live" ? deleted : visible
      const fetched = deletedSide === "server" ? deleted : visible
      await withMergedPage(
        kind,
        page([live]),
        { items: [fetched], has_more: false, next_cursor: null },
        (state, cache) => {
          expect(cache.items).toEqual([deleted])
          expect(state.messages).toHaveLength(1)
          expect(state.messages[0]).toMatchObject({
            id: "shared",
            text: "",
            deletedAt,
            attachments: [],
          })
        }
      )
    }
  )
})

it("orders hydrated history and live-only messages chronologically, with stable id ties", async () => {
  const oldest = message("z-oldest", { created_at: "2026-08-25T08:00:00Z" })
  const tied = message("a-tie", { created_at: "2026-08-25T09:00:00Z" })
  const overlap = message("z-tie", { created_at: "2026-08-25T09:00:00Z", content: "live overlap" })
  const newest = message("a-newest", { created_at: "2026-08-25T11:00:00Z" })
  const restOnly = message("m-rest", { created_at: "2026-08-25T10:00:00Z" })
  const fetched = {
    items: [{ ...overlap, content: "stale overlap" }, restOnly],
    has_more: true,
    next_cursor: "refreshed-cursor",
  }
  await withMergedPage(
    "hydration",
    page([oldest, tied, overlap]),
    fetched,
    (state, cache) => {
      expect(cache).toEqual({ ...fetched, items: [oldest, tied, overlap, restOnly, newest] })
      expect(state.messages.map(({ id, text }) => ({ id, text }))).toEqual(
        [oldest, tied, overlap, restOnly, newest].map(({ id, content }) => ({ id, text: content }))
      )
      expect(state.hasMoreMessages).toBe(true)
    },
    (client) => {
      client.setQueryData(messageKey, page([oldest, tied, overlap, newest]))
    }
  )
})

it("repopulates an evicted message cache when an already requested older page finishes", async () => {
  const older = message("older", { created_at: "2026-08-25T08:00:00Z" })
  const fetched = { items: [older], has_more: false, next_cursor: null }
  await withMergedPage(
    "older history",
    page([message("current")]),
    fetched,
    (state, cache) => {
      expect(cache).toEqual(fetched)
      expect(state.olderMessagesError).toBe(false)
      expect(state.isLoadingOlderMessages).toBe(false)
    },
    (client) => {
      client.removeQueries({ queryKey: messageKey, exact: true })
      expect(client.getQueryData(messageKey)).toBeUndefined()
    }
  )
})
