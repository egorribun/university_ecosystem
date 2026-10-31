import { useMemo, useSyncExternalStore } from "react"
import { CancelledError, useQueryClient, type Query, type QueryClient } from "@tanstack/react-query"
import type { Chat, ChatsListResponse, Message, MessagesListResponse } from "@/api/chat"
import {
  captureSessionEpoch,
  getBrowserSessionGeneration,
  getSessionEpoch,
  isCurrentBrowserSession,
} from "@/stores/sessionEpoch"
import { compareMessageOrder } from "@/utils/messageOrder"

type Reaction = NonNullable<Message["reactions"]>[number]
type Operation = {
  token: object
  accountId: string | null
  sessionEpoch: number
  chatId: string
  ownsSession: () => boolean
  retireSession: () => void
  chatsQuery?: Query
  messagesQuery?: Query
  status: "pending" | "succeeded" | "failed"
} & (
  | {
      kind: "edit"
      messageId: string
      content: string
      editedAt: string
      before: Pick<Message, "content" | "edited_at">
      superseded: boolean
      started: boolean
    }
  | { kind: "deleteMessage"; messageId: string; deletedAt: string }
  | { kind: "reaction"; messageId: string; emoji: string; reacted: boolean }
  | {
      kind: "clear"
      cutoff?: Message
      hiddenIds: Set<string>
      unread: number
      refreshChats: () => Promise<ChatsListResponse>
    }
  | { kind: "deleteChat" }
)

type Input =
  | { kind: "edit"; messageId: string; content: string }
  | { kind: "deleteMessage"; messageId: string }
  | { kind: "reaction"; messageId: string; emoji: string; reacted: boolean }
  | { kind: "clear"; refreshChats: () => Promise<ChatsListResponse> }
  | { kind: "deleteChat" }

type ConfirmedEdit = {
  token: object
  accountId: string | null
  ownsSession: () => boolean
  retireSession: () => void
  content: string
  serverEditedAt: string | null | undefined
  optimisticEditedAt: string
  retireOnSuccess: boolean
}

type ProjectionStore = {
  entries: Operation[]
  operationQueues: Map<object, Map<string, Promise<void>>>
  clearRefreshes: Map<
    Query,
    { token: object; operation: Extract<Operation, { kind: "clear" }>; retireOnSuccess: boolean }
  >
  confirmedEdits: Map<Query, Map<string, ConfirmedEdit>>
  chatRefreshes: Set<Extract<Operation, { kind: "clear" }>>
  failedChatRefreshes: Map<
    Query,
    { operation: Extract<Operation, { kind: "clear" }>; fetchUpdateCount?: number }
  >
  subscribe: (listener: () => void) => () => void
  snapshot: () => Operation[]
  publish: (entries: Operation[]) => void
}

const stores = new WeakMap<QueryClient, ProjectionStore>()
const SESSION_GENERATION_STORAGE_KEY = "ecosystem.session.generation.v1"

function getStore(client: QueryClient): ProjectionStore {
  let store = stores.get(client)
  if (store) return store
  const listeners = new Set<() => void>()
  let detachStorage: (() => void) | undefined
  store = {
    entries: [],
    operationQueues: new Map(),
    clearRefreshes: new Map(),
    confirmedEdits: new Map(),
    chatRefreshes: new Set(),
    failedChatRefreshes: new Map(),
    subscribe: (listener) => {
      listeners.add(listener)
      if (listeners.size === 1 && typeof window !== "undefined") {
        const onStorage = (event: StorageEvent) => {
          if (event.key !== null && event.key !== SESSION_GENERATION_STORAGE_KEY) return
          try {
            if (event.storageArea && event.storageArea !== window.localStorage) return
          } catch {
            // Unavailable local storage cannot prove the session is current.
          }
          store!.entries.forEach((operation) => operation.retireSession())
          store!.clearRefreshes.forEach((refresh) => refresh.operation.retireSession())
          store!.confirmedEdits.forEach((edits) => edits.forEach((edit) => edit.retireSession()))
          store!.chatRefreshes.forEach((operation) => operation.retireSession())
          store!.failedChatRefreshes.forEach((refresh) => refresh.operation.retireSession())
          store!.clearRefreshes.clear()
          store!.confirmedEdits.clear()
          store!.failedChatRefreshes.clear()
          store!.operationQueues.clear()
          store!.publish([])
        }
        window.addEventListener("storage", onStorage)
        detachStorage = () => window.removeEventListener("storage", onStorage)
      }
      return () => {
        listeners.delete(listener)
        if (listeners.size === 0) {
          detachStorage?.()
          detachStorage = undefined
        }
      }
    },
    snapshot: () => store!.entries,
    publish: (entries) => {
      store!.entries = entries
      listeners.forEach((listener) => listener())
    },
  }
  stores.set(client, store)
  client.getQueryCache().subscribe((event) => {
    if (event.type === "updated") {
      const recovery = store!.failedChatRefreshes.get(event.query)
      if (recovery) {
        if (!ownsChats(client, recovery.operation)) {
          store!.failedChatRefreshes.delete(event.query)
        } else if (event.action.type === "fetch") {
          recovery.fetchUpdateCount = event.query.state.dataUpdateCount
        } else if (event.action.type === "success") {
          const recovered =
            !event.action.manual &&
            recovery.fetchUpdateCount !== undefined &&
            event.query.state.dataUpdateCount === recovery.fetchUpdateCount + 1
          if (recovered) {
            store!.failedChatRefreshes.delete(event.query)
          } else {
            if (!event.action.manual) recovery.fetchUpdateCount = undefined
            // Query.invalidate() already ignores a query that is still invalidated.
            event.query.invalidate()
          }
        } else if (event.action.type === "setState") {
          // Cancellation can restore a pre-invalidation manual-write snapshot.
          recovery.fetchUpdateCount = undefined
          event.query.invalidate()
        } else if (event.action.type === "error") {
          recovery.fetchUpdateCount = undefined
        }
      }
    }
    if (event.type === "updated" && event.action.type === "success" && !event.action.manual) {
      const refresh = store!.clearRefreshes.get(event.query)
      if (refresh?.retireOnSuccess && refresh.operation.ownsSession()) {
        store!.clearRefreshes.delete(event.query)
        store!.publish([...store!.entries])
      }
      const edits = store!.confirmedEdits.get(event.query)
      if (edits) {
        let retired = false
        for (const [messageId, edit] of edits) {
          if (edit.retireOnSuccess && edit.ownsSession()) {
            edits.delete(messageId)
            retired = true
          }
        }
        if (edits.size === 0) store!.confirmedEdits.delete(event.query)
        if (retired) store!.publish([...store!.entries])
      }
    }
    if (event.type !== "removed") return
    store!.clearRefreshes.delete(event.query)
    store!.confirmedEdits.delete(event.query)
    store!.failedChatRefreshes.delete(event.query)
    store!.operationQueues.delete(event.query)
    const retained = store!.entries.filter((operation) => ownsRelevantQuery(client, operation))
    if (retained.length !== store!.entries.length) store!.publish(retained)
  })
  return store
}

const queryFor = (client: QueryClient, key: readonly string[]) =>
  client.getQueryCache().find({ queryKey: key, exact: true })

const ownsMessages = (client: QueryClient, operation: Operation) =>
  operation.ownsSession() &&
  operation.messagesQuery !== undefined &&
  queryFor(client, ["messages", operation.chatId]) === operation.messagesQuery

const ownsChats = (client: QueryClient, operation: Operation) =>
  operation.ownsSession() &&
  operation.chatsQuery !== undefined &&
  queryFor(client, ["chats"]) === operation.chatsQuery

function ownsRelevantQuery(client: QueryClient, operation: Operation) {
  return operation.kind === "clear" || operation.kind === "deleteChat"
    ? ownsMessages(client, operation) || ownsChats(client, operation)
    : ownsMessages(client, operation)
}

function setReaction(
  reactions: Reaction[] | undefined,
  emoji: string,
  reacted: boolean
): Reaction[] {
  const result = [...(reactions ?? [])]
  const index = result.findIndex((reaction) => reaction.emoji === emoji)
  const current = result[index]
  if ((current?.reacted_by_me ?? false) === reacted) return result
  if (!current) result.push({ emoji, count: 1, reacted_by_me: true })
  else if (!reacted && current.count <= 1) result.splice(index, 1)
  else
    result[index] = {
      ...current,
      count: current.count + (reacted ? 1 : -1),
      reacted_by_me: reacted,
    }
  return result
}

export function applyOwnReactionFrame(
  data: MessagesListResponse | undefined,
  frame: { message_id: string; emoji: string; action: "added" | "removed" }
) {
  if (!data) return data
  const target = data.items.find((message) => message.id === frame.message_id)
  const current = target?.reactions?.find((reaction) => reaction.emoji === frame.emoji)
  if (!target || (current?.reacted_by_me ?? false) === (frame.action === "added")) return data
  return {
    ...data,
    items: data.items.map((message) =>
      message.id === frame.message_id
        ? {
            ...message,
            reactions: setReaction(message.reactions, frame.emoji, frame.action === "added"),
          }
        : message
    ),
  }
}

function isCleared(message: Message, operation: Extract<Operation, { kind: "clear" }>) {
  if (operation.hiddenIds.has(message.id)) return true
  if (!operation.cutoff) return false
  const order = compareMessageOrder(message, operation.cutoff)
  return order !== null && order <= 0
}

function applyMessages(data: MessagesListResponse, operation: Operation): MessagesListResponse {
  if (operation.kind === "clear") {
    return {
      ...data,
      items: data.items.filter((message) => !isCleared(message, operation)),
      has_more: false,
      next_cursor: null,
    }
  }
  if (operation.kind === "deleteChat") return data
  return {
    ...data,
    items: data.items.map((message) => {
      if (message.id !== operation.messageId) return message
      if (operation.kind === "deleteMessage")
        return {
          ...message,
          content: "",
          attachments: [],
          deleted_at: message.deleted_at ?? operation.deletedAt,
        }
      if (message.deleted_at) return message
      if (operation.kind === "edit")
        return operation.superseded
          ? message
          : { ...message, content: operation.content, edited_at: operation.editedAt }
      return {
        ...message,
        reactions: setReaction(message.reactions, operation.emoji, operation.reacted),
      }
    }),
  }
}

function applyChats(data: ChatsListResponse, operation: Operation): ChatsListResponse {
  if (operation.kind === "deleteChat")
    return { ...data, items: data.items.filter((chat) => chat.id !== operation.chatId) }
  if (operation.kind !== "clear") return data
  return {
    ...data,
    items: data.items.map((chat) =>
      chat.id !== operation.chatId
        ? chat
        : {
            ...chat,
            last_message:
              chat.last_message && !isCleared(chat.last_message, operation)
                ? chat.last_message
                : undefined,
            unread_count: Math.max(0, chat.unread_count - operation.unread),
          }
    ),
  }
}

export function projectMessengerMessages(
  client: QueryClient,
  accountId: string | null,
  chatId: string,
  data: MessagesListResponse | undefined,
  entries = getStore(client).entries
) {
  const store = getStore(client)
  const query = queryFor(client, ["messages", chatId])
  const clear = query && store.clearRefreshes.get(query)?.operation
  let base =
    data && clear && clear.accountId === accountId && clear.ownsSession()
      ? applyMessages(data, clear)
      : data
  const confirmed = query && store.confirmedEdits.get(query)
  if (base && confirmed) {
    base = {
      ...base,
      items: base.items.map((message) => {
        const edit = confirmed.get(message.id)
        return edit &&
          edit.accountId === accountId &&
          edit.ownsSession() &&
          !message.deleted_at &&
          message.content === edit.content &&
          message.edited_at === edit.serverEditedAt
          ? { ...message, edited_at: edit.optimisticEditedAt }
          : message
      }),
    }
  }
  return entries.reduce(
    (current, operation) =>
      current &&
      operation.status !== "failed" &&
      operation.accountId === accountId &&
      operation.chatId === chatId &&
      ownsMessages(client, operation)
        ? applyMessages(current, operation)
        : current,
    base
  )
}

function projectMessengerChats(
  client: QueryClient,
  accountId: string | null,
  data: ChatsListResponse | undefined,
  entries = getStore(client).entries
) {
  return entries.reduce(
    (current, operation) =>
      current &&
      operation.status !== "failed" &&
      operation.accountId === accountId &&
      ownsChats(client, operation)
        ? applyChats(current, operation)
        : current,
    data
  )
}

export function useProjectedMessengerMessages(
  data: MessagesListResponse | undefined,
  accountId: string | null,
  chatId: string | null
) {
  const client = useQueryClient()
  const store = getStore(client)
  const entries = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const sessionEpoch = getSessionEpoch()
  const sessionGeneration = getBrowserSessionGeneration()
  const sessionIsCurrent = isCurrentBrowserSession()
  return useMemo(() => {
    void sessionEpoch
    void sessionGeneration
    void sessionIsCurrent
    return chatId ? projectMessengerMessages(client, accountId, chatId, data, entries) : data
  }, [client, accountId, chatId, data, entries, sessionEpoch, sessionGeneration, sessionIsCurrent])
}

export function useProjectedMessengerChats(
  data: ChatsListResponse | undefined,
  accountId: string | null
) {
  const client = useQueryClient()
  const store = getStore(client)
  const entries = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const sessionEpoch = getSessionEpoch()
  const sessionGeneration = getBrowserSessionGeneration()
  const sessionIsCurrent = isCurrentBrowserSession()
  return useMemo(() => {
    void sessionEpoch
    void sessionGeneration
    void sessionIsCurrent
    return projectMessengerChats(client, accountId, data, entries)
  }, [client, accountId, data, entries, sessionEpoch, sessionGeneration, sessionIsCurrent])
}

export function beginMessengerOperation(
  client: QueryClient,
  accountId: string | null,
  chatId: string,
  input: Input
): object | undefined {
  const store = getStore(client)
  const activeEntries = store.entries.filter(
    (operation) => operation.accountId === accountId && ownsRelevantQuery(client, operation)
  )
  const messagesQuery = queryFor(client, ["messages", chatId])
  const chatsQuery = queryFor(client, ["chats"])
  const current = projectMessengerMessages(
    client,
    accountId,
    chatId,
    client.getQueryData(["messages", chatId]),
    activeEntries
  )
  const chats = projectMessengerChats(
    client,
    accountId,
    client.getQueryData(["chats"]),
    activeEntries
  )
  const ownsEpoch = captureSessionEpoch()
  let retired = false
  const ownsSession = () => {
    if (!ownsEpoch()) retired = true
    return !retired
  }
  const base = {
    token: {},
    accountId,
    sessionEpoch: getSessionEpoch(),
    chatId,
    ownsSession,
    retireSession: () => {
      retired = true
    },
    messagesQuery,
    chatsQuery,
    status: "pending" as const,
  }
  let operation: Operation
  if (input.kind === "edit") {
    const target = client
      .getQueryData<MessagesListResponse>(["messages", chatId])
      ?.items.find((message) => message.id === input.messageId)
    if (!target || target.deleted_at) {
      if (activeEntries.length !== store.entries.length) store.publish(activeEntries)
      return undefined
    }
    operation = {
      ...base,
      ...input,
      editedAt: new Date().toISOString(),
      before: { content: target.content, edited_at: target.edited_at },
      superseded: false,
      started: false,
    }
  } else if (input.kind === "deleteMessage") {
    operation = { ...base, ...input, deletedAt: new Date().toISOString() }
  } else if (input.kind === "clear") {
    const chat =
      chats?.items.find((item) => item.id === chatId) ??
      client.getQueryData<Chat>(["chats", chatId])
    const items = [...(current?.items ?? []), ...(chat?.last_message ? [chat.last_message] : [])]
    const cutoff = items.reduce<Message | undefined>(
      (latest, item) => (!latest || (compareMessageOrder(item, latest) ?? -1) > 0 ? item : latest),
      undefined
    )
    operation = {
      ...base,
      kind: "clear",
      cutoff,
      hiddenIds: new Set(items.map((item) => item.id)),
      unread: chat?.unread_count ?? 0,
      refreshChats: input.refreshChats,
    }
  } else operation = { ...base, ...input }
  store.publish([...activeEntries, operation])
  return operation.token
}

// A validated, non-stale server edit owns the underlying fields even when its
// bytes happen to match an optimistic rendering.
export function noteMessengerServerEdit(
  client: QueryClient,
  chatId: string,
  messageId: string,
  fields: Pick<Message, "content" | "edited_at">,
  confirmedBefore?: Pick<Message, "content" | "edited_at">
) {
  const store = getStore(client)
  let changed = false
  const entries = store.entries.map((operation) => {
    if (
      operation.kind !== "edit" ||
      operation.chatId !== chatId ||
      operation.messageId !== messageId ||
      !ownsMessages(client, operation)
    )
      return operation
    if (!operation.started) {
      changed = true
      return { ...operation, before: fields }
    }
    if (
      confirmedBefore &&
      operation.before.content === confirmedBefore.content &&
      operation.before.edited_at === confirmedBefore.edited_at
    ) {
      changed = true
      return { ...operation, before: fields }
    }
    if (!operation.superseded && operation.content === fields.content) {
      changed = true
      return { ...operation, superseded: true }
    }
    return operation
  })
  if (changed) store.publish(entries)
}

export function classifyMessengerServerEdit(
  client: QueryClient,
  chatId: string,
  messageId: string,
  content: string
):
  | { kind: "normal" | "refresh" }
  | {
      kind: "confirmed"
      before: Pick<Message, "content" | "edited_at">
    } {
  const query = queryFor(client, ["messages", chatId])
  const store = getStore(client)
  const edits = query && store.confirmedEdits.get(query)
  const edit = edits?.get(messageId)
  if (!query || !edit || !edit.ownsSession()) return { kind: "normal" }
  const target = client
    .getQueryData<MessagesListResponse>(["messages", chatId])
    ?.items.find((message) => message.id === messageId)
  if (
    !target ||
    target.deleted_at ||
    target.content !== edit.content ||
    target.edited_at !== edit.serverEditedAt
  ) {
    edits!.delete(messageId)
    if (edits!.size === 0) store.confirmedEdits.delete(query)
    store.publish([...store.entries])
    return { kind: "normal" }
  }
  if (content !== edit.content) return { kind: "refresh" }
  return { kind: "confirmed", before: { content: edit.content, edited_at: edit.serverEditedAt } }
}

export function confirmMessengerServerEdit(client: QueryClient, chatId: string, messageId: string) {
  const query = queryFor(client, ["messages", chatId])
  const store = getStore(client)
  const edits = query && store.confirmedEdits.get(query)
  if (!query || !edits?.delete(messageId)) return
  if (edits.size === 0) store.confirmedEdits.delete(query)
  store.publish([...store.entries])
}

export function beginMessengerEditRefresh(client: QueryClient, chatId: string) {
  const query = queryFor(client, ["messages", chatId])
  const edits = query && getStore(client).confirmedEdits.get(query)
  const snapshot = new Map<string, object>()
  edits?.forEach((edit, messageId) => {
    if (!edit.ownsSession()) return
    edit.retireOnSuccess = false
    snapshot.set(messageId, edit.token)
  })
  return snapshot
}

export function finishMessengerEditRefresh(
  client: QueryClient,
  chatId: string,
  snapshot: Map<string, object>,
  fetched: MessagesListResponse,
  atRequestStart: MessagesListResponse | undefined,
  current: MessagesListResponse | undefined
) {
  const query = queryFor(client, ["messages", chatId])
  const edits = query && getStore(client).confirmedEdits.get(query)
  const authoritative = new Set<string>()
  for (const [messageId, token] of snapshot) {
    const edit = edits?.get(messageId)
    const before = atRequestStart?.items.find((message) => message.id === messageId)
    const live = current?.items.find((message) => message.id === messageId)
    const server = fetched.items.find((message) => message.id === messageId)
    if (!edit || edit.token !== token || !edit.ownsSession() || !before || !live || !server)
      continue
    if (
      before.content !== live.content ||
      before.edited_at !== live.edited_at ||
      live.content !== edit.content ||
      live.edited_at !== edit.serverEditedAt
    )
      continue
    edit.retireOnSuccess = true
    authoritative.add(messageId)
  }
  return authoritative
}

export function runMessengerOperation<T>(
  client: QueryClient,
  token: object | undefined,
  action: () => Promise<T>
): Promise<T> {
  if (!token) return action()
  const store = getStore(client)
  const operation = store.entries.find((item) => item.token === token)
  if (!operation) {
    return Promise.reject(new CancelledError({ silent: true }))
  }
  const owner = operation.messagesQuery ?? operation.chatsQuery ?? operation.token
  const maintenance = operation.kind === "clear" || operation.kind === "deleteChat"
  const scope = `${JSON.stringify([operation.sessionEpoch, operation.accountId])}\u0000`
  const queueKey = `${scope}${maintenance ? "\u0000chat" : operation.messageId}`
  const queue = store.operationQueues.get(owner) ?? new Map<string, Promise<void>>()
  store.operationQueues.set(owner, queue)
  const predecessors = maintenance
    ? [...queue.entries()].filter(([key]) => key.startsWith(scope)).map(([, value]) => value)
    : [queue.get(`${scope}\u0000chat`), queue.get(queueKey)].filter((value) => value !== undefined)
  const result = Promise.all(predecessors).then(() => {
    if (
      !operation.ownsSession() ||
      (operation.messagesQuery && !ownsMessages(client, operation)) ||
      (!operation.messagesQuery && operation.chatsQuery && !ownsChats(client, operation))
    ) {
      throw new CancelledError({ silent: true })
    }
    if (operation.kind === "edit") {
      const target = client
        .getQueryData<MessagesListResponse>(["messages", operation.chatId])
        ?.items.find((message) => message.id === operation.messageId)
      store.publish(
        store.entries.map((item) =>
          item.token === token && item.kind === "edit"
            ? {
                ...item,
                started: true,
                before: target
                  ? { content: target.content, edited_at: target.edited_at }
                  : item.before,
              }
            : item
        )
      )
    }
    return action()
  })
  const tail = result.then(
    () => undefined,
    () => undefined
  )
  queue.set(queueKey, tail)
  void tail.then(() => {
    if (queue.get(queueKey) !== tail) return
    queue.delete(queueKey)
    if (queue.size === 0 && store.operationQueues.get(owner) === queue) {
      store.operationQueues.delete(owner)
    }
  })
  return result
}

export function getClearRefresh(client: QueryClient, chatId: string): object | undefined {
  const query = queryFor(client, ["messages", chatId])
  const refresh = query && getStore(client).clearRefreshes.get(query)
  return refresh?.operation.ownsSession() ? refresh.token : undefined
}

export function finishClearRefresh(
  client: QueryClient,
  chatId: string,
  token: object | undefined,
  fetched: MessagesListResponse
) {
  if (!token) return { fetched, cleared: false }
  const query = queryFor(client, ["messages", chatId])
  const store = getStore(client)
  const refresh = query && store.clearRefreshes.get(query)
  if (!query || !refresh || refresh.token !== token || !refresh.operation.ownsSession()) {
    return { fetched, cleared: false }
  }
  const items = fetched.items.filter((message) => !isCleared(message, refresh.operation))
  // Keep masking until React Query has installed this successful response.
  refresh.retireOnSuccess = items.length === fetched.items.length
  return { fetched: { ...fetched, items }, cleared: true }
}

const CHAT_REFRESH_QUIET_MS = 100

// The caller checks ownership synchronously before waiting; cache events and the
// quiet timer re-check it while the wait is pending.
function waitForQuietChatsAfterClear(
  client: QueryClient,
  operation: Extract<Operation, { kind: "clear" }>
): Promise<boolean> {
  return new Promise((resolve) => {
    let timer: ReturnType<typeof setTimeout> | undefined
    // Detaching the listener and clearing the timer let this promise settle once.
    const finish = (current: boolean) => {
      clearTimeout(timer)
      detach()
      resolve(current)
    }
    const restartQuietPeriod = () => {
      clearTimeout(timer)
      timer = setTimeout(() => finish(ownsChats(client, operation)), CHAT_REFRESH_QUIET_MS)
    }
    const detach = client.getQueryCache().subscribe((event) => {
      if (!ownsChats(client, operation)) {
        finish(false)
        return
      }
      if (
        event.query === operation.chatsQuery &&
        event.type === "updated" &&
        event.action.type === "success"
      ) {
        restartQuietPeriod()
      }
    })
    restartQuietPeriod()
  })
}

async function reconcileChatsAfterClear(
  client: QueryClient,
  operation: Extract<Operation, { kind: "clear" }>
) {
  // A response cannot replace a WebSocket update received while it was in
  // flight. After three immediate collisions, coalesce external data changes
  // into one quiet-period attempt instead of dropping the pending correction.
  let collisions = 0
  while (ownsChats(client, operation)) {
    if (collisions >= 3 && !(await waitForQuietChatsAfterClear(client, operation))) return
    if (!ownsChats(client, operation)) return
    const before = client.getQueryData<ChatsListResponse>(["chats"])
    if (!before) return
    const query = operation.chatsQuery!
    const recovery = getStore(client).failedChatRefreshes.get(query)
    const updateCount = query.state.dataUpdateCount
    const fetched = await operation.refreshChats()
    if (!ownsChats(client, operation)) return
    if (client.getQueryData<ChatsListResponse>(["chats"]) !== before) {
      collisions += 1
      continue
    }
    const merged: ChatsListResponse = {
      ...fetched,
      items: fetched.items.map((chat) => {
        const live = before.items.find((item) => item.id === chat.id)
        return live
          ? {
              ...chat,
              presence: live.presence ?? chat.presence,
              read_receipts: live.read_receipts ?? chat.read_receipts,
            }
          : chat
      }),
    }
    if (
      recovery &&
      getStore(client).failedChatRefreshes.get(query) === recovery &&
      query.state.dataUpdateCount === updateCount &&
      query.state.fetchStatus === "idle"
    ) {
      getStore(client).failedChatRefreshes.delete(query)
    }
    client.setQueryData<ChatsListResponse>(["chats"], merged)
    return
  }
}

function commitOperation(client: QueryClient, operation: Operation) {
  let committedEdit = false
  if (ownsMessages(client, operation) && operation.kind !== "deleteChat") {
    client.setQueryData<MessagesListResponse>(["messages", operation.chatId], (current) => {
      if (!current) return current
      if (operation.kind === "edit") {
        const target = current.items.find((message) => message.id === operation.messageId)
        if (
          !target ||
          target.deleted_at ||
          operation.superseded ||
          target.content !== operation.before.content ||
          target.edited_at !== operation.before.edited_at
        )
          return current
      }
      if (operation.kind === "edit") {
        committedEdit = true
        return {
          ...current,
          items: current.items.map((message) =>
            message.id === operation.messageId
              ? { ...message, content: operation.content, edited_at: operation.before.edited_at }
              : message
          ),
        }
      }
      return applyMessages(current, operation)
    })
  }
  if (committedEdit && operation.kind === "edit" && operation.messagesQuery) {
    const store = getStore(client)
    const edits =
      store.confirmedEdits.get(operation.messagesQuery) ?? new Map<string, ConfirmedEdit>()
    edits.set(operation.messageId, {
      token: {},
      accountId: operation.accountId,
      ownsSession: operation.ownsSession,
      retireSession: operation.retireSession,
      content: operation.content,
      serverEditedAt: operation.before.edited_at,
      optimisticEditedAt: operation.editedAt,
      retireOnSuccess: false,
    })
    store.confirmedEdits.set(operation.messagesQuery, edits)
  }
  if (
    operation.messagesQuery &&
    (operation.kind === "clear" || operation.kind === "deleteMessage")
  ) {
    const store = getStore(client)
    const edits = store.confirmedEdits.get(operation.messagesQuery)
    if (edits) {
      const remaining =
        client.getQueryData<MessagesListResponse>(["messages", operation.chatId])?.items ?? []
      for (const messageId of edits.keys()) {
        if (
          operation.kind === "deleteMessage"
            ? messageId === operation.messageId
            : !remaining.some((message) => message.id === messageId)
        )
          edits.delete(messageId)
      }
      if (edits.size === 0) store.confirmedEdits.delete(operation.messagesQuery)
    }
  }
  if (
    ownsChats(client, operation) &&
    (operation.kind === "clear" || operation.kind === "deleteChat")
  ) {
    client.setQueryData<ChatsListResponse>(["chats"], (current) =>
      current ? applyChats(current, operation) : current
    )
  }
  if (operation.kind === "clear" && ownsMessages(client, operation)) {
    const store = getStore(client)
    const previous = store.clearRefreshes.get(operation.messagesQuery!)?.operation
    let retained = operation
    if (previous && previous.accountId === operation.accountId && previous.ownsSession()) {
      const olderCutoff = previous.cutoff
      const newerCutoff = operation.cutoff
      const order =
        olderCutoff && newerCutoff ? compareMessageOrder(newerCutoff, olderCutoff) : null
      const cutoff = !olderCutoff
        ? newerCutoff
        : !newerCutoff
          ? olderCutoff
          : order !== null
            ? order > 0
              ? newerCutoff
              : olderCutoff
            : compareMessageOrder(olderCutoff, olderCutoff) !== null
              ? olderCutoff
              : newerCutoff
      retained = {
        ...operation,
        cutoff,
        hiddenIds: new Set([...previous.hiddenIds, ...operation.hiddenIds]),
      }
    }
    store.clearRefreshes.set(operation.messagesQuery!, {
      token: {},
      operation: retained,
      retireOnSuccess: false,
    })
    void client.invalidateQueries({
      queryKey: ["messages", operation.chatId],
      refetchType: "active",
    })
  }
  if (operation.kind === "clear" && ownsChats(client, operation)) {
    const store = getStore(client)
    store.chatRefreshes.add(operation)
    void reconcileChatsAfterClear(client, operation).then(
      () => store.chatRefreshes.delete(operation),
      () => {
        store.chatRefreshes.delete(operation)
        const query = operation.chatsQuery
        if (query && ownsChats(client, operation)) {
          // Keep a failed post-clear refresh stale across unrelated live writes
          // until a newer uncontended server fetch repairs the aggregate.
          store.failedChatRefreshes.set(query, { operation })
          query.invalidate()
        }
      }
    )
  }
  if (operation.kind === "deleteChat" && ownsMessages(client, operation)) {
    client.removeQueries({ queryKey: ["messages", operation.chatId], exact: true })
  }
  return committedEdit
}

export function finishMessengerOperation(
  client: QueryClient,
  token: object | undefined,
  succeeded: boolean
) {
  if (!token) return false
  const store = getStore(client)
  const operation = store.entries.find((item) => item.token === token)
  if (!operation) return false
  const ownsMessagesQuery = ownsMessages(client, operation)
  const ownsChatsQuery = ownsChats(client, operation)
  let entries: Operation[] = store.entries.map((item) =>
    item.token === token ? { ...item, status: succeeded ? "succeeded" : "failed" } : item
  )
  // Publish conflicting operations in invocation order, independently of
  // MutationCache retention and HTTP completion order. Unrelated messages can
  // retire while an earlier request remains pending.
  while (true) {
    const index = entries.findIndex(
      (item, position) =>
        item.status !== "pending" &&
        (item.status === "failed" ||
          !entries.slice(0, position).some((earlier) => operationsConflict(earlier, item)))
    )
    if (index < 0) break
    const first = entries[index]!
    const committedEdit = first.status === "succeeded" && commitOperation(client, first)
    entries = entries.filter((item) => item !== first)
    if (committedEdit && first.kind === "edit") {
      entries = entries.map((item) =>
        item.kind === "edit" &&
        item.chatId === first.chatId &&
        item.messageId === first.messageId &&
        item.before.content === first.before.content &&
        item.before.edited_at === first.before.edited_at
          ? { ...item, before: { content: first.content, edited_at: first.before.edited_at } }
          : item
      )
    }
  }
  store.publish(entries)
  if (ownsMessagesQuery)
    client.invalidateQueries({ queryKey: ["messages", operation.chatId], refetchType: "none" })
  if (ownsChatsQuery && operation.kind !== "reaction")
    client.invalidateQueries({ queryKey: ["chats"], refetchType: "none" })
  return ownsMessagesQuery || ownsChatsQuery
}

function operationsConflict(left: Operation, right: Operation) {
  if (left.chatId !== right.chatId) return false
  if (
    left.kind === "clear" ||
    left.kind === "deleteChat" ||
    right.kind === "clear" ||
    right.kind === "deleteChat"
  )
    return true
  return left.messageId === right.messageId
}
