import { useCallback, useEffect, useSyncExternalStore } from "react"
import * as v from "valibot"

const STORAGE_KEY = "news:bookmarks"
const CHANNEL_NAME = "ecosystem.news.bookmarks"
const EMPTY_SERVER_SNAPSHOT = new Set<string>()

const BookmarkIdSchema = v.pipe(v.string(), v.minLength(1))
const ClockSchema = v.pipe(v.number(), v.safeInteger(), v.minValue(0))
const ActorSchema = v.pipe(v.string(), v.regex(/^[A-Za-z0-9_-]{1,128}$/))

const BookmarkRecordSchema = v.object({
  bookmarked: v.boolean(),
  clock: ClockSchema,
  actor: ActorSchema,
})
const StoredBookmarkStateSchema = v.object({
  version: v.literal(2),
  items: v.record(BookmarkIdSchema, BookmarkRecordSchema),
})
const LegacyBookmarkListSchema = v.array(BookmarkIdSchema)
const BookmarkOperationSchema = v.object({
  type: v.literal("bookmark-state"),
  id: BookmarkIdSchema,
  bookmarked: v.boolean(),
  clock: ClockSchema,
  actor: ActorSchema,
})

type BookmarkRecord = v.InferOutput<typeof BookmarkRecordSchema>
type BookmarkOperation = v.InferOutput<typeof BookmarkOperationSchema>

/* ── External store for cross-tab sync ── */
let bookmarkRecords: Map<string, BookmarkRecord> = loadFromStorage()
let bookmarkSet = createBookmarkSet(bookmarkRecords)
let lamportClock = highestClock(bookmarkRecords)
let listeners: Array<() => void> = []

function createActorId(): string {
  try {
    const id = globalThis.crypto?.randomUUID?.()
    if (id) return id
  } catch {
    // Some browser contexts do not expose randomUUID.
  }
  return `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

const actorId = createActorId()

function decodeStoredRecords(value: unknown): Map<string, BookmarkRecord> {
  const legacy = v.safeParse(LegacyBookmarkListSchema, value)
  if (legacy.success) {
    return new Map(legacy.output.map((id) => [id, { bookmarked: true, clock: 0, actor: "legacy" }]))
  }

  const stored = v.safeParse(StoredBookmarkStateSchema, value)
  if (!stored.success) return new Map()
  return new Map(Object.entries(stored.output.items))
}

function loadFromStorage(): Map<string, BookmarkRecord> {
  try {
    if (typeof localStorage === "undefined") return new Map()
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? decodeStoredRecords(JSON.parse(raw) as unknown) : new Map()
  } catch {
    return new Map()
  }
}

function recordsEqual(
  left: ReadonlyMap<string, BookmarkRecord>,
  right: ReadonlyMap<string, BookmarkRecord>
): boolean {
  if (left.size !== right.size) return false
  for (const [id, leftRecord] of left) {
    const rightRecord = right.get(id)
    if (
      !rightRecord ||
      leftRecord.bookmarked !== rightRecord.bookmarked ||
      leftRecord.clock !== rightRecord.clock ||
      leftRecord.actor !== rightRecord.actor
    ) {
      return false
    }
  }
  return true
}

function compareRecords(left: BookmarkRecord, right: BookmarkRecord): number {
  if (left.clock !== right.clock) return left.clock > right.clock ? 1 : -1
  if (left.actor !== right.actor) return left.actor > right.actor ? 1 : -1
  if (left.bookmarked !== right.bookmarked) return left.bookmarked ? 1 : -1
  return 0
}

function mergeRecords(
  ...sources: ReadonlyMap<string, BookmarkRecord>[]
): Map<string, BookmarkRecord> {
  const merged = new Map<string, BookmarkRecord>()
  for (const source of sources) {
    for (const [id, candidate] of source) {
      const current = merged.get(id)
      if (!current || compareRecords(candidate, current) > 0) merged.set(id, candidate)
    }
  }
  return merged
}

function createBookmarkSet(records: ReadonlyMap<string, BookmarkRecord>): Set<string> {
  return new Set([...records].filter(([, record]) => record.bookmarked).map(([id]) => id))
}

function highestClock(records: ReadonlyMap<string, BookmarkRecord>): number {
  let highest = 0
  for (const record of records.values()) highest = Math.max(highest, record.clock)
  return highest
}

function replaceRecords(next: Map<string, BookmarkRecord>): boolean {
  if (recordsEqual(bookmarkRecords, next)) return false
  bookmarkRecords = next
  bookmarkSet = createBookmarkSet(next)
  lamportClock = Math.max(lamportClock, highestClock(next))
  return true
}

function persistMergedState(): boolean {
  const changed = replaceRecords(mergeRecords(bookmarkRecords, loadFromStorage()))
  lamportClock = Math.max(lamportClock, highestClock(bookmarkRecords))
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ version: 2, items: Object.fromEntries(bookmarkRecords) })
      )
    }
  } catch {
    // RZ-31-03: Safari private browsing guard
  }
  return changed
}

function emitChange() {
  for (const listener of listeners) listener()
}

function getSnapshot(): Set<string> {
  return bookmarkSet
}

function getServerSnapshot(): Set<string> {
  return EMPTY_SERVER_SNAPSHOT
}

function subscribe(listener: () => void): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}

/* ── BroadcastChannel cross-tab sync ── */
let channel: BroadcastChannel | null = null

function applyOperation(operation: BookmarkOperation) {
  lamportClock = Math.max(lamportClock, operation.clock)
  const incoming = new Map<string, BookmarkRecord>([
    [
      operation.id,
      { bookmarked: operation.bookmarked, clock: operation.clock, actor: operation.actor },
    ],
  ])
  const changed = replaceRecords(mergeRecords(bookmarkRecords, loadFromStorage(), incoming))
  const persistedChange = persistMergedState()
  if (changed || persistedChange) emitChange()
}

function ensureChannel() {
  if (channel) return
  try {
    channel = new BroadcastChannel(CHANNEL_NAME)
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const parsed = v.safeParse(BookmarkOperationSchema, event.data)
      if (parsed.success) applyOperation(parsed.output)
    }
  } catch {
    // BroadcastChannel not supported — degrade gracefully
  }
}

function broadcastUpdate(operation: BookmarkOperation) {
  channel?.postMessage(operation)
}

function toggleBookmarkState(id: string) {
  if (!v.safeParse(BookmarkIdSchema, id).success) return

  // Merge the latest durable state before computing a new desired value. This
  // also prevents a tab that missed a channel event from writing a stale list.
  const mergedDurableState = persistMergedState()
  const highestObservedClock = Math.max(lamportClock, highestClock(bookmarkRecords))
  if (highestObservedClock >= Number.MAX_SAFE_INTEGER) {
    if (mergedDurableState) emitChange()
    return
  }
  const operation: BookmarkOperation = {
    type: "bookmark-state",
    id,
    bookmarked: !bookmarkSet.has(id),
    clock: highestObservedClock + 1,
    actor: actorId,
  }
  lamportClock = operation.clock
  replaceRecords(
    mergeRecords(
      bookmarkRecords,
      new Map([[id, { bookmarked: operation.bookmarked, clock: operation.clock, actor: actorId }]])
    )
  )
  persistMergedState()
  broadcastUpdate(operation)
  emitChange()
}

/**
 * Hook for managing news bookmarks.
 * Persisted in localStorage with cross-tab sync via per-bookmark operations.
 */
export function useBookmarks() {
  useEffect(() => {
    ensureChannel()
  }, [])

  const bookmarks = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  const isBookmarked = useCallback((id: string) => bookmarks.has(id), [bookmarks])
  const toggleBookmark = useCallback((id: string) => toggleBookmarkState(id), [])

  const bookmarkCount = bookmarks.size

  return { bookmarks, isBookmarked, toggleBookmark, bookmarkCount } as const
}
