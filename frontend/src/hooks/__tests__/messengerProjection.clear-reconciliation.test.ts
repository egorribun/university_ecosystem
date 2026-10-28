import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Chat, ChatsListResponse } from "@/api/chat"
import { beginMessengerOperation, finishMessengerOperation } from "@/hooks/messengerProjection"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"

const generationKey = "ecosystem.session.generation.v1"
const chat: Chat = {
  id: "11111111-1111-4111-8111-111111111111",
  participants: [],
  unread_count: 10,
  created_at: "2026-10-22T12:00:00.000Z",
  updated_at: "2026-10-22T12:00:00.000Z",
}
const accountId = "44444444-4444-4444-8444-444444444444"
let previousGeneration: string | null
let clients: QueryClient[]

function page(unread: number): ChatsListResponse {
  return {
    items: [{ ...chat, unread_count: unread }],
    has_more: false,
    next_cursor: null,
  }
}

function deferredPage() {
  let resolve!: (value: ChatsListResponse) => void
  const promise = new Promise<ChatsListResponse>((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}

async function startQuietClear() {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: Infinity, retry: false } },
  })
  clients.push(client)
  client.setQueryData(["chats"], page(10))
  const requests: ReturnType<typeof deferredPage>[] = []
  const refreshChats = vi.fn(() => {
    const request = deferredPage()
    requests.push(request)
    return request.promise
  })
  const token = beginMessengerOperation(client, accountId, chat.id, {
    kind: "clear",
    refreshChats,
  })
  expect(finishMessengerOperation(client, token, true)).toBe(true)
  const cache = client.getQueryCache()
  const subscribe = cache.subscribe.bind(cache)
  const subscriptions: { releases: number }[] = []
  vi.spyOn(cache, "subscribe").mockImplementation((listener) => {
    const unsubscribe = subscribe(listener)
    const subscription = { releases: 0 }
    subscriptions.push(subscription)
    return () => {
      subscription.releases += 1
      unsubscribe()
    }
  })
  for (let index = 0; index < 3; index += 1) {
    expect(refreshChats).toHaveBeenCalledTimes(index + 1)
    client.setQueryData(["chats"], page(index + 1))
    requests[index]!.resolve(page(0))
    await vi.advanceTimersByTimeAsync(0)
  }
  expect(refreshChats).toHaveBeenCalledTimes(3)
  expect(vi.getTimerCount()).toBe(1)
  expect(subscriptions).toEqual([{ releases: 0 }])
  return { client, requests, refreshChats, subscriptions }
}

beforeEach(() => {
  vi.useFakeTimers()
  clients = []
  previousGeneration = localStorage.getItem(generationKey)
  localStorage.setItem(generationKey, JSON.stringify({ nonce: "quiet-owner", hash: null }))
  acceptBrowserSessionGeneration()
})

afterEach(async () => {
  invalidateSessionEpoch()
  clients.forEach((client) => client.clear())
  await vi.advanceTimersByTimeAsync(0)
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  if (previousGeneration === null) localStorage.removeItem(generationKey)
  else localStorage.setItem(generationKey, previousGeneration)
  acceptBrowserSessionGeneration()
})

describe("clear reconciliation quiet-period ownership", () => {
  it("ignores foreign writes, coalesces owned writes and recovers beyond a fourth collision", async () => {
    const { client, requests, refreshChats, subscriptions } = await startQuietClear()
    await vi.advanceTimersByTimeAsync(50)
    client.setQueryData(["foreign-chat-list"], { revision: 1 })
    await vi.advanceTimersByTimeAsync(49)
    expect(refreshChats).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1)
    expect(refreshChats).toHaveBeenCalledTimes(4)
    expect(subscriptions).toEqual([{ releases: 1 }])

    client.setQueryData(["chats"], page(4))
    requests[3]!.resolve(page(0))
    await vi.advanceTimersByTimeAsync(0)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(60)
    client.setQueryData(["chats"], page(5))
    await vi.advanceTimersByTimeAsync(99)
    expect(refreshChats).toHaveBeenCalledTimes(4)
    await vi.advanceTimersByTimeAsync(1)
    expect(refreshChats).toHaveBeenCalledTimes(5)
    requests[4]!.resolve(page(0))
    await vi.advanceTimersByTimeAsync(0)

    expect(client.getQueryData<ChatsListResponse>(["chats"])?.items[0]?.unread_count).toBe(0)
    expect(subscriptions).toEqual([{ releases: 1 }, { releases: 1 }])
    expect(vi.getTimerCount()).toBe(0)
    client.setQueryData(["chats"], page(9))
    const recovered = client.getQueryData(["chats"])
    await vi.advanceTimersByTimeAsync(1000)
    expect(refreshChats).toHaveBeenCalledTimes(5)
    expect(client.getQueryData(["chats"])).toBe(recovered)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    "query removal",
    "query replacement",
    "session epoch",
    "observed generation round trip",
  ] as const)("retires the quiet wait after %s", async (retirement) => {
    const { client, refreshChats, subscriptions } = await startQuietClear()
    if (retirement === "query removal" || retirement === "query replacement") {
      client.removeQueries({ queryKey: ["chats"], exact: true })
      if (retirement === "query replacement") client.setQueryData(["chats"], page(77))
    } else if (retirement === "session epoch") {
      invalidateSessionEpoch()
    } else {
      localStorage.setItem(generationKey, JSON.stringify({ nonce: "foreign-owner", hash: null }))
      // A real cache notification observes the foreign binding before it returns.
      client.setQueryData(["foreign-chat-list"], { revision: 1 })
      localStorage.setItem(generationKey, JSON.stringify({ nonce: "quiet-owner", hash: null }))
    }
    const retained = client.getQueryData(["chats"])
    await vi.advanceTimersByTimeAsync(1000)
    expect(refreshChats).toHaveBeenCalledTimes(3)
    expect(client.getQueryData(["chats"])).toBe(retained)
    expect(subscriptions).toEqual([{ releases: 1 }])
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(["query replacement", "session epoch"] as const)(
    "ignores a quiet refresh response after %s retires its owner",
    async (retirement) => {
      const { client, requests, refreshChats, subscriptions } = await startQuietClear()
      await vi.advanceTimersByTimeAsync(100)
      expect(refreshChats).toHaveBeenCalledTimes(4)
      expect(subscriptions).toEqual([{ releases: 1 }])
      if (retirement === "query replacement") {
        client.removeQueries({ queryKey: ["chats"], exact: true })
        client.setQueryData(["chats"], page(77))
      } else {
        invalidateSessionEpoch()
      }
      const retained = client.getQueryData(["chats"])
      requests[3]!.resolve(page(99))
      await vi.advanceTimersByTimeAsync(1000)
      expect(refreshChats).toHaveBeenCalledTimes(4)
      expect(client.getQueryData(["chats"])).toBe(retained)
      expect(vi.getTimerCount()).toBe(0)
    }
  )
})
