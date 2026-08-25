import { renderHook, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

/**
 * Session-14 Lane-C branch top-up for useMessengerController.
 *
 * Sibling to useMessengerController.test.tsx — drives the mutation HANDLERS +
 * group/forward/profile handlers + the visibility / room-lifecycle effects that
 * the existing test leaves uncovered. Same hoisted-mock scaffold; vitest
 * isolates each file so this can't break the existing one.
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
    createGroup: vi.fn(),
    renameChat: vi.fn(),
    addParticipant: vi.fn(),
    removeParticipant: vi.fn(),
    forwardMessages: vi.fn(),
    clearChat: vi.fn(),
    deleteChat: vi.fn(),
    editMessage: vi.fn(),
    deleteMessage: vi.fn(),
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
  },
  navigate: vi.fn(),
  paramsRef: { current: {} as { chatId?: string } },
  presenceMap: {} as Record<string, { active?: boolean }>,
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
    presenceMap: mocks.presenceMap,
    isConnected: true,
    sendTyping: vi.fn(),
    sendRead: vi.fn(),
    sendJoin: vi.fn(),
    sendLeave: vi.fn(),
    getTypingUsersForChat: () => [],
    unreadCount: 0,
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

// Import after mocks are registered.
import { useMessengerController } from "../useMessengerController"

const seedChat = (chatId = "chat-1", extra: Record<string, unknown> = {}) => {
  mocks.paramsRef.current = { chatId }
  mocks.chatApi.getChats.mockResolvedValue({
    items: [
      {
        id: chatId,
        participants: [{ id: "current-user-id" }, { id: "peer", full_name: "Peer" }],
        unread_count: 0,
        ...extra,
      },
    ],
    has_more: false,
    next_cursor: null,
  })
}

const seedGroup = (chatId = "group-1") => {
  mocks.paramsRef.current = { chatId }
  mocks.chatApi.getChats.mockResolvedValue({
    items: [
      {
        id: chatId,
        chat_type: "group",
        name: "Project Alpha",
        created_by: "current-user-id",
        participants: [{ id: "current-user-id" }, { id: "peer-a" }, { id: "peer-b" }],
        unread_count: 0,
      },
    ],
    has_more: false,
    next_cursor: null,
  })
}

// ---------- Setup ----------

beforeEach(() => {
  vi.clearAllMocks()
  mocks.paramsRef.current = {}
  mocks.presenceMap = {}

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

  mocks.chatApi.getChats.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
  mocks.chatApi.getChat.mockResolvedValue(null)
  mocks.chatApi.getMessages.mockResolvedValue({ items: [], has_more: false, next_cursor: null })
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
  mocks.chatApi.createChat.mockResolvedValue({
    id: "new-chat-id",
    participants: [],
    unread_count: 0,
  })
  mocks.chatApi.createGroup.mockResolvedValue({
    id: "new-group-id",
    chat_type: "group",
    participants: [],
    unread_count: 0,
  })
  mocks.chatApi.renameChat.mockResolvedValue({ status: "ok" })
  mocks.chatApi.addParticipant.mockResolvedValue({ status: "ok" })
  mocks.chatApi.removeParticipant.mockResolvedValue({ status: "ok" })
  mocks.chatApi.forwardMessages.mockResolvedValue([{ id: "fwd-1" }])
  mocks.chatApi.clearChat.mockResolvedValue({ status: "ok" })
  mocks.chatApi.deleteChat.mockResolvedValue({ status: "ok" })
  mocks.apiClient.get.mockResolvedValue({ data: mocks.testUser })
})

afterEach(() => {
  // Scoped restore — do NOT vi.restoreAllMocks() (wipes URL spies before
  // testing-library's auto-unmount flushes effect cleanups).
  mocks.revokeObjectURL.mockReset().mockImplementation(() => {})
  mocks.createObjectURL.mockReset().mockReturnValue("blob:mock-url")
})

// ---------- Tests ----------

describe("useMessengerController — branch top-up", () => {
  describe("createChat / createGroup mutations (386-403)", () => {
    it("handleCreateChat navigates to the new chat + closes the modal on success", async () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })

      act(() => result.current.setIsNewChatModalOpen(true))
      expect(result.current.isNewChatModalOpen).toBe(true)

      await act(async () => {
        result.current.handleCreateChat("peer-id")
      })

      await waitFor(() => {
        expect(mocks.navigate).toHaveBeenCalledWith({
          to: "/messenger/$chatId",
          params: { chatId: "new-chat-id" },
        })
      })
      expect(mocks.chatApi.createChat).toHaveBeenCalledWith("peer-id")
      await waitFor(() => expect(result.current.isNewChatModalOpen).toBe(false))
    })

    it("handleCreateGroup creates a group, navigates, closes the modal", async () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })

      act(() => result.current.setIsNewChatModalOpen(true))

      await act(async () => {
        result.current.handleCreateGroup("Team", ["a", "b"])
      })

      await waitFor(() => {
        expect(mocks.chatApi.createGroup).toHaveBeenCalledWith("Team", ["a", "b"])
      })
      await waitFor(() => {
        expect(mocks.navigate).toHaveBeenCalledWith({
          to: "/messenger/$chatId",
          params: { chatId: "new-group-id" },
        })
      })
      await waitFor(() => expect(result.current.isNewChatModalOpen).toBe(false))
    })
  })

  describe("group member management (408-438, 886-915)", () => {
    it("handleRenameGroup dispatches renameChat with the trimmed name", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("group-1"))

      await act(async () => {
        result.current.handleRenameGroup("  New Name  ")
      })

      await waitFor(() => {
        expect(mocks.chatApi.renameChat).toHaveBeenCalledWith("group-1", "New Name")
      })
    })

    it("handleRenameGroup is a no-op on a blank name", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("group-1"))

      act(() => result.current.handleRenameGroup("   "))

      expect(mocks.chatApi.renameChat).not.toHaveBeenCalled()
    })

    it("handleAddMember dispatches addParticipant", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("group-1"))

      await act(async () => {
        result.current.handleAddMember("new-member")
      })

      await waitFor(() => {
        expect(mocks.chatApi.addParticipant).toHaveBeenCalledWith("group-1", "new-member")
      })
    })

    it("handleAddMember is a no-op when no chat is selected", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      act(() => result.current.handleAddMember("x"))
      expect(mocks.chatApi.addParticipant).not.toHaveBeenCalled()
    })

    it("handleRemoveMember (kick a peer) opens a danger dialog with the remove keys", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("group-1"))

      act(() => result.current.handleRemoveMember("peer-a"))

      expect(result.current.confirmDialog).toEqual(
        expect.objectContaining({
          open: true,
          variant: "danger",
          title: "messenger:removeMemberTitle",
          message: "messenger:confirmRemoveMember",
          confirmText: "messenger:removeMemberConfirm",
        })
      )

      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => {
        expect(mocks.chatApi.removeParticipant).toHaveBeenCalledWith("group-1", "peer-a")
      })
      expect(result.current.confirmDialog).toBeNull()
    })

    it("handleRemoveMember (leave self) opens the leave dialog + navigates away on confirm", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("group-1"))

      act(() => result.current.setShowGroupInfo(true))
      act(() => result.current.handleRemoveMember("current-user-id"))

      expect(result.current.confirmDialog).toEqual(
        expect.objectContaining({
          title: "messenger:leaveGroup",
          message: "messenger:confirmLeaveGroup",
        })
      )

      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => {
        expect(mocks.chatApi.removeParticipant).toHaveBeenCalledWith("group-1", "current-user-id")
      })
      // removeParticipant onSuccess: self-removal closes the panel + navigates.
      await waitFor(() => {
        expect(mocks.navigate).toHaveBeenCalledWith({ to: "/messenger" })
      })
      await waitFor(() => expect(result.current.showGroupInfo).toBe(false))
    })

    it("handleRemoveMember is a no-op when no chat is selected", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      act(() => result.current.handleRemoveMember("x"))
      expect(result.current.confirmDialog).toBeNull()
    })
  })

  describe("reply compose (304-310, 783-789, 823-831)", () => {
    const seedReplyTarget = () => {
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
            id: "msg-target",
            chat_id: "chat-1",
            sender_id: "peer",
            content: "quote me",
            created_at: new Date().toISOString(),
            read_status: false,
            sender: { full_name: "Peer Name", avatar_url: "/peer.png" },
            reply_to: {
              id: "older",
              sender_id: "current-user-id",
              sender_name: "Me",
              content: "the original",
              deleted_at: null,
            },
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("transform maps reply_to into a UI replyTo with resolved isMe", async () => {
      seedReplyTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-target")).toBeTruthy()
      )
      const m = result.current.messages.find((msg) => msg.id === "msg-target")
      expect(m?.replyTo).toEqual({
        id: "older",
        senderName: "Me",
        isMe: true, // reply_to.sender_id === current user
        text: "the original",
        deletedAt: null,
      })
    })

    it("handleStartReply sets replyingTo from the resolved message", async () => {
      seedReplyTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-target")).toBeTruthy()
      )

      act(() => result.current.handleStartReply("msg-target"))

      expect(result.current.replyingTo).toEqual({
        id: "msg-target",
        senderName: "Peer Name",
        isMe: false,
        text: "quote me",
      })
    })

    it("handleStartReply is a no-op on an unknown message id", async () => {
      seedReplyTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-target")).toBeTruthy()
      )
      act(() => result.current.handleStartReply("nonexistent"))
      expect(result.current.replyingTo).toBeNull()
    })

    it("handleCancelReply clears replyingTo", async () => {
      seedReplyTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-target")).toBeTruthy()
      )
      act(() => result.current.handleStartReply("msg-target"))
      expect(result.current.replyingTo).not.toBeNull()
      act(() => result.current.handleCancelReply())
      expect(result.current.replyingTo).toBeNull()
    })

    it("handleSendMessage threads replyToMessageId + builds optimistic replyTo, then clears it", async () => {
      seedReplyTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-target")).toBeTruthy()
      )

      act(() => result.current.handleStartReply("msg-target"))
      expect(result.current.replyingTo?.id).toBe("msg-target")

      await act(async () => {
        result.current.handleSendMessage("my reply", [])
      })

      expect(mocks.chatApi.sendMessage).toHaveBeenCalledWith("chat-1", "my reply", [], "msg-target")
      // Reply context cleared once the send is dispatched.
      expect(result.current.replyingTo).toBeNull()
    })
  })

  describe("forward (842-864, 444-460)", () => {
    const seedForwardTarget = () => {
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
            id: "msg-fwd",
            chat_id: "chat-1",
            sender_id: "peer",
            content: "forward me",
            created_at: new Date().toISOString(),
            read_status: false,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("handleStartForward opens the picker for a valid message", async () => {
      seedForwardTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-fwd")).toBeTruthy()
      )
      act(() => result.current.handleStartForward("msg-fwd"))
      expect(result.current.forwardSourceMessageId).toBe("msg-fwd")
    })

    it("handleStartForward is a no-op on an unknown id", async () => {
      seedForwardTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-fwd")).toBeTruthy()
      )
      act(() => result.current.handleStartForward("nope"))
      expect(result.current.forwardSourceMessageId).toBeNull()
    })

    it("handleCancelForward clears forwardSourceMessageId", async () => {
      seedForwardTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-fwd")).toBeTruthy()
      )
      act(() => result.current.handleStartForward("msg-fwd"))
      act(() => result.current.handleCancelForward())
      expect(result.current.forwardSourceMessageId).toBeNull()
    })

    it("handleForwardToChat dispatches the forward + navigates to the destination on success", async () => {
      seedForwardTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-fwd")).toBeTruthy()
      )

      act(() => result.current.handleStartForward("msg-fwd"))

      await act(async () => {
        result.current.handleForwardToChat("dest-chat")
      })

      expect(mocks.chatApi.forwardMessages).toHaveBeenCalledWith("dest-chat", "chat-1", ["msg-fwd"])
      await waitFor(() => {
        expect(mocks.navigate).toHaveBeenCalledWith({
          to: "/messenger/$chatId",
          params: { chatId: "dest-chat" },
        })
      })
      // onSuccess clears the picker.
      await waitFor(() => expect(result.current.forwardSourceMessageId).toBeNull())
    })

    it("handleForwardToChat is a no-op when nothing is being forwarded", async () => {
      seedForwardTarget()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))
      act(() => result.current.handleForwardToChat("dest-chat"))
      expect(mocks.chatApi.forwardMessages).not.toHaveBeenCalled()
    })
  })

  describe("attachments transform (284-289)", () => {
    it("maps server attachments to the UI shape", async () => {
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
            id: "msg-att",
            chat_id: "chat-1",
            sender_id: "peer",
            content: "see file",
            created_at: new Date().toISOString(),
            read_status: false,
            attachments: [
              { id: "att-1", url: "/f.png", file_type: "image", filename: "f.png", size: 123 },
            ],
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-att")).toBeTruthy()
      )
      const m = result.current.messages.find((msg) => msg.id === "msg-att")
      expect(m?.attachments).toEqual([
        { id: "att-1", url: "/f.png", type: "image", name: "f.png", size: 123 },
      ])
    })
  })

  describe("clear chat optimistic mutation (464-512)", () => {
    const seedChatWithMessage = () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 3,
            last_message: { content: "last", created_at: new Date().toISOString() },
          },
          {
            id: "chat-2",
            participants: [{ id: "current-user-id" }, { id: "peer-2" }],
            unread_count: 1,
            last_message: { content: "keep", created_at: new Date().toISOString() },
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
            sender_id: "peer",
            content: "to clear",
            created_at: new Date().toISOString(),
            read_status: false,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("optimistically empties the message list + closes the menu on confirm (success)", async () => {
      seedChatWithMessage()
      // After clear, the server returns an empty message list (onSettled
      // invalidates ["messages"] → refetch reflects the cleared server state).
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")).toBeTruthy()
      )
      mocks.chatApi.getMessages.mockResolvedValue({
        items: [],
        has_more: false,
        next_cursor: null,
      })

      act(() => result.current.setShowChatMenu(true))
      act(() => result.current.handleClearChat())

      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => expect(result.current.messages).toHaveLength(0))
      expect(mocks.chatApi.clearChat).toHaveBeenCalledWith("chat-1")
      // onSuccess closes the menu (not reverted by the onSettled refetch).
      await waitFor(() => expect(result.current.showChatMenu).toBe(false))
    })

    it("rolls back the cleared messages on error", async () => {
      seedChatWithMessage()
      mocks.chatApi.clearChat.mockRejectedValue(new Error("fail"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() =>
        expect(result.current.messages.find((m) => m.id === "msg-1")).toBeTruthy()
      )

      act(() => result.current.handleClearChat())
      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => {
        expect(result.current.messages.find((m) => m.id === "msg-1")?.text).toBe("to clear")
      })
    })
  })

  describe("delete chat optimistic mutation (514-545)", () => {
    const seedTwoChats = () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-1",
            participants: [{ id: "current-user-id" }, { id: "peer" }],
            unread_count: 0,
          },
          {
            id: "chat-2",
            participants: [{ id: "current-user-id" }, { id: "peer2" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })
    }

    it("optimistically removes the chat + navigates away from the selected one (success)", async () => {
      seedTwoChats()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.contacts).toHaveLength(2))

      // After delete, the server list omits chat-1 (onSettled invalidates
      // ["chats"] → refetch reflects the deleted server state).
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          {
            id: "chat-2",
            participants: [{ id: "current-user-id" }, { id: "peer2" }],
            unread_count: 0,
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      act(() => result.current.handleDeleteChat())
      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() =>
        expect(result.current.contacts.some((c) => c.id === "chat-1")).toBe(false)
      )
      expect(mocks.chatApi.deleteChat).toHaveBeenCalledWith("chat-1")
      // onMutate navigates away because chat-1 was the selected chat.
      expect(mocks.navigate).toHaveBeenCalledWith({ to: "/messenger" })
    })

    it("rolls back the removed chat on error", async () => {
      seedTwoChats()
      mocks.chatApi.deleteChat.mockRejectedValue(new Error("fail"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.contacts).toHaveLength(2))

      act(() => result.current.handleDeleteChat())
      await act(async () => {
        result.current.confirmDialog?.onConfirm()
      })

      await waitFor(() => expect(result.current.contacts).toHaveLength(2))
    })

    it("does not navigate away when the route changes before delete confirmation", async () => {
      seedTwoChats()
      const { result, rerender } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => result.current.handleDeleteChat())
      const confirmDelete = result.current.confirmDialog?.onConfirm
      expect(confirmDelete).toBeTypeOf("function")

      mocks.paramsRef.current = { chatId: "chat-2" }
      rerender()
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-2"))
      mocks.navigate.mockClear()

      act(() => confirmDelete?.())

      await waitFor(() => expect(mocks.chatApi.deleteChat).toHaveBeenCalledWith("chat-1"))
      expect(mocks.navigate).not.toHaveBeenCalledWith({ to: "/messenger" })
    })
  })

  describe("profile modal (1010-1027)", () => {
    it("handleViewProfile loads the peer profile on success + closes the menu", async () => {
      seedChat()
      mocks.apiClient.get.mockResolvedValue({ data: { id: "peer", full_name: "Peer" } })
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      act(() => result.current.setShowChatMenu(true))

      await act(async () => {
        result.current.handleViewProfile()
      })

      await waitFor(() => {
        expect(result.current.profileUser).toEqual({ id: "peer", full_name: "Peer" })
      })
      expect(mocks.apiClient.get).toHaveBeenCalledWith("/users/peer")
      expect(result.current.showChatMenu).toBe(false)
      expect(result.current.isProfileLoading).toBe(false)
      expect(result.current.profileError).toBeNull()
    })

    it("handleViewProfile sets profileError on fetch failure", async () => {
      seedChat()
      mocks.apiClient.get.mockRejectedValue(new Error("boom"))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      await act(async () => {
        result.current.handleViewProfile()
      })

      await waitFor(() => {
        expect(result.current.profileError).toBe("messenger:profileLoadError")
      })
      expect(result.current.isProfileLoading).toBe(false)
      expect(result.current.profileUser).toBeNull()
    })

    it("handleViewProfile is a no-op when there is no other participant", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      act(() => result.current.handleViewProfile())
      expect(mocks.apiClient.get).not.toHaveBeenCalled()
      expect(result.current.isProfileLoading).toBe(false)
    })

    it("handleCloseProfile resets all profile state", async () => {
      seedChat()
      mocks.apiClient.get.mockResolvedValue({ data: { id: "peer", full_name: "Peer" } })
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("chat-1"))

      await act(async () => {
        result.current.handleViewProfile()
      })
      await waitFor(() => expect(result.current.profileUser).not.toBeNull())

      act(() => result.current.handleCloseProfile())
      expect(result.current.profileUser).toBeNull()
      expect(result.current.isProfileLoading).toBe(false)
      expect(result.current.profileError).toBeNull()
    })
  })

  describe("markRead effects (693-743)", () => {
    it("marks the chat read on selection", async () => {
      seedChat()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))
      await waitFor(() => expect(mocks.chatApi.markRead).toHaveBeenCalledWith("chat-1"))
    })

    it("re-marks read on visibilitychange while a chat is open (736-743)", async () => {
      seedChat()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))
      await waitFor(() => expect(mocks.chatApi.markRead).toHaveBeenCalled())

      mocks.chatApi.markRead.mockClear()
      await act(async () => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          value: "hidden",
        })
        document.dispatchEvent(new Event("visibilitychange"))
      })
      expect(mocks.chatApi.markRead).not.toHaveBeenCalled()

      await act(async () => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          value: "visible",
        })
        document.dispatchEvent(new Event("visibilitychange"))
      })

      // jsdom default visibilityState is "visible" → onVisible fires markAsRead.
      await waitFor(() => expect(mocks.chatApi.markRead).toHaveBeenCalledWith("chat-1"))
    })
  })

  describe("active chat display (1057-1060)", () => {
    it("exposes activeChatDisplay for a group", async () => {
      seedGroup()
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.activeChat?.id).toBe("group-1"))
      expect(result.current.activeChatDisplay).toEqual(
        expect.objectContaining({ isGroup: true, name: "Project Alpha", memberCount: 3 })
      )
    })

    it("activeChatDisplay is null when no chat is active", () => {
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      expect(result.current.activeChatDisplay).toBeNull()
    })
  })

  describe("message mutations without a cached message list", () => {
    it("keeps optimistic edit, delete, and reaction mutations safe before history resolves", async () => {
      seedChat()
      mocks.chatApi.getMessages.mockImplementation(() => new Promise(() => {}))
      mocks.chatApi.editMessage.mockResolvedValue({ status: "ok" })
      mocks.chatApi.deleteMessage.mockResolvedValue({ status: "ok" })
      mocks.chatApi.addReaction.mockResolvedValue({ status: "ok" })

      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => {
        result.current.handleEditMessage("uncached-edit", "before")
        result.current.setEditingMessageContent("after")
      })
      await waitFor(() => expect(result.current.editingMessageContent).toBe("after"))
      act(() => result.current.handleSaveEdit("uncached-edit"))
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalled())

      act(() => result.current.handleDeleteMessage("uncached-delete"))
      await act(async () => result.current.confirmDialog?.onConfirm())
      await waitFor(() => expect(mocks.chatApi.deleteMessage).toHaveBeenCalled())

      act(() => result.current.handleToggleReaction("uncached-reaction", "👍"))
      await waitFor(() => expect(mocks.chatApi.addReaction).toHaveBeenCalled())

      act(() =>
        result.current.handleSendMessage("uncached-send", [
          new File(["payload"], "note.txt", { type: "text/plain" }),
        ])
      )
      await waitFor(() => expect(mocks.chatApi.sendMessage).toHaveBeenCalled())
    })

    it("keeps every rollback path safe when neither chats nor messages have resolved", async () => {
      mocks.paramsRef.current = { chatId: "chat-1" }
      mocks.chatApi.getChats.mockImplementation(() => new Promise(() => {}))
      mocks.chatApi.getMessages.mockImplementation(() => new Promise(() => {}))
      mocks.chatApi.clearChat.mockRejectedValue(new Error("clear failed"))
      mocks.chatApi.deleteChat.mockRejectedValue(new Error("delete chat failed"))
      mocks.chatApi.editMessage.mockRejectedValue(new Error("edit failed"))
      mocks.chatApi.deleteMessage.mockRejectedValue(new Error("delete message failed"))
      mocks.chatApi.addReaction.mockRejectedValue(new Error("reaction failed"))

      const client = new QueryClient({
        defaultOptions: {
          queries: { retry: false, gcTime: 0 },
          mutations: { retry: false },
        },
      })
      const localWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const errorCount = () =>
        client
          .getMutationCache()
          .getAll()
          .filter((mutation) => mutation.state.status === "error").length
      const { result } = renderHook(() => useMessengerController(), { wrapper: localWrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => result.current.handleClearChat())
      act(() => result.current.confirmDialog?.onConfirm())
      await waitFor(() => expect(mocks.chatApi.clearChat).toHaveBeenCalledWith("chat-1"))
      await waitFor(() => expect(errorCount()).toBeGreaterThanOrEqual(1))

      act(() => result.current.handleDeleteChat())
      act(() => result.current.confirmDialog?.onConfirm())
      await waitFor(() => expect(mocks.chatApi.deleteChat).toHaveBeenCalledWith("chat-1"))
      await waitFor(() => expect(errorCount()).toBeGreaterThanOrEqual(2))

      act(() => client.removeQueries({ queryKey: ["messages", "chat-1"], exact: true }))
      expect(client.getQueryData(["messages", "chat-1"])).toBeUndefined()
      act(() => {
        result.current.handleEditMessage("uncached-edit", "before")
        result.current.setEditingMessageContent("after")
      })
      await waitFor(() => expect(result.current.editingMessageContent).toBe("after"))
      act(() => result.current.handleSaveEdit("uncached-edit"))
      await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalled())
      await waitFor(() => expect(errorCount()).toBeGreaterThanOrEqual(3))

      act(() => client.removeQueries({ queryKey: ["messages", "chat-1"], exact: true }))
      expect(client.getQueryData(["messages", "chat-1"])).toBeUndefined()
      act(() => result.current.handleDeleteMessage("uncached-delete"))
      act(() => result.current.confirmDialog?.onConfirm())
      await waitFor(() => expect(mocks.chatApi.deleteMessage).toHaveBeenCalled())
      await waitFor(() => expect(errorCount()).toBeGreaterThanOrEqual(4))

      act(() => client.removeQueries({ queryKey: ["messages", "chat-1"], exact: true }))
      expect(client.getQueryData(["messages", "chat-1"])).toBeUndefined()
      act(() => result.current.handleToggleReaction("uncached-reaction", "👍"))
      await waitFor(() => expect(mocks.chatApi.addReaction).toHaveBeenCalled())
      await waitFor(() => expect(errorCount()).toBeGreaterThanOrEqual(5))
    })

    it("handles a remove-reaction race after the cache entry disappears", async () => {
      seedChat()
      mocks.chatApi.getMessages.mockImplementation(() => new Promise(() => {}))
      mocks.chatApi.removeReaction.mockResolvedValue({ status: "ok" })
      const client = new QueryClient({
        defaultOptions: {
          queries: { retry: false, gcTime: 0 },
          mutations: { retry: false },
        },
      })
      const localWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      let releaseCancel!: () => void
      const cancelGate = new Promise<void>((resolve) => {
        releaseCancel = resolve
      })
      const cancelQueries = vi.spyOn(client, "cancelQueries").mockReturnValue(cancelGate)
      const { result } = renderHook(() => useMessengerController(), { wrapper: localWrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))
      client.setQueryData(["messages", "chat-1"], {
        items: [
          {
            id: "reaction-race",
            chat_id: "chat-1",
            sender_id: "peer",
            content: "race",
            created_at: "2026-08-18T00:00:00Z",
            read_status: false,
            reactions: [{ emoji: "👍", count: 1, reacted_by_me: true }],
          },
        ],
        has_more: false,
        next_cursor: null,
      })

      act(() => result.current.handleToggleReaction("reaction-race", "👍"))
      await waitFor(() => expect(cancelQueries).toHaveBeenCalled())
      client.setQueryData(["messages", "chat-1"], {
        items: [
          {
            id: "reaction-race",
            chat_id: "chat-1",
            sender_id: "peer",
            content: "race",
            created_at: "2026-08-18T00:00:00Z",
            read_status: false,
            reactions: [],
          },
        ],
        has_more: false,
        next_cursor: null,
      })
      releaseCancel()

      await waitFor(() =>
        expect(mocks.chatApi.removeReaction).toHaveBeenCalledWith("chat-1", "reaction-race", "👍")
      )
    })
  })

  it("makes no selected-chat mutations no-ops", () => {
    const { result } = renderHook(() => useMessengerController(), { wrapper })

    act(() => {
      result.current.handleSendMessage("ignored", [])
      result.current.handleDeleteChat()
      result.current.handleSaveEdit("ignored-edit")
      result.current.handleDeleteMessage("ignored-delete")
      result.current.handleToggleReaction("ignored-reaction", "👍")
    })

    expect(result.current.confirmDialog).toBeNull()
    expect(mocks.chatApi.sendMessage).not.toHaveBeenCalled()
    expect(mocks.chatApi.deleteChat).not.toHaveBeenCalled()
    expect(mocks.chatApi.editMessage).not.toHaveBeenCalled()
    expect(mocks.chatApi.deleteMessage).not.toHaveBeenCalled()
    expect(mocks.chatApi.addReaction).not.toHaveBeenCalled()
  })

  it("marks the latest read message sent by the current user", async () => {
    seedChat()
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [
        {
          id: "read-own",
          chat_id: "chat-1",
          sender_id: "current-user-id",
          content: "already seen",
          created_at: "2026-07-30T10:00:00Z",
          read_status: true,
          read_at: "2026-07-30T10:01:00Z",
        },
        {
          id: "unread-peer",
          chat_id: "chat-1",
          sender_id: "peer",
          content: "reply",
          created_at: "2026-07-30T10:02:00Z",
          read_status: false,
        },
      ],
      has_more: false,
      next_cursor: null,
    })

    const { result } = renderHook(() => useMessengerController(), { wrapper })
    await waitFor(() => expect(result.current.messages).toHaveLength(2))

    expect(result.current.messages.find((message) => message.id === "read-own")?.isLastRead).toBe(
      true
    )
  })

  it("uses the live DM presence state for contact online status", async () => {
    mocks.presenceMap = { peer: { active: true } }
    seedChat("chat-1", { last_message: { content: "", created_at: "" } })
    const { result } = renderHook(() => useMessengerController(), { wrapper })

    await waitFor(() => expect(result.current.contacts[0]?.online).toBe(true))
  })

  it("does not append a server message that is already cached", async () => {
    seedChat()
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [
        {
          id: "server-msg-id",
          chat_id: "chat-1",
          sender_id: "current-user-id",
          content: "already there",
          created_at: "2026-07-30T10:00:00Z",
          read_status: false,
        },
      ],
      has_more: false,
      next_cursor: null,
    })

    const { result } = renderHook(() => useMessengerController(), { wrapper })
    await waitFor(() => expect(result.current.messages).toHaveLength(1))

    act(() => result.current.handleSendMessage("duplicate", []))
    await waitFor(() => expect(mocks.chatApi.sendMessage).toHaveBeenCalled())
    expect(
      result.current.messages.filter((message) => message.id === "server-msg-id")
    ).toHaveLength(1)
  })

  it("keeps an unrelated message unchanged during an edit mutation", async () => {
    seedChat()
    mocks.chatApi.getMessages.mockResolvedValue({
      items: [
        {
          id: "other-message",
          chat_id: "chat-1",
          sender_id: "peer",
          content: "keep this",
          created_at: "2026-07-30T10:00:00Z",
          read_status: false,
        },
      ],
      has_more: false,
      next_cursor: null,
    })

    const { result } = renderHook(() => useMessengerController(), { wrapper })
    await waitFor(() => expect(result.current.messages).toHaveLength(1))

    act(() => result.current.handleEditMessage("missing-message", "before"))
    act(() => result.current.setEditingMessageContent("after"))
    await waitFor(() => expect(result.current.editingMessageContent).toBe("after"))
    act(() => result.current.handleSaveEdit("missing-message"))

    await waitFor(() => expect(mocks.chatApi.editMessage).toHaveBeenCalled())
    expect(result.current.messages[0]?.text).toBe("keep this")
  })

  it("builds an optimistic message safely for a user without name or avatar", async () => {
    const previousName = mocks.testUser.full_name
    const previousAvatar = mocks.testUser.avatar_url
    Object.assign(mocks.testUser, { full_name: undefined, avatar_url: undefined })
    try {
      seedChat()
      mocks.chatApi.getMessages.mockImplementation(() => new Promise(() => {}))
      const { result } = renderHook(() => useMessengerController(), { wrapper })
      await waitFor(() => expect(result.current.selectedChatId).toBe("chat-1"))

      act(() => result.current.handleSendMessage("fallback identity", []))
      await waitFor(() => expect(mocks.chatApi.sendMessage).toHaveBeenCalled())
    } finally {
      Object.assign(mocks.testUser, { full_name: previousName, avatar_url: previousAvatar })
    }
  })
})
