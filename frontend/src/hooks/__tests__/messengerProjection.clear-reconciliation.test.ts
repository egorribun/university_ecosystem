import { CancelledError, QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Chat, ChatsListResponse, Message, MessagesListResponse } from "@/api/chat"
import {
  beginMessengerEditRefresh,
  beginMessengerOperation,
  classifyMessengerServerEdit,
  confirmMessengerServerEdit,
  finishClearRefresh,
  finishMessengerEditRefresh,
  finishMessengerOperation,
  getClearRefresh,
  projectMessengerMessages,
  runMessengerOperation,
} from "@/hooks/messengerProjection"
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

function projectionMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    chat_id: chat.id,
    sender_id: accountId,
    content: "canonical",
    created_at: "2026-10-22T12:00:00.000Z",
    edited_at: "2026-10-22T12:00:01.000Z",
    read_status: false,
    attachments: [],
    reactions: [],
    ...overrides,
  }
}

function messagesPage(items: Message[]): MessagesListResponse {
  return { items, has_more: false, next_cursor: null }
}

function projectionClient(items: Message[] = [projectionMessage()]) {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: Infinity, retry: false } },
  })
  clients.push(client)
  client.setQueryData(["messages", chat.id], messagesPage(items))
  return client
}

function canonicalMessages(client: QueryClient, chatId = chat.id) {
  return client.getQueryData<MessagesListResponse>(["messages", chatId])!
}

async function acceptEdit(
  client: QueryClient,
  messageId: string,
  content: string,
  chatId = chat.id
) {
  const token = beginMessengerOperation(client, accountId, chatId, {
    kind: "edit",
    messageId,
    content,
  })
  expect(token).toBeDefined()
  await runMessengerOperation(client, token, async () => undefined)
  expect(finishMessengerOperation(client, token, true)).toBe(true)
}

function acceptClear(client: QueryClient) {
  const token = beginMessengerOperation(client, accountId, chat.id, {
    kind: "clear",
    refreshChats: async () => page(0),
  })
  expect(finishMessengerOperation(client, token, true)).toBe(true)
  return getClearRefresh(client, chat.id)
}

function actionGate() {
  let resolve!: () => void
  const promise = new Promise<void>((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}

describe("confirmed edit receipts and authoritative refreshes", () => {
  it.each(["content", "timestamp", "deleted", "missing"] as const)(
    "retires a receipt after the canonical target changes in %s",
    async (change) => {
      const target = projectionMessage()
      const client = projectionClient([target])
      await acceptEdit(client, target.id, "accepted")
      const confirmed = canonicalMessages(client)
      const changed = { ...confirmed.items[0]! }
      if (change === "content") changed.content = "peer version"
      if (change === "timestamp") changed.edited_at = "2026-10-22T12:01:00.000Z"
      if (change === "deleted") changed.deleted_at = "2026-10-22T12:01:00.000Z"
      client.setQueryData(
        ["messages", chat.id],
        messagesPage(change === "missing" ? [] : [changed])
      )

      expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toEqual({
        kind: "normal",
      })
      client.setQueryData(["messages", chat.id], confirmed)
      expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toEqual({
        kind: "normal",
      })
      expect(
        projectMessengerMessages(client, accountId, chat.id, confirmed)?.items[0]?.edited_at
      ).toBe(target.edited_at)
    }
  )

  it("confirms only the named message and permits repeated confirmation", async () => {
    const first = projectionMessage()
    const second = projectionMessage({ id: "second", content: "second canonical" })
    const client = projectionClient([first, second])
    await acceptEdit(client, first.id, "first accepted")
    await acceptEdit(client, second.id, "second accepted")

    confirmMessengerServerEdit(client, chat.id, first.id)
    confirmMessengerServerEdit(client, chat.id, first.id)
    confirmMessengerServerEdit(client, "missing-chat", first.id)
    expect(classifyMessengerServerEdit(client, chat.id, first.id, "first accepted")).toEqual({
      kind: "normal",
    })
    expect(
      classifyMessengerServerEdit(client, chat.id, second.id, "second accepted")
    ).toMatchObject({
      kind: "confirmed",
    })
    confirmMessengerServerEdit(client, chat.id, second.id)
    expect(classifyMessengerServerEdit(client, chat.id, second.id, "second accepted")).toEqual({
      kind: "normal",
    })
  })

  it("does not retire an equal-bytes replacement receipt with an older refresh token", async () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    await acceptEdit(client, target.id, "accepted")
    const oldSnapshot = beginMessengerEditRefresh(client, chat.id)
    const atRequestStart = canonicalMessages(client)
    await acceptEdit(client, target.id, "accepted")
    const replacement = canonicalMessages(client)
    expect(
      finishMessengerEditRefresh(
        client,
        chat.id,
        oldSnapshot,
        replacement,
        atRequestStart,
        replacement
      )
    ).toEqual(new Set())
    await client.fetchQuery({
      queryKey: ["messages", chat.id],
      queryFn: async () => replacement,
    })
    expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toMatchObject({
      kind: "confirmed",
    })

    const currentSnapshot = beginMessengerEditRefresh(client, chat.id)
    expect(
      finishMessengerEditRefresh(
        client,
        chat.id,
        currentSnapshot,
        replacement,
        replacement,
        replacement
      )
    ).toEqual(new Set([target.id]))
    await client.fetchQuery({
      queryKey: ["messages", chat.id],
      queryFn: async () => replacement,
    })
    expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toEqual({
      kind: "normal",
    })
  })

  it("does not mark a peer edit received during a refresh as authoritative old data", async () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    await acceptEdit(client, target.id, "accepted")
    const snapshot = beginMessengerEditRefresh(client, chat.id)
    const before = canonicalMessages(client)
    const peer = messagesPage([
      { ...before.items[0]!, content: "peer arrived", edited_at: "2026-10-22T12:02:00.000Z" },
    ])
    client.setQueryData(["messages", chat.id], peer)

    expect(finishMessengerEditRefresh(client, chat.id, snapshot, before, before, peer)).toEqual(
      new Set()
    )
    expect(canonicalMessages(client)).toEqual(peer)
    expect(projectMessengerMessages(client, accountId, chat.id, peer)?.items[0]).toEqual(
      peer.items[0]
    )
  })

  it("keeps a new query's receipt separate from a removed query's refresh", async () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    await acceptEdit(client, target.id, "accepted")
    const snapshot = beginMessengerEditRefresh(client, chat.id)
    const before = canonicalMessages(client)
    client.removeQueries({ queryKey: ["messages", chat.id], exact: true })
    client.setQueryData(["messages", chat.id], messagesPage([target]))
    await acceptEdit(client, target.id, "accepted")
    const replacement = canonicalMessages(client)

    expect(
      finishMessengerEditRefresh(client, chat.id, snapshot, replacement, before, replacement)
    ).toEqual(new Set())
    await client.fetchQuery({
      queryKey: ["messages", chat.id],
      queryFn: async () => replacement,
    })
    expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toMatchObject({
      kind: "confirmed",
    })
  })

  it.each(["request snapshot", "live snapshot", "server target"] as const)(
    "retains the receipt when the refresh lacks its %s",
    async (missing) => {
      const target = projectionMessage()
      const client = projectionClient([target])
      await acceptEdit(client, target.id, "accepted")
      const snapshot = beginMessengerEditRefresh(client, chat.id)
      const current = canonicalMessages(client)
      expect(
        finishMessengerEditRefresh(
          client,
          chat.id,
          snapshot,
          missing === "server target" ? messagesPage([]) : current,
          missing === "request snapshot" ? undefined : current,
          missing === "live snapshot" ? undefined : current
        )
      ).toEqual(new Set())
      await client.fetchQuery({
        queryKey: ["messages", chat.id],
        queryFn: async () => current,
      })
      expect(classifyMessengerServerEdit(client, chat.id, target.id, "accepted")).toMatchObject({
        kind: "confirmed",
      })
    }
  )
})

describe("operation ordering and query ownership", () => {
  it("does not run an action whose operation was already retired", async () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    const token = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: target.id,
      content: "discarded",
    })
    expect(finishMessengerOperation(client, token, false)).toBe(true)
    const action = vi.fn(async () => "unreachable")
    await expect(runMessengerOperation(client, token, action)).rejects.toBeInstanceOf(
      CancelledError
    )
    expect(action).not.toHaveBeenCalled()
    expect(canonicalMessages(client).items[0]?.content).toBe("canonical")
  })

  it("does not recreate a target that disappears before its edit action starts", async () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    const token = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: target.id,
      content: "accepted for a removed row",
    })
    expect(token).toBeDefined()
    client.setQueryData(["messages", chat.id], messagesPage([]))
    const action = vi.fn(async () => undefined)
    await runMessengerOperation(client, token, action)
    expect(action).toHaveBeenCalledOnce()
    expect(finishMessengerOperation(client, token, true)).toBe(true)
    expect(canonicalMessages(client).items).toEqual([])
  })

  it("retires a later edit to another message while an earlier edit remains pending", () => {
    const first = projectionMessage()
    const second = projectionMessage({ id: "second", content: "second canonical" })
    const client = projectionClient([first, second])
    const earlier = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: first.id,
      content: "first pending",
    })
    const later = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: second.id,
      content: "second accepted",
    })

    expect(finishMessengerOperation(client, later, true)).toBe(true)
    expect(canonicalMessages(client).items.map((item) => item.content)).toEqual([
      "canonical",
      "second accepted",
    ])
    expect(finishMessengerOperation(client, earlier, false)).toBe(true)
    expect(canonicalMessages(client).items.map((item) => item.content)).toEqual([
      "canonical",
      "second accepted",
    ])
  })

  it("commits successful callbacks for the same message in invocation order", () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    const earlier = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: target.id,
      content: "first accepted",
    })
    const later = beginMessengerOperation(client, accountId, chat.id, {
      kind: "edit",
      messageId: target.id,
      content: "second accepted",
    })

    expect(finishMessengerOperation(client, later, true)).toBe(true)
    expect(canonicalMessages(client).items[0]?.content).toBe("canonical")
    expect(finishMessengerOperation(client, earlier, true)).toBe(true)
    expect(canonicalMessages(client).items[0]?.content).toBe("second accepted")
    expect(
      projectMessengerMessages(client, accountId, chat.id, canonicalMessages(client))?.items
    ).toMatchObject([{ content: "second accepted" }])
  })

  it("does not make a pending clear block a successful edit in another chat", () => {
    const target = projectionMessage()
    const client = projectionClient([target])
    const otherId = "other-chat"
    const other = projectionMessage({ id: "other-message", chat_id: otherId })
    client.setQueryData(["messages", otherId], messagesPage([other]))
    const clear = beginMessengerOperation(client, accountId, chat.id, {
      kind: "clear",
      refreshChats: async () => page(0),
    })
    const edit = beginMessengerOperation(client, accountId, otherId, {
      kind: "edit",
      messageId: other.id,
      content: "other accepted",
    })

    expect(finishMessengerOperation(client, edit, true)).toBe(true)
    expect(canonicalMessages(client, otherId).items[0]?.content).toBe("other accepted")
    expect(finishMessengerOperation(client, clear, false)).toBe(true)
    expect(canonicalMessages(client).items[0]).toEqual(target)
    expect(canonicalMessages(client, otherId).items[0]?.content).toBe("other accepted")
  })

  it.each(["clear before edit", "edit before clear"] as const)(
    "holds the real action queue barrier for %s",
    async (order) => {
      const target = projectionMessage()
      const newer = projectionMessage({
        id: "newer",
        content: "arrived after clear started",
        created_at: "2026-10-22T12:02:00.000Z",
      })
      const client = projectionClient([target])
      const gate = actionGate()
      const first = beginMessengerOperation(
        client,
        accountId,
        chat.id,
        order === "clear before edit"
          ? { kind: "clear", refreshChats: async () => page(0) }
          : { kind: "edit", messageId: target.id, content: "accepted before clear" }
      )
      const firstAction = vi.fn(() => gate.promise)
      const firstPending = runMessengerOperation(client, first, firstAction)
      let secondPending: Promise<void> | undefined
      try {
        await vi.advanceTimersByTimeAsync(0)
        expect(firstAction).toHaveBeenCalledOnce()
        if (order === "clear before edit") {
          client.setQueryData(["messages", chat.id], messagesPage([target, newer]))
        }
        const second = beginMessengerOperation(
          client,
          accountId,
          chat.id,
          order === "clear before edit"
            ? { kind: "edit", messageId: newer.id, content: "accepted after clear" }
            : { kind: "clear", refreshChats: async () => page(0) }
        )
        expect(second).toBeDefined()
        const secondAction = vi.fn(async () => undefined)
        secondPending = runMessengerOperation(client, second, secondAction)
        await vi.advanceTimersByTimeAsync(0)
        expect(secondAction).not.toHaveBeenCalled()

        gate.resolve()
        await firstPending
        expect(finishMessengerOperation(client, first, true)).toBe(true)
        await secondPending
        expect(secondAction).toHaveBeenCalledOnce()
        expect(finishMessengerOperation(client, second, true)).toBe(true)
        expect(canonicalMessages(client).items.map((item) => [item.id, item.content])).toEqual(
          order === "clear before edit" ? [[newer.id, "accepted after clear"]] : []
        )
      } finally {
        gate.resolve()
        await Promise.allSettled([firstPending, ...(secondPending ? [secondPending] : [])])
      }
    }
  )
})

describe("receipt retirement and retained clear cutoffs", () => {
  it("retires a deleted receipt, then retires the remaining receipt on clear", async () => {
    const first = projectionMessage()
    const second = projectionMessage({ id: "second", content: "second canonical" })
    const client = projectionClient([first, second])
    await acceptEdit(client, first.id, "first accepted")
    await acceptEdit(client, second.id, "second accepted")
    const confirmed = canonicalMessages(client)
    const deletion = beginMessengerOperation(client, accountId, chat.id, {
      kind: "deleteMessage",
      messageId: first.id,
    })
    expect(finishMessengerOperation(client, deletion, true)).toBe(true)
    expect(canonicalMessages(client).items[0]?.deleted_at).toBeTruthy()

    // Restore matching canonical bytes so classifier fallback cannot hide a
    // failure to retire the receipt in the actual delete/clear commit paths.
    client.setQueryData(["messages", chat.id], confirmed)
    expect(classifyMessengerServerEdit(client, chat.id, first.id, "first accepted")).toEqual({
      kind: "normal",
    })
    expect(
      classifyMessengerServerEdit(client, chat.id, second.id, "second accepted")
    ).toMatchObject({
      kind: "confirmed",
    })
    acceptClear(client)
    expect(canonicalMessages(client).items).toEqual([])
    client.setQueryData(["messages", chat.id], confirmed)
    expect(classifyMessengerServerEdit(client, chat.id, second.id, "second accepted")).toEqual({
      kind: "normal",
    })
  })

  it.each([
    "empty first clear",
    "empty second clear",
    "later cutoff",
    "unordered new cutoff",
    "unordered old cutoff",
  ] as const)("retains both hidden IDs and the safe ordering boundary after %s", (scenario) => {
    const older = projectionMessage()
    const newer = projectionMessage({ id: "newer", created_at: "2026-10-22T12:02:00.000Z" })
    const unordered = projectionMessage({ id: "unordered", created_at: "not-a-timestamp" })
    const unseenBefore = projectionMessage({
      id: "unseen-before",
      created_at: "2026-10-22T11:59:00.000Z",
    })
    const between = projectionMessage({ id: "between", created_at: "2026-10-22T12:01:00.000Z" })
    const after = projectionMessage({ id: "after", created_at: "2026-10-22T12:03:00.000Z" })
    const first =
      scenario === "empty first clear"
        ? []
        : scenario === "unordered old cutoff"
          ? [unordered]
          : [older]
    const second =
      scenario === "empty second clear"
        ? []
        : scenario === "later cutoff"
          ? [newer]
          : scenario === "unordered new cutoff"
            ? [unordered]
            : [older]
    const client = projectionClient(first)
    const oldRefresh = acceptClear(client)
    client.setQueryData(["messages", chat.id], messagesPage(second))
    const currentRefresh = acceptClear(client)
    const stale = messagesPage([...first, ...second, unseenBefore, between, after])

    expect(finishClearRefresh(client, chat.id, oldRefresh, stale)).toEqual({
      fetched: stale,
      cleared: false,
    })
    const refreshed = finishClearRefresh(client, chat.id, currentRefresh, stale)
    expect(refreshed.cleared).toBe(true)
    expect(refreshed.fetched.items.map((item) => item.id)).toEqual(
      scenario === "later cutoff" ? [after.id] : [between.id, after.id]
    )
    expect(
      projectMessengerMessages(client, accountId, chat.id, stale)?.items.map((item) => item.id)
    ).toEqual(refreshed.fetched.items.map((item) => item.id))
  })
})
