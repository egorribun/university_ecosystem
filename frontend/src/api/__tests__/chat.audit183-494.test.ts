import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { chatApi } from "@/api/chat"
import client from "@/api/client"

vi.mock("@/api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe("chat API path identifiers and send idempotency", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    vi.resetAllMocks()
  })

  it("encodes every identifier inserted into a request path", async () => {
    const chatId = "chat/segment?filter=1#fragment"
    const messageId = "message/segment?filter=2#fragment"
    const userId = "user/segment?filter=3#fragment"
    const chatSegment = encodeURIComponent(chatId)
    const messageSegment = encodeURIComponent(messageId)
    const userSegment = encodeURIComponent(userId)

    vi.mocked(client.get).mockResolvedValue({ data: {} } as never)
    vi.mocked(client.post).mockResolvedValue({ data: {} } as never)
    vi.mocked(client.patch).mockResolvedValue({ data: {} } as never)
    vi.mocked(client.delete).mockResolvedValue({ data: {} } as never)

    await chatApi.getChat(chatId)
    await chatApi.addParticipant(chatId, userId)
    await chatApi.removeParticipant(chatId, userId)
    await chatApi.renameChat(chatId, "Renamed")
    await chatApi.getMessages(chatId)
    await chatApi.forwardMessages(chatId, "source-chat", [messageId])
    await chatApi.markRead(chatId)
    await chatApi.sendTyping(chatId)
    await chatApi.editMessage(chatId, messageId, "edited")
    await chatApi.deleteMessage(chatId, messageId)
    await chatApi.addReaction(chatId, messageId, "👍")
    await chatApi.removeReaction(chatId, messageId, "👍")
    await chatApi.getReactors(chatId, messageId, "👍")
    await chatApi.clearChat(chatId)
    await chatApi.deleteChat(chatId)

    expect(vi.mocked(client.get).mock.calls.map(([url]) => url)).toEqual([
      `/chats/${chatSegment}`,
      `/chats/${chatSegment}/messages?limit=50`,
      `/chats/${chatSegment}/messages/${messageSegment}/reactions?emoji=${encodeURIComponent("👍")}`,
    ])
    expect(vi.mocked(client.post).mock.calls.map(([url]) => url)).toEqual([
      `/chats/${chatSegment}/participants`,
      `/chats/${chatSegment}/forward`,
      `/chats/${chatSegment}/read`,
      `/chats/${chatSegment}/typing`,
      `/chats/${chatSegment}/messages/${messageSegment}/reactions`,
      `/chats/${chatSegment}/clear`,
    ])
    expect(vi.mocked(client.delete).mock.calls.map(([url]) => url)).toEqual([
      `/chats/${chatSegment}/participants/${userSegment}`,
      `/chats/${chatSegment}/messages/${messageSegment}`,
      `/chats/${chatSegment}/messages/${messageSegment}/reactions?emoji=${encodeURIComponent("👍")}`,
      `/chats/${chatSegment}`,
    ])
    expect(vi.mocked(client.patch).mock.calls.map(([url]) => url)).toEqual([
      `/chats/${chatSegment}`,
      `/chats/${chatSegment}/messages/${messageSegment}`,
    ])
  })

  it("always sends an idempotency key and preserves a caller's retry key", async () => {
    const generatedKey = "00000000-0000-4000-8000-000000000001"
    const randomUuid = vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(generatedKey)
    vi.mocked(client.post).mockResolvedValue({
      data: { id: "message-1" },
    } as never)

    await chatApi.sendMessage("chat/room", "hello")
    await chatApi.sendMessage("chat/room", "retry", undefined, undefined, "stable-retry-key")
    await chatApi.sendMessage("chat/room", "retry", undefined, undefined, "stable-retry-key")

    const encodedChatId = encodeURIComponent("chat/room")
    expect(randomUuid).toHaveBeenCalledOnce()
    expect(client.post).toHaveBeenNthCalledWith(
      1,
      `/chats/${encodedChatId}/messages`,
      expect.any(FormData),
      { headers: { "Idempotency-Key": generatedKey } }
    )
    expect(client.post).toHaveBeenNthCalledWith(
      2,
      `/chats/${encodedChatId}/messages`,
      expect.any(FormData),
      { headers: { "Idempotency-Key": "stable-retry-key" } }
    )
    expect(client.post).toHaveBeenNthCalledWith(
      3,
      `/chats/${encodedChatId}/messages`,
      expect.any(FormData),
      { headers: { "Idempotency-Key": "stable-retry-key" } }
    )
  })
})
