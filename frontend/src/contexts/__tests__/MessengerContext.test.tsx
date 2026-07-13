/* eslint-disable @typescript-eslint/no-explicit-any */
import { renderHook, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

/**
 * Wave 183 SW13 — MessengerContext unit tests.
 *
 * Covers MessengerProvider behaviour + useMessenger hook contract.
 *
 * In-scope:
 *  - Throws helpful error when useMessenger used outside MessengerProvider.
 *  - unreadCount aggregates unread_count from all chats.
 *  - unreadCount falls back to 0 when no chats data.
 *  - presenceMap starts empty.
 *  - isConnected reflects WS connection state from useChatWebSocket.
 *  - getTypingUsersForChat / sendTyping / sendRead delegate to
 *    useChatWebSocket and return their values.
 *
 * Mocking strategy:
 *  - useChatWebSocket mocked with predictable returns (no actual WS).
 *  - useAuth mocked with isAuth=true so chat query fires.
 *  - chatApi.getChats mocked with sample data.
 */

const mocks = vi.hoisted(() => ({
  useChatWebSocket: vi.fn(),
  useAuth: vi.fn(),
  chatApi: {
    getChats: vi.fn(),
  },
}))

vi.mock("@/hooks/useChatWebSocket", () => ({
  useChatWebSocket: mocks.useChatWebSocket,
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: mocks.useAuth,
}))

vi.mock("@/api/chat", () => ({
  chatApi: mocks.chatApi,
}))

import { MessengerProvider, useMessenger } from "@/contexts/MessengerContext"

let currentQueryClient: QueryClient | null = null

const wrapper = ({ children }: { children: ReactNode }) => {
  currentQueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={currentQueryClient}>
      <MessengerProvider>{children}</MessengerProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.useAuth.mockReturnValue({ isAuth: true })
  mocks.useChatWebSocket.mockReturnValue({
    isConnected: true,
    sendTyping: vi.fn(),
    sendRead: vi.fn(),
    getTypingUsersForChat: vi.fn().mockReturnValue([]),
  })
  mocks.chatApi.getChats.mockResolvedValue({
    items: [],
    has_more: false,
    next_cursor: null,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("MessengerContext", () => {
  describe("useMessenger hook", () => {
    it("throws when used outside MessengerProvider", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      expect(() => {
        renderHook(() => useMessenger(), {
          wrapper: ({ children }) => {
            const queryClient = new QueryClient()
            return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
          },
        })
      }).toThrow(/useMessenger must be used within MessengerProvider/)

      errorSpy.mockRestore()
    })

    it("returns expected shape inside MessengerProvider", () => {
      const { result } = renderHook(() => useMessenger(), { wrapper })

      expect(result.current).toMatchObject({
        unreadCount: expect.any(Number),
        presenceMap: expect.any(Object),
        isConnected: expect.any(Boolean),
        sendTyping: expect.any(Function),
        sendRead: expect.any(Function),
        getTypingUsersForChat: expect.any(Function),
      })
    })
  })

  describe("unreadCount aggregation", () => {
    it("defaults to 0 when chats data is empty", async () => {
      const { result } = renderHook(() => useMessenger(), { wrapper })

      await waitFor(() => {
        expect(result.current.unreadCount).toBe(0)
      })
    })

    it("sums unread_count across all chats", async () => {
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          { id: "1", participants: [], unread_count: 3, presence: {} },
          { id: "2", participants: [], unread_count: 7, presence: {} },
          { id: "3", participants: [], unread_count: 0, presence: {} },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessenger(), { wrapper })

      await waitFor(() => {
        expect(result.current.unreadCount).toBe(10)
      })
    })

    it("handles missing unread_count gracefully", async () => {
      mocks.chatApi.getChats.mockResolvedValue({
        items: [
          { id: "1", participants: [], unread_count: 5, presence: {} },
          { id: "2", participants: [], presence: {} },
        ],
        has_more: false,
        next_cursor: null,
      })

      const { result } = renderHook(() => useMessenger(), { wrapper })

      await waitFor(() => {
        expect(result.current.unreadCount).toBe(5)
      })
    })
  })

  describe("isAuth gating", () => {
    it("does NOT fire useChatWebSocket connect when isAuth=false", () => {
      mocks.useAuth.mockReturnValue({ isAuth: false })

      renderHook(() => useMessenger(), { wrapper })

      // useChatWebSocket should be called with enabled: false
      expect(mocks.useChatWebSocket).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: false })
      )
    })

    it("fires useChatWebSocket connect when isAuth=true", () => {
      mocks.useAuth.mockReturnValue({ isAuth: true })

      renderHook(() => useMessenger(), { wrapper })

      expect(mocks.useChatWebSocket).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: true })
      )
    })
  })

  describe("delegation to useChatWebSocket", () => {
    it("isConnected reflects useChatWebSocket return value", () => {
      mocks.useChatWebSocket.mockReturnValue({
        isConnected: false,
        sendTyping: vi.fn(),
        sendRead: vi.fn(),
        getTypingUsersForChat: vi.fn(() => []),
      })

      const { result } = renderHook(() => useMessenger(), { wrapper })
      expect(result.current.isConnected).toBe(false)
    })

    it("sendTyping passes through to useChatWebSocket's sendTyping", () => {
      const sendTypingSpy = vi.fn()
      mocks.useChatWebSocket.mockReturnValue({
        isConnected: true,
        sendTyping: sendTypingSpy,
        sendRead: vi.fn(),
        getTypingUsersForChat: vi.fn(() => []),
      })

      const { result } = renderHook(() => useMessenger(), { wrapper })
      result.current.sendTyping("chat-1")
      expect(sendTypingSpy).toHaveBeenCalledWith("chat-1")
    })

    it("getTypingUsersForChat returns useChatWebSocket result", () => {
      const typing = [{ userId: "u1", userName: "Alice" }]
      mocks.useChatWebSocket.mockReturnValue({
        isConnected: true,
        sendTyping: vi.fn(),
        sendRead: vi.fn(),
        getTypingUsersForChat: vi.fn(() => typing),
      })

      const { result } = renderHook(() => useMessenger(), { wrapper })
      expect(result.current.getTypingUsersForChat("chat-1")).toEqual(typing)
    })
  })

  describe("onPresenceUpdate validation (MessengerContext.tsx:33-47)", () => {
    it("calls useChatWebSocket with an onPresenceUpdate validator callback", () => {
      renderHook(() => useMessenger(), { wrapper })

      const callArgs = mocks.useChatWebSocket.mock.calls[0]![0]
      expect(callArgs.onPresenceUpdate).toBeInstanceOf(Function)
    })
  })

  describe("onRead cache updates", () => {
    it("correctly updates read_receipts in both single chat and chats list caches", async () => {
      renderHook(() => useMessenger(), { wrapper })
      const queryClient = currentQueryClient!

      const chatId = "chat-1"
      const userId = "user-2"
      const readAt = "2026-07-13T19:57:00Z"

      // Initialize caches
      const initialChat = {
        id: chatId,
        participants: [],
        unread_count: 0,
        created_at: "",
        updated_at: "",
        read_receipts: [{ user_id: "user-3", last_read_at: "2026-07-13T19:00:00Z" }],
      }
      queryClient.setQueryData(["chats", chatId], initialChat)

      const initialChatsList = {
        items: [initialChat],
        has_more: false,
        next_cursor: null,
      }
      queryClient.setQueryData(["chats"], initialChatsList)

      const callArgs = mocks.useChatWebSocket.mock.calls[0]![0]
      expect(callArgs.onRead).toBeInstanceOf(Function)

      // Trigger read receipt update
      act(() => {
        callArgs.onRead(chatId, userId, readAt)
      })

      // Verify single chat cache update
      const updatedChat = queryClient.getQueryData<any>(["chats", chatId])
      expect(updatedChat).toBeDefined()
      expect(updatedChat.read_receipts).toContainEqual({ user_id: userId, last_read_at: readAt })
      expect(updatedChat.read_receipts).toContainEqual({
        user_id: "user-3",
        last_read_at: "2026-07-13T19:00:00Z",
      })

      // Verify chats list cache update
      const updatedList = queryClient.getQueryData<any>(["chats"])
      expect(updatedList).toBeDefined()
      expect(updatedList.items[0].read_receipts).toContainEqual({
        user_id: userId,
        last_read_at: readAt,
      })
    })
  })
})
