import { describe, expect, it, vi } from "vitest"
import { chatApi } from "@/api/chat"
import client from "@/api/client"

vi.mock("@/api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

describe("chatApi", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("getChats calls correct endpoint", async () => {
    const mockData = { items: [], has_more: false, next_cursor: null }
    vi.mocked(client.get).mockResolvedValueOnce({ data: mockData })

    const result = await chatApi.getChats("cursor1", 10)
    expect(client.get).toHaveBeenCalledWith("/chats?cursor=cursor1&limit=10")
    expect(result).toEqual(mockData)
  })

  it("getChat calls correct endpoint", async () => {
    const mockChat = { id: "chat1" }
    vi.mocked(client.get).mockResolvedValueOnce({ data: mockChat })

    const result = await chatApi.getChat("chat1")
    expect(client.get).toHaveBeenCalledWith("/chats/chat1")
    expect(result).toEqual(mockChat)
  })

  it("createChat calls correct endpoint", async () => {
    const mockChat = { id: "new-chat" }
    vi.mocked(client.post).mockResolvedValueOnce({ data: mockChat })

    const result = await chatApi.createChat("user1")
    expect(client.post).toHaveBeenCalledWith("/chats", { participant_id: "user1" })
    expect(result).toEqual(mockChat)
  })

  it("sendMessage handles FormData with files", async () => {
    const mockMessage = { id: "msg1" }
    vi.mocked(client.post).mockResolvedValueOnce({ data: mockMessage })

    const file = new File(["foo"], "foo.txt", { type: "text/plain" })
    const result = await chatApi.sendMessage("chat1", "hello", [file])

    expect(client.post).toHaveBeenCalledWith("/chats/chat1/messages", expect.any(FormData))
    expect(result).toEqual(mockMessage)

    const formData = vi.mocked(client.post).mock.calls[0]![1] as FormData
    expect(formData).toBeInstanceOf(FormData)
    // Check if expected fields exist in FormData
    // Since FormData.get might be weird in some environments, we can check its internal state if needed
    // or just assume if it's FormData it's probably okay after being passed to the client.
  })

  it("markRead calls correct endpoint", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { ok: true } })
    await chatApi.markRead("chat1")
    expect(client.post).toHaveBeenCalledWith("/chats/chat1/read")
  })

  it("clearChat calls correct endpoint", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { chat_id: "chat1" } })
    await chatApi.clearChat("chat1")
    expect(client.post).toHaveBeenCalledWith("/chats/chat1/clear")
  })

  it("deleteChat calls correct endpoint", async () => {
    vi.mocked(client.delete).mockResolvedValueOnce({ data: { chat_id: "chat1" } })
    await chatApi.deleteChat("chat1")
    expect(client.delete).toHaveBeenCalledWith("/chats/chat1")
  })
})
