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
    // Wave 205 SW6 — author-only edit / soft-delete
    editMessage: vi.fn(),
    deleteMessage: vi.fn(),
    // Wave 206 — emoji reactions
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
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
    // Wave 204 SW6 — the controller's room-lifecycle effect calls sendJoin/
    // sendLeave on chat-select; the mock must provide them or the effect throws.
    sendJoin: vi.fn(),
    sendLeave: vi.fn(),
    getTypingUsersForChat: () => [],
    unreadCount: 0,
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    // Wave 208 SW5 — the transform reads i18n.language for the absolute
    // date-divider label (formatDate locale). Provide a stable language so the
    // memo doesn't throw on `i18n.language`.
    i18n: { language: "en" },
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
  mocks.chatApi.editMessage.mockResolvedValue({ status: "ok" })
  mocks.chatApi.deleteMessage.mockResolvedValue({ status: "ok" })
  mocks.chatApi.addReaction.mockResolvedValue({ status: "ok" })
  mocks.chatApi.removeReaction.mockResolvedValue({ status: "ok" })
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
      // Wave 211 G4 — the DM no-name fallback moved from a hardcoded "Unknown
      // User" literal to t("messenger:unknownUser") (chatDisplayInfo). The mock
      // t(key) => key returns the key (file convention; see :433).
      expect(result.current.contacts[0]!.name).toBe("messenger:unknownUser")
    })

    it("renders a group chat with its name + member count, no presence (W211 G4)", async () => {
      mocks.paramsRef.current = {}
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "group-1",
            chat_type: "group",
            name: "Project Alpha",
            participants: [{ id: "current-user-id" }, { id: "peer-a" }, { id: "peer-b" }],
            unread_count: 2,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.contacts).toHaveLength(1))
      const contact = result.current.contacts[0]!
      expect(contact.isGroup).toBe(true)
      expect(contact.name).toBe("Project Alpha")
      expect(contact.memberCount).toBe(3)
      expect(contact.avatar).toBe("") // GroupAvatar renders the glyph, no photo
      expect(contact.online).toBe(false) // no per-user presence dot for a group
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

  // Wave 205 SW6 — inline edit + soft-delete (optimistic mutations). The
  // optimistic onMutate writes to the ["messages", chatId] cache which the
  // controller's messages query observes, so result.current.messages reflects
  // the optimistic value (and the rollback) without any refetch — exactly the
  // behaviour these tests assert. retry: 2 on the cache-assert describe blocks
  // matches the W183 Blob-lifecycle pattern (Windows parallel-IPC flake).
  describe("Wave 205 SW6 — inline edit state machine", () => {
    const seedSelectedChat = () => {
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
    }

    it("handleEditMessage seeds editingMessageId + editingMessageContent", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      act(() => result.current.handleEditMessage("msg-1", "hello"))
      expect(result.current.editingMessageId).toBe("msg-1")
      expect(result.current.editingMessageContent).toBe("hello")
    })

    it("handleCancelEdit clears the editor state", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      act(() => result.current.handleEditMessage("msg-1", "hello"))
      act(() => result.current.handleCancelEdit())
      expect(result.current.editingMessageId).toBeNull()
      expect(result.current.editingMessageContent).toBe("")
    })

    it("handleSaveEdit closes the editor + skips the mutation on whitespace-only content", async () => {
      seedSelectedChat()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => result.current.handleEditMessage("msg-1", "x"))
      act(() => result.current.setEditingMessageContent("   "))
      act(() => result.current.handleSaveEdit("msg-1"))

      expect(result.current.editingMessageId).toBeNull()
      expect(mocks.chatApi.editMessage).not.toHaveBeenCalled()
    })
  })

  describe("Wave 205 SW6 — optimistic edit/delete mutations", { retry: 2 }, () => {
    const seedChatWithMessage = () => {
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
      mocks.chatApi.getMessages.mockResolvedValue({
        items: [
          {
            id: "msg-1",
            chat_id: "chat-1",
            sender_id: "current-user-id",
            content: "original",
            created_at: new Date().toISOString(),
            read_status: false,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("optimistically updates content + editedAt on save (success)", async () => {
      seedChatWithMessage()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.text).toBe("original")
      )

      act(() => result.current.handleEditMessage("msg-1", "original"))
      act(() => result.current.setEditingMessageContent("edited!"))
      await act(async () => {
        result.current.handleSaveEdit("msg-1")
      })

      await waitFor(() => {
        const m = result.current.messages.find((msg) => msg.id === "msg-1")
        expect(m?.text).toBe("edited!")
        expect(m?.editedAt).toBeTruthy()
      })
      expect(mocks.chatApi.editMessage).toHaveBeenCalledWith("chat-1", "msg-1", "edited!")
    })

    it("rolls back content on edit mutation error", async () => {
      seedChatWithMessage()
      mocks.chatApi.editMessage.mockRejectedValue(new Error("network fail"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.text).toBe("original")
      )

      act(() => result.current.handleEditMessage("msg-1", "original"))
      act(() => result.current.setEditingMessageContent("edited!"))
      await act(async () => {
        result.current.handleSaveEdit("msg-1")
      })

      await waitFor(() => {
        const m = result.current.messages.find((msg) => msg.id === "msg-1")
        expect(m?.text).toBe("original")
        expect(m?.editedAt).toBeFalsy()
      })
    })

    it("handleDeleteMessage opens a danger confirm dialog with the W205 i18n keys", async () => {
      seedChatWithMessage()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => result.current.handleDeleteMessage("msg-1"))

      expect(result.current.confirmDialog).toEqual(
        expect.objectContaining({
          open: true,
          variant: "danger",
          title: "messenger:deleteMessageTitle",
          message: "messenger:confirmDeleteMessage",
        })
      )
    })

    it("optimistically tombstones the message (deletedAt set + content cleared) on confirm (success)", async () => {
      seedChatWithMessage()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.text).toBe("original")
      )

      act(() => result.current.handleDeleteMessage("msg-1"))
      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => {
        const m = result.current.messages.find((msg) => msg.id === "msg-1")
        expect(m?.deletedAt).toBeTruthy()
        expect(m?.text).toBe("")
      })
      expect(mocks.chatApi.deleteMessage).toHaveBeenCalledWith("chat-1", "msg-1")
    })

    it("rolls back the tombstone on delete mutation error", async () => {
      seedChatWithMessage()
      mocks.chatApi.deleteMessage.mockRejectedValue(new Error("fail"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.text).toBe("original")
      )

      act(() => result.current.handleDeleteMessage("msg-1"))
      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => {
        const m = result.current.messages.find((msg) => msg.id === "msg-1")
        expect(m?.deletedAt).toBeFalsy()
        expect(m?.text).toBe("original")
      })
    })
  })

  // Wave 206 — emoji reaction toggle (optimistic). handleToggleReaction reads
  // currentlyReacted from the live ["messages", chatId] cache, then optimistically
  // flips the aggregate (count ±1 + reactedByMe) before the add/remove request.
  // The transform maps the cached API shape (reacted_by_me) to the UI shape
  // (reactedByMe), so result.current.messages reflects it without a refetch.
  describe("Wave 206 — optimistic reaction toggle", { retry: 2 }, () => {
    const seedChatWithReactions = (
      reactions?: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
    ) => {
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
      mocks.chatApi.getMessages.mockResolvedValue({
        items: [
          {
            id: "msg-1",
            chat_id: "chat-1",
            sender_id: "current-user-id",
            content: "hi",
            created_at: new Date().toISOString(),
            read_status: false,
            ...(reactions ? { reactions } : {}),
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("adds a reaction (count 1 + reactedByMe) + calls addReaction when not yet reacted", async () => {
      seedChatWithReactions()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")).toBeTruthy()
      )

      await act(async () => {
        result.current.handleToggleReaction("msg-1", "👍")
      })

      await waitFor(() => {
        const r = result.current.messages.find((m) => m.id === "msg-1")?.reactions
        expect(r).toEqual([{ emoji: "👍", count: 1, reactedByMe: true }])
      })
      expect(mocks.chatApi.addReaction).toHaveBeenCalledWith("chat-1", "msg-1", "👍")
      expect(mocks.chatApi.removeReaction).not.toHaveBeenCalled()
    })

    it("removes a reaction + calls removeReaction when already reacted", async () => {
      seedChatWithReactions([{ emoji: "👍", count: 1, reacted_by_me: true }])
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.reactions).toEqual([
          { emoji: "👍", count: 1, reactedByMe: true },
        ])
      )

      await act(async () => {
        result.current.handleToggleReaction("msg-1", "👍")
      })

      await waitFor(() => {
        const r = result.current.messages.find((m) => m.id === "msg-1")?.reactions
        expect(r).toEqual([])
      })
      expect(mocks.chatApi.removeReaction).toHaveBeenCalledWith("chat-1", "msg-1", "👍")
      expect(mocks.chatApi.addReaction).not.toHaveBeenCalled()
    })

    it("rolls back the optimistic reaction on mutation error", async () => {
      seedChatWithReactions([])
      mocks.chatApi.addReaction.mockRejectedValue(new Error("network fail"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")?.reactions).toEqual([])
      )

      await act(async () => {
        result.current.handleToggleReaction("msg-1", "👍")
      })

      await waitFor(() => {
        const r = result.current.messages.find((m) => m.id === "msg-1")?.reactions
        expect(r).toEqual([])
      })
    })
  })

  // Wave 208 SW5 — date dividers + sender grouping. The transform annotates each
  // message with showDateDivider/dateLabel/isGroupStart; result.current.messages
  // reflects them (transformedMessages flows through optimisticMessages). retry: 2
  // absorbs the rare midnight straddle between the test's `new Date()` and the
  // transform's, matching the codebase hook-timing-flake convention.
  describe("Wave 208 SW5 — date dividers + sender grouping", { retry: 2 }, () => {
    const seedChatWithMessages = (
      items: Array<{ id: string; sender_id: string; content: string; created_at: string }>
    ) => {
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
      mocks.chatApi.getMessages.mockResolvedValue({
        items: items.map((it) => ({ ...it, chat_id: "chat-1", read_status: false })),
        has_more: false,
        next_cursor: null,
      })
    }

    it("marks a date divider + group start on the first message of each calendar day", async () => {
      const now = new Date()
      const yesterdayNoon = new Date(now)
      yesterdayNoon.setDate(now.getDate() - 1)
      yesterdayNoon.setHours(12, 0, 0, 0)
      const today9 = new Date(now)
      today9.setHours(9, 0, 0, 0)
      const today902 = new Date(today9)
      today902.setMinutes(2)
      seedChatWithMessages([
        {
          id: "A",
          sender_id: "current-user-id",
          content: "a",
          created_at: yesterdayNoon.toISOString(),
        },
        { id: "B", sender_id: "current-user-id", content: "b", created_at: today9.toISOString() },
        { id: "C", sender_id: "current-user-id", content: "c", created_at: today902.toISOString() },
      ])

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.messages).toHaveLength(3))
      const get = (id: string) => result.current.messages.find((m) => m.id === id)

      // A — first message: divider (yesterday label) + group start.
      expect(get("A")?.showDateDivider).toBe(true)
      expect(get("A")?.isGroupStart).toBe(true)
      expect(get("A")?.dateLabel).toBe("messenger:dateDivider.yesterday")
      // B — new calendar day: divider (today label) + group start.
      expect(get("B")?.showDateDivider).toBe(true)
      expect(get("B")?.isGroupStart).toBe(true)
      expect(get("B")?.dateLabel).toBe("messenger:dateDivider.today")
      // C — same day + same sender within 5min: no divider, grouped.
      expect(get("C")?.showDateDivider).toBe(false)
      expect(get("C")?.isGroupStart).toBe(false)
      expect(get("C")?.dateLabel).toBeUndefined()
    })

    it("starts a new group on a different sender or a > 5min gap (same day)", async () => {
      const now = new Date()
      const base = new Date(now)
      base.setHours(9, 0, 0, 0)
      const at = (mins: number) => {
        const d = new Date(base)
        d.setMinutes(mins)
        return d.toISOString()
      }
      seedChatWithMessages([
        { id: "M1", sender_id: "current-user-id", content: "1", created_at: at(0) },
        { id: "M2", sender_id: "current-user-id", content: "2", created_at: at(1) },
        { id: "M3", sender_id: "peer", content: "3", created_at: at(2) },
        { id: "M4", sender_id: "peer", content: "4", created_at: at(15) },
      ])

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.messages).toHaveLength(4))
      const get = (id: string) => result.current.messages.find((m) => m.id === id)

      expect(get("M1")?.isGroupStart).toBe(true) // first
      expect(get("M2")?.isGroupStart).toBe(false) // same sender, +1min
      expect(get("M3")?.isGroupStart).toBe(true) // different sender
      expect(get("M4")?.isGroupStart).toBe(true) // same sender as M3 but +13min gap
      // All same calendar day → only the first message shows a divider.
      expect(get("M1")?.showDateDivider).toBe(true)
      expect(get("M2")?.showDateDivider).toBe(false)
      expect(get("M3")?.showDateDivider).toBe(false)
      expect(get("M4")?.showDateDivider).toBe(false)
    })

    it("uses an absolute localized date label for messages older than yesterday", async () => {
      const now = new Date()
      const lastWeek = new Date(now)
      lastWeek.setDate(now.getDate() - 7)
      lastWeek.setHours(12, 0, 0, 0)
      seedChatWithMessages([
        {
          id: "OLD",
          sender_id: "current-user-id",
          content: "old",
          created_at: lastWeek.toISOString(),
        },
      ])

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.messages).toHaveLength(1))
      const old = result.current.messages.find((m) => m.id === "OLD")

      expect(old?.showDateDivider).toBe(true)
      expect(old?.isGroupStart).toBe(true)
      // Absolute formatted date — NOT the relative today/yesterday i18n keys.
      expect(old?.dateLabel).toBeTruthy()
      expect(old?.dateLabel).not.toBe("messenger:dateDivider.today")
      expect(old?.dateLabel).not.toBe("messenger:dateDivider.yesterday")
    })
  })
})
