import { renderHook, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

/**
 * Wave 183 SW8 — useMessengerController unit tests.
 *
 * Covers W183 SW3 + SW7 regression guards + baseline hook API:
 *  - W183 SW3 Blob URL memory leak (createObjectURL tracking + revokeObjectURL
 *    on success / error / unmount).
 *  - getOtherParticipant correctly excludes current user.
 *  - chat selection from URL params.
 *  - contacts derivation from chats + presenceMap.
 *  - confirmDialog state machine for clearChat + deleteChat.
 *  - W183 SW3 defaultValue antipattern removal (mock t() passes keys
 *    through verbatim; assertions check key name without fallback string).
 *
 * Mocking strategy uses vi.hoisted() to share mock fns between the
 * top-level vi.mock factories (which are hoisted to file top) and the
 * test setup blocks (which run after imports are evaluated).
 */

// ---------- Hoisted mocks (vi.hoisted) ----------

const mocks = vi.hoisted(() => ({
  chatApi: {
    getChats: vi.fn(),
    getChat: vi.fn(),
    getMessages: vi.fn(),
    sendMessage: vi.fn(),
    markRead: vi.fn(),
    createChat: vi.fn(),
    clearChat: vi.fn(),
    deleteChat: vi.fn(),
  },
  navigate: vi.fn(),
  paramsRef: { current: {} as { chatId?: string } },
  testUser: {
    id: "current-user-id",
    email: "test@example.com",
    full_name: "Test User",
    avatar_url: "/avatar.png",
    is_active: true,
    role: "student",
  },
  apiClient: {
    get: vi.fn(),
  },
  createObjectURL: vi.fn<(obj: Blob | MediaSource) => string>(),
  revokeObjectURL: vi.fn<(url: string) => void>(),
}))

vi.mock("@/api/chat", () => ({
  chatApi: mocks.chatApi,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useParams: () => mocks.paramsRef.current,
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.testUser }),
}))

vi.mock("@/contexts/MessengerContext", () => ({
  useMessenger: () => ({
    presenceMap: {},
    isConnected: true,
    sendTyping: vi.fn(),
    sendRead: vi.fn(),
    getTypingUsersForChat: () => [],
    unreadCount: 0,
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/api/client", () => ({
  default: mocks.apiClient,
}))

// ---------- Helpers ----------

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

// Import after mocks are registered (vi.mock factories are hoisted to
// top of file, but the actual module evaluation happens here)
import { useMessengerController } from "../useMessengerController"

// ---------- Setup ----------

beforeEach(() => {
  vi.clearAllMocks()
  mocks.paramsRef.current = {}

  // URL spies — restored each test (vi.clearAllMocks would wipe their
  // return values otherwise).
  mocks.createObjectURL.mockClear().mockReturnValue("blob:mock-url")
  mocks.revokeObjectURL.mockClear()
  Object.defineProperty(URL, "createObjectURL", {
    value: mocks.createObjectURL,
    writable: true,
  })
  Object.defineProperty(URL, "revokeObjectURL", {
    value: mocks.revokeObjectURL,
    writable: true,
  })

  // Default chatApi behaviour — empty list, no chats. Tests override.
  mocks.chatApi.getChats.mockResolvedValue({
    items: [],
    has_more: false,
    next_cursor: null,
  })
  mocks.chatApi.getMessages.mockResolvedValue({
    items: [],
    has_more: false,
    next_cursor: null,
  })
  mocks.chatApi.sendMessage.mockResolvedValue({
    id: "server-msg-id",
    chat_id: "chat-1",
    sender_id: "current-user-id",
    content: "hello",
    created_at: new Date().toISOString(),
    read_status: false,
    attachments: [],
  })
  mocks.chatApi.markRead.mockResolvedValue({ success: true })
  mocks.apiClient.get.mockResolvedValue({ data: mocks.testUser })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------- Tests ----------

describe("useMessengerController", () => {
  describe("Blob URL lifecycle (W183 SW3 regression)", { retry: 2 }, () => {
    it("creates ONE Blob URL per attached file in handleSendMessage", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })

      await waitFor(() => {
        expect(result.current.activeChat?.id).toBe("chat-1")
      })

      const file1 = new File(["a"], "a.png", { type: "image/png" })
      const file2 = new File(["b"], "b.png", { type: "image/png" })

      await act(async () => {
        result.current.handleSendMessage("hello", [file1, file2])
      })

      expect(mocks.createObjectURL).toHaveBeenCalledTimes(2)
      expect(mocks.createObjectURL).toHaveBeenCalledWith(file1)
      expect(mocks.createObjectURL).toHaveBeenCalledWith(file2)
    })

    it("revokes all tracked Blob URLs on mutation success", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      const file = new File(["a"], "a.png", { type: "image/png" })

      await act(async () => {
        result.current.handleSendMessage("hi", [file])
      })

      await waitFor(() => {
        expect(mocks.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url")
      })
    })

    it("revokes Blob URLs on mutation error", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
      mocks.chatApi.sendMessage.mockRejectedValue(new Error("network fail"))

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      const file = new File(["a"], "a.png", { type: "image/png" })

      await act(async () => {
        result.current.handleSendMessage("hi", [file])
      })

      await waitFor(() => {
        expect(mocks.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url")
      })
    })

    it("revokes outstanding Blob URLs on unmount", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
      mocks.chatApi.sendMessage.mockReturnValue(new Promise(() => {}))

      const { result, unmount } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      const file = new File(["a"], "a.png", { type: "image/png" })

      await act(async () => {
        result.current.handleSendMessage("hi", [file])
      })

      mocks.revokeObjectURL.mockClear()

      unmount()

      expect(mocks.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url")
    })
  })

  describe("getOtherParticipant", () => {
    it("returns the participant who is NOT the current user", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      const peer = { id: "peer-id", full_name: "Peer" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [{ id: "chat-1", participants: [{ id: "current-user-id" }, peer], unread_count: 0 }],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      const other = result.current.getOtherParticipant(result.current.activeChat!)
      expect(other).toEqual(peer)
      expect(other?.id).not.toBe(mocks.testUser.id)
    })

    it("returns first non-self when current user is not in participants (edge case)", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      const peerA = { id: "peer-a" }
      const peerB = { id: "peer-b" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [{ id: "chat-1", participants: [peerA, peerB], unread_count: 0 }],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      const other = result.current.getOtherParticipant(result.current.activeChat!)
      expect(other).toEqual(peerA)
    })
  })

  describe("chat selection from URL params", () => {
    it("selectedChatId mirrors useParams.chatId on mount", async () => {
      mocks.paramsRef.current = { chatId: "chat-from-url" }
      mocks.chatApi.getChat.mockResolvedValue({
        id: "chat-from-url",
        participants: [{ id: "current-user-id" }, { id: "peer" }],
        unread_count: 0,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })

      await waitFor(() => {
        expect(result.current.selectedChatId).toBe("chat-from-url")
      })
    })

    it("selectedChatId is null when useParams.chatId is undefined", () => {
      mocks.paramsRef.current = {}

      const { result } = renderHook(() => useMessengerController(), { wrapper })

      expect(result.current.selectedChatId).toBeNull()
    })
  })

  describe("contacts derivation", () => {
    it("transforms chats into Contact[] with name/avatar/lastMessage from peer", async () => {
      mocks.paramsRef.current = {}
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [
              { id: "current-user-id" },
              { id: "peer", full_name: "Peer Name", avatar_url: "/peer.png" },
            ],
            unread_count: 5,
            last_message: { content: "last msg", created_at: new Date().toISOString() },
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })

      await waitFor(() => {
        expect(result.current.contacts).toHaveLength(1)
      })

      const contact = result.current.contacts[0]!
      expect(contact.id).toBe("chat-1")
      expect(contact.name).toBe("Peer Name")
      expect(contact.avatar).toBe("/peer.png")
      expect(contact.lastMessage).toBe("last msg")
      expect(contact.unread).toBe(5)
    })

    it("falls back to 'Unknown User' when peer has no full_name", async () => {
      mocks.paramsRef.current = {}
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.contacts).toHaveLength(1))
      expect(result.current.contacts[0]!.name).toBe("Unknown User")
    })
  })

  describe("confirmDialog state machine", () => {
    it("handleClearChat opens dialog with warning variant + clean i18n keys (W183 SW3)", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      expect(result.current.confirmDialog).toBeNull()

      act(() => {
        result.current.handleClearChat()
      })

      // W183 SW3 removed defaultValue antipattern — title/message use ONLY
      // t(key) without positional fallback string. Mock t() passes keys
      // through verbatim, so assertions check key NAME without fallback.
      expect(result.current.confirmDialog).toEqual(
        expect.objectContaining({
          open: true,
          variant: "warning",
          title: "messenger:clearChatTitle",
          message: "messenger:confirmClear",
        })
      )
    })

    it("handleDeleteChat opens dialog with danger variant + clean i18n keys", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      act(() => {
        result.current.handleDeleteChat()
      })

      expect(result.current.confirmDialog).toEqual(
        expect.objectContaining({
          open: true,
          variant: "danger",
          title: "messenger:deleteChatTitle",
          message: "messenger:confirmDelete",
        })
      )
    })

    it("does NOT open dialog when no chat is selected", () => {
      mocks.paramsRef.current = {}

      const { result } = renderHook(() => useMessengerController(), { wrapper })

      act(() => {
        result.current.handleClearChat()
      })

      expect(result.current.confirmDialog).toBeNull()
    })
  })
})
