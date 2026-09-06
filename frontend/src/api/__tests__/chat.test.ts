import { describe, expect, it, vi } from "vitest"
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

  it("createGroup posts name + participant_ids", async () => {
    const mockChat = { id: "group1", chat_type: "group", name: "Team" }
    vi.mocked(client.post).mockResolvedValueOnce({ data: mockChat })

    const result = await chatApi.createGroup("Team", ["u1", "u2"])
    expect(client.post).toHaveBeenCalledWith("/chats/groups", {
      name: "Team",
      participant_ids: ["u1", "u2"],
    })
    expect(result).toEqual(mockChat)
  })

  it("addParticipant posts user_id to the participants endpoint", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { status: "ok" } })

    await chatApi.addParticipant("chat1", "u3")
    expect(client.post).toHaveBeenCalledWith("/chats/chat1/participants", {
      user_id: "u3",
    })
  })

  it("removeParticipant deletes the participant path", async () => {
    vi.mocked(client.delete).mockResolvedValueOnce({ data: { status: "ok" } })

    await chatApi.removeParticipant("chat1", "u3")
    expect(client.delete).toHaveBeenCalledWith("/chats/chat1/participants/u3")
  })

  it("renameChat patches the chat with the new name", async () => {
    vi.mocked(client.patch).mockResolvedValueOnce({ data: { status: "ok" } })

    await chatApi.renameChat("chat1", "New Name")
    expect(client.patch).toHaveBeenCalledWith("/chats/chat1", { name: "New Name" })
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
    expect(formData.get("content")).toBe("hello")
    expect(formData.getAll("files")).toHaveLength(1)
    expect(formData.get("reply_to_message_id")).toBeNull()
  })

  it("omits optional file and reply fields when they are not supplied", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { id: "msg-no-options" } })

    await chatApi.sendMessage("chat1", "plain", [], "")

    const formData = vi.mocked(client.post).mock.calls[0]![1] as FormData
    expect(formData.get("content")).toBe("plain")
    expect(formData.getAll("files")).toEqual([])
    expect(formData.get("reply_to_message_id")).toBeNull()
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

  it("getMessages builds the cursor + limit query string", async () => {
    const mockData = { items: [], has_more: false, next_cursor: null }
    vi.mocked(client.get).mockResolvedValueOnce({ data: mockData })
    const result = await chatApi.getMessages("chat1", "cur2", 25)
    expect(client.get).toHaveBeenCalledWith("/chats/chat1/messages?cursor=cur2&limit=25")
    expect(result).toEqual(mockData)
  })

  it("forwards abort signals on cancellable GET requests", async () => {
    const signal = new AbortController().signal
    const chats = { items: [], has_more: false, next_cursor: null }
    const chat = { id: "chat1" }
    const messages = { items: [], has_more: false, next_cursor: null }
    const reactors = [{ user_id: "u1", name: "Alice", avatar_url: null }]
    vi.mocked(client.get)
      .mockResolvedValueOnce({ data: chats })
      .mockResolvedValueOnce({ data: chat })
      .mockResolvedValueOnce({ data: messages })
      .mockResolvedValueOnce({ data: reactors })

    await chatApi.getChats(undefined, 20, signal)
    await chatApi.getChat("chat1", signal)
    await chatApi.getMessages("chat1", undefined, 50, signal)
    await chatApi.getReactors("chat1", "msg1", "👍", signal)

    expect(client.get).toHaveBeenNthCalledWith(1, "/chats?limit=20", { signal })
    expect(client.get).toHaveBeenNthCalledWith(2, "/chats/chat1", { signal })
    expect(client.get).toHaveBeenNthCalledWith(3, "/chats/chat1/messages?limit=50", { signal })
    expect(client.get).toHaveBeenNthCalledWith(
      4,
      `/chats/chat1/messages/msg1/reactions?emoji=${encodeURIComponent("👍")}`,
      { signal }
    )
  })

  it("sendMessage appends reply_to_message_id when replying (W207)", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { id: "m2" } })
    await chatApi.sendMessage("chat1", "re", undefined, "target-msg")
    expect(client.post).toHaveBeenCalledWith("/chats/chat1/messages", expect.any(FormData))
    const formData = vi.mocked(client.post).mock.calls[0]![1] as FormData
    expect(formData.get("reply_to_message_id")).toBe("target-msg")
  })

  it("forwardMessages POSTs source_chat_id + message_ids as JSON (W211)", async () => {
    const forwarded = [{ id: "fwd1", content: "orig", forwarded_from_name: "Alice" }]
    vi.mocked(client.post).mockResolvedValueOnce({ data: forwarded })
    const result = await chatApi.forwardMessages("dest1", "src1", ["m1"])
    expect(client.post).toHaveBeenCalledWith("/chats/dest1/forward", {
      source_chat_id: "src1",
      message_ids: ["m1"],
    })
    expect(result).toEqual(forwarded)
  })

  it("editMessage PATCHes the message with FormData content (W205)", async () => {
    vi.mocked(client.patch).mockResolvedValueOnce({ data: { id: "msg1" } })
    await chatApi.editMessage("chat1", "msg1", "fixed")
    expect(client.patch).toHaveBeenCalledWith("/chats/chat1/messages/msg1", expect.any(FormData))
    const formData = vi.mocked(client.patch).mock.calls[0]![1] as FormData
    expect(formData.get("content")).toBe("fixed")
  })

  it("deleteMessage DELETEs the message (W205)", async () => {
    vi.mocked(client.delete).mockResolvedValueOnce({ data: { ok: true } })
    await chatApi.deleteMessage("chat1", "msg1")
    expect(client.delete).toHaveBeenCalledWith("/chats/chat1/messages/msg1")
  })

  it("addReaction POSTs the emoji as a Form field (W206)", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { ok: true } })
    await chatApi.addReaction("chat1", "msg1", "👍")
    expect(client.post).toHaveBeenCalledWith(
      "/chats/chat1/messages/msg1/reactions",
      expect.any(FormData)
    )
    const formData = vi.mocked(client.post).mock.calls[0]![1] as FormData
    expect(formData.get("emoji")).toBe("👍")
  })

  it("removeReaction DELETEs with the emoji as a percent-encoded query param (W206 SW7)", async () => {
    vi.mocked(client.delete).mockResolvedValueOnce({ data: { ok: true } })
    await chatApi.removeReaction("chat1", "msg1", "👍")
    expect(client.delete).toHaveBeenCalledWith(
      `/chats/chat1/messages/msg1/reactions?emoji=${encodeURIComponent("👍")}`
    )
  })

  it("getReactors GETs the reactor list with the emoji query param (W207)", async () => {
    const reactors = [{ user_id: "u1", name: "Alice", avatar_url: null }]
    vi.mocked(client.get).mockResolvedValueOnce({ data: reactors })
    const result = await chatApi.getReactors("chat1", "msg1", "👍")
    expect(client.get).toHaveBeenCalledWith(
      `/chats/chat1/messages/msg1/reactions?emoji=${encodeURIComponent("👍")}`
    )
    expect(result).toEqual(reactors)
  })

  it("sendTyping POSTs the fire-and-forget typing endpoint (W207)", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: undefined })
    await chatApi.sendTyping("chat1")
    expect(client.post).toHaveBeenCalledWith("/chats/chat1/typing")
  })
})
