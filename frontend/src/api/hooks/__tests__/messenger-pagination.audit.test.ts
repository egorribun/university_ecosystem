import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { chatApi, type Chat, type ChatsListResponse } from "@/api/chat"
import { fetchLoadedChats } from "@/api/hooks/messenger"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

const clients: QueryClient[] = []
const chat = (id: string): Chat => ({
  id,
  participants: [],
  unread_count: 0,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
})
const page = (
  items: Chat[],
  has_more = false,
  next_cursor: string | null = null
): ChatsListResponse => ({ items, has_more, next_cursor })

function loadedClient(count = 21) {
  const client = new QueryClient()
  clients.push(client)
  client.setQueryData(
    ["chats"],
    page(Array.from({ length: count }, (_, index) => chat("old-" + String(index + 1))))
  )
  return client
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear())
  vi.restoreAllMocks()
})

describe("AUD030 authoritative loaded chat extent", () => {
  it("rebuilds only the loaded extent and never retains an old deleted tail", async () => {
    const client = loadedClient()
    const before = client.getQueryData(["chats"])
    const fresh = Array.from({ length: 20 }, (_, index) => chat("fresh-" + String(index)))
    const replacement = chat("replacement-tail")
    const requests = vi
      .spyOn(chatApi, "getChats")
      .mockResolvedValueOnce(page(fresh, true, "second"))
      .mockResolvedValueOnce(page([fresh[0]!, replacement], true, "third"))
    const signal = new AbortController().signal

    const result = await fetchLoadedChats(client, signal)

    expect(requests).toHaveBeenCalledTimes(2)
    expect(requests).toHaveBeenNthCalledWith(1, undefined, 20, signal)
    expect(requests).toHaveBeenNthCalledWith(2, "second", 20, signal)
    expect(result).toEqual(page([...fresh, replacement], true, "third"))
    expect(result.items.some(({ id }) => id.startsWith("old-"))).toBe(false)
    expect(client.getQueryData(["chats"])).toBe(before)
  })

  it("stops at fresh exhaustion even when the old cache contained more pages", async () => {
    const client = loadedClient(41)
    const requests = vi.spyOn(chatApi, "getChats").mockResolvedValue(page([]))

    expect(await fetchLoadedChats(client)).toEqual(page([]))
    expect(requests).toHaveBeenCalledTimes(1)
  })

  it.each(["missing", "repeated", "malformed"] as const)(
    "rejects a %s continuation instead of manufacturing a complete aggregate",
    async (failure) => {
      const client = loadedClient(41)
      const requests = vi.spyOn(chatApi, "getChats")
      if (failure === "malformed") {
        requests.mockResolvedValue({ items: {} } as unknown as ChatsListResponse)
      } else if (failure === "missing") {
        requests.mockResolvedValue(page([chat("fresh")], true, null))
      } else {
        requests.mockResolvedValue(page([chat("fresh")], true, "same-cursor"))
      }

      await expect(fetchLoadedChats(client)).rejects.toThrow(
        /Chat list (?:page is invalid|cursor did not advance)/
      )
      expect(requests).toHaveBeenCalledTimes(failure === "repeated" ? 2 : 1)
    }
  )

  it("does not start an already cancelled multi-page refresh", async () => {
    const client = loadedClient()
    const controller = new AbortController()
    controller.abort()
    const requests = vi.spyOn(chatApi, "getChats")

    await expect(fetchLoadedChats(client, controller.signal)).rejects.toThrow(
      "Chat list request was cancelled"
    )
    expect(requests).not.toHaveBeenCalled()
  })

  it("does not follow a cursor after an ignored transport cancellation", async () => {
    const client = loadedClient()
    const controller = new AbortController()
    let resolve!: (value: ChatsListResponse) => void
    const response = new Promise<ChatsListResponse>((done) => {
      resolve = done
    })
    const requests = vi.spyOn(chatApi, "getChats").mockReturnValue(response)
    const attempt = fetchLoadedChats(client, controller.signal)
    try {
      expect(requests).toHaveBeenCalledTimes(1)
      controller.abort()
      resolve(page([chat("fresh")], true, "second"))
      await expect(attempt).rejects.toThrow("Chat list request was cancelled")
      expect(requests).toHaveBeenCalledTimes(1)
    } finally {
      controller.abort()
      resolve(page([]))
      await attempt.catch(() => undefined)
    }
  })

  it.each(["query replacement", "session rotation"] as const)(
    "stops a signal-less refresh after %s without dispatching another cursor",
    async (transition) => {
      const client = loadedClient()
      let resolve!: (value: ChatsListResponse) => void
      const response = new Promise<ChatsListResponse>((done) => {
        resolve = done
      })
      const requests = vi.spyOn(chatApi, "getChats").mockReturnValue(response)
      const attempt = fetchLoadedChats(client)
      try {
        expect(requests).toHaveBeenCalledWith(undefined, 20, undefined)
        if (transition === "query replacement") {
          client.removeQueries({ queryKey: ["chats"], exact: true })
          client.setQueryData(["chats"], page([chat("new-owner")]))
        } else {
          invalidateSessionEpoch()
        }
        resolve(page([chat("old-owner")], true, "old-owner-cursor"))
        await expect(attempt).rejects.toThrow("Chat list request was cancelled")
        expect(requests).toHaveBeenCalledTimes(1)
      } finally {
        resolve(page([]))
        await attempt.catch(() => undefined)
      }
    }
  )
})
