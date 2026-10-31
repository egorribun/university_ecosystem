import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createElement, type ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import type { Chat, ChatsListResponse } from "@/api/chat"
import {
  beginMessengerOperation,
  finishMessengerOperation,
  useProjectedMessengerChats,
} from "@/hooks/messengerProjection"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

const chatId = "chat-1"
const accountId = "me"
const chat: Chat = {
  id: chatId,
  participants: [],
  unread_count: 2,
  created_at: "2026-10-22T12:00:00Z",
  updated_at: "2026-10-22T12:00:00Z",
}
const page = (unread: number): ChatsListResponse => ({
  items: [{ ...chat, unread_count: unread }],
  has_more: false,
  next_cursor: null,
})
const clients: QueryClient[] = []

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  clients.push(client)
  client.setQueryData(["chats"], page(2))
  return client
}

function commitClear(client: QueryClient, refreshChats: () => Promise<ChatsListResponse>) {
  const token = beginMessengerOperation(client, accountId, chatId, { kind: "clear", refreshChats })
  expect(finishMessengerOperation(client, token, true)).toBe(true)
}

async function rejectRefresh(refresh: ReturnType<typeof deferred<ChatsListResponse>>) {
  refresh.reject(new Error("temporary failure"))
  await refresh.promise.catch(() => {})
  await Promise.resolve()
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear())
})

it("keeps a failed clear refresh stale through live writes until a later fetch succeeds", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  const refreshChats = vi.fn(() => refresh.promise)
  commitClear(client, refreshChats)
  await rejectRefresh(refresh)
  client.setQueryData(["other-chats"], page(7))
  client.setQueryData(["chats"], page(1))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)
  expect(client.getQueryState(["other-chats"])?.isInvalidated).toBe(false)
  expect(refreshChats).toHaveBeenCalledOnce()

  await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
  expect(client.getQueryData(["chats"])).toEqual(page(0))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  client.setQueryData(["chats"], page(3))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  expect(refreshChats).toHaveBeenCalledOnce()
})

it("does not retire recovery for a query fetch that began before the failed refresh", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  const earlierFetch = deferred<ChatsListResponse>()
  commitClear(client, () => refresh.promise)
  const fetch = client.fetchQuery({ queryKey: ["chats"], queryFn: () => earlierFetch.promise })
  await rejectRefresh(refresh)
  earlierFetch.resolve(page(2))
  await fetch
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

  await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  expect(client.getQueryData(["chats"])).toEqual(page(0))
})

it("keeps recovery pending if a live write arrives during a later query fetch", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  const fetchResponse = deferred<ChatsListResponse>()
  commitClear(client, () => refresh.promise)
  await rejectRefresh(refresh)
  const fetch = client.fetchQuery({ queryKey: ["chats"], queryFn: () => fetchResponse.promise })
  client.setQueryData(["chats"], page(1))
  fetchResponse.resolve(page(0))
  await fetch
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

  await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
})

it("keeps recovery available after the next query fetch also fails", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  commitClear(client, () => refresh.promise)
  await rejectRefresh(refresh)
  await expect(
    client.fetchQuery({
      queryKey: ["chats"],
      queryFn: async () => {
        throw new Error("retry failed")
      },
    })
  ).rejects.toThrow("retry failed")
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

  await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
  client.setQueryData(["chats"], page(3))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
})

it("keeps recovery pending when a guarded direct refresh overlaps a query fetch", async () => {
  const client = setup()
  const failed = deferred<ChatsListResponse>()
  const direct = deferred<ChatsListResponse>()
  const response = deferred<ChatsListResponse>()
  commitClear(client, () => failed.promise)
  await rejectRefresh(failed)
  commitClear(client, () => direct.promise)
  const fetch = client
    .fetchQuery({ queryKey: ["chats"], queryFn: () => response.promise })
    .catch(() => undefined)
  try {
    direct.resolve(page(1))
    await direct.promise
    await waitFor(() => expect(client.getQueryData(["chats"])).toEqual(page(1)), { timeout: 1500 })
    expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)
    response.resolve(page(0))
    await fetch
    expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

    await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
    expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  } finally {
    direct.resolve(page(1))
    response.resolve(page(0))
    await fetch
  }
})

it.each(["query replacement", "session retirement"] as const)(
  "does not keep the failed refresh marker after %s",
  async (retirement) => {
    const client = setup()
    const refresh = deferred<ChatsListResponse>()
    commitClear(client, () => refresh.promise)
    await rejectRefresh(refresh)
    if (retirement === "query replacement") {
      client.removeQueries({ queryKey: ["chats"], exact: true })
      client.setQueryData(["chats"], page(7))
    } else {
      invalidateSessionEpoch()
      client.setQueryData(["chats"], page(7))
    }
    expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
    expect(client.getQueryData(["chats"])).toEqual(page(7))
  }
)

it("does not revive failed recovery after an observed cross-tab session round trip", async () => {
  const client = setup()
  const Wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  const { unmount } = renderHook(() => useProjectedMessengerChats(undefined, accountId), {
    wrapper: Wrapper,
  })
  const key = "ecosystem.session.generation.v1"
  const previous = localStorage.getItem(key)
  const replacement = JSON.stringify({ nonce: crypto.randomUUID(), hash: null })
  try {
    const refresh = deferred<ChatsListResponse>()
    act(() => commitClear(client, () => refresh.promise))
    await act(async () => rejectRefresh(refresh))
    act(() => {
      localStorage.setItem(key, replacement)
      window.dispatchEvent(
        new StorageEvent("storage", { key, oldValue: previous, newValue: replacement })
      )
      if (previous === null) localStorage.removeItem(key)
      else localStorage.setItem(key, previous)
      window.dispatchEvent(
        new StorageEvent("storage", { key, oldValue: replacement, newValue: previous })
      )
      client.setQueryData(["chats"], page(7))
    })
    expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  } finally {
    unmount()
    if (previous === null) localStorage.removeItem(key)
    else localStorage.setItem(key, previous)
  }
})

it("does not carry recovery to a replacement query when its old fetch is cancelled", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  const response = deferred<ChatsListResponse>()
  commitClear(client, () => refresh.promise)
  await rejectRefresh(refresh)
  const fetch = client
    .fetchQuery({ queryKey: ["chats"], queryFn: () => response.promise })
    .catch(() => undefined)
  client.removeQueries({ queryKey: ["chats"], exact: true })
  client.setQueryData(["chats"], page(7))
  response.resolve(page(0))
  await fetch
  expect(client.getQueryData(["chats"])).toEqual(page(7))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
})

it("keeps recovery stale when a fetch cancellation reverts a live cache write", async () => {
  const client = setup()
  const refresh = deferred<ChatsListResponse>()
  const response = deferred<ChatsListResponse>()
  commitClear(client, () => refresh.promise)
  await rejectRefresh(refresh)
  const fetch = client
    .fetchQuery({ queryKey: ["chats"], queryFn: () => response.promise })
    .catch(() => undefined)
  client.setQueryData(["chats"], page(1))
  await client.cancelQueries({ queryKey: ["chats"], exact: true })
  response.resolve(page(0))
  await fetch
  expect(client.getQueryData(["chats"])).toEqual(page(1))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

  await client.fetchQuery({ queryKey: ["chats"], queryFn: async () => page(0) })
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
})

it("does not let an older direct refresh retire a newer failed clear", async () => {
  const client = setup()
  const earlier = deferred<ChatsListResponse>()
  const later = deferred<ChatsListResponse>()
  commitClear(client, () => earlier.promise)
  commitClear(client, () => later.promise)
  await rejectRefresh(later)
  earlier.resolve(page(1))
  await earlier.promise
  await waitFor(() => expect(client.getQueryData(["chats"])).toEqual(page(1)), { timeout: 1500 })
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(true)

  const newer = deferred<ChatsListResponse>()
  commitClear(client, () => newer.promise)
  newer.resolve(page(0))
  await newer.promise
  await waitFor(() => expect(client.getQueryData(["chats"])).toEqual(page(0)), { timeout: 1500 })
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
  client.setQueryData(["chats"], page(3))
  expect(client.getQueryState(["chats"])?.isInvalidated).toBe(false)
})
