import { afterEach, describe, expect, it } from "vitest"
import { AxiosHeaders } from "axios"
import client from "@/api/client"
import { chatApi } from "@/api/chat"

const originalAdapter = client.defaults.adapter
const originalBaseURL = client.defaults.baseURL

const parseRequestUrl = (url: string): URL => new URL(url, window.location.origin)

describe("chat API path identifiers through Axios", () => {
  afterEach(() => {
    client.defaults.adapter = originalAdapter
    client.defaults.baseURL = originalBaseURL
  })

  it("keeps path identifiers in one encoded segment on actual Axios requests", async () => {
    const requestUrls: URL[] = []
    client.defaults.baseURL = "/api/v1"
    client.defaults.adapter = async (config) => {
      requestUrls.push(parseRequestUrl(client.getUri(config)))
      return {
        config,
        data: {},
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    const chatId = "chat/room with space?view=all#fragment"
    const messageId = "message/part one?filter=unread#fragment"
    const userId = "user/part one?scope=group#fragment"
    const uuid = "550e8400-e29b-41d4-a716-446655440000"
    const chatSegment = encodeURIComponent(chatId)
    const messageSegment = encodeURIComponent(messageId)
    const userSegment = encodeURIComponent(userId)

    await chatApi.getChat(chatId)
    await chatApi.getChat(uuid)
    await chatApi.addParticipant(chatId, userId)
    await chatApi.removeParticipant(chatId, userId)
    await chatApi.renameChat(chatId, "Renamed")
    await chatApi.getMessages(chatId)
    await chatApi.sendMessage(chatId, "hello", undefined, undefined, "fixed-test-key")
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

    expect(requestUrls.map(({ pathname }) => pathname)).toEqual([
      `/api/v1/chats/${chatSegment}`,
      `/api/v1/chats/${uuid}`,
      `/api/v1/chats/${chatSegment}/participants`,
      `/api/v1/chats/${chatSegment}/participants/${userSegment}`,
      `/api/v1/chats/${chatSegment}`,
      `/api/v1/chats/${chatSegment}/messages`,
      `/api/v1/chats/${chatSegment}/messages`,
      `/api/v1/chats/${chatSegment}/forward`,
      `/api/v1/chats/${chatSegment}/read`,
      `/api/v1/chats/${chatSegment}/typing`,
      `/api/v1/chats/${chatSegment}/messages/${messageSegment}`,
      `/api/v1/chats/${chatSegment}/messages/${messageSegment}`,
      `/api/v1/chats/${chatSegment}/messages/${messageSegment}/reactions`,
      `/api/v1/chats/${chatSegment}/messages/${messageSegment}/reactions`,
      `/api/v1/chats/${chatSegment}/messages/${messageSegment}/reactions`,
      `/api/v1/chats/${chatSegment}/clear`,
      `/api/v1/chats/${chatSegment}`,
    ])
    expect(requestUrls[0]?.search).toBe("")
    expect(requestUrls[0]?.hash).toBe("")
    expect(requestUrls[5]?.searchParams.get("limit")).toBe("50")
    expect(requestUrls[13]?.searchParams.get("emoji")).toBe("👍")
    expect(requestUrls[14]?.searchParams.get("emoji")).toBe("👍")
    expect(requestUrls[0]?.pathname).not.toContain("%252F")
  })
})
