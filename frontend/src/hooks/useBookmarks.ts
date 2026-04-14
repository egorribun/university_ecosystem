import { useCallback, useEffect, useSyncExternalStore } from "react"

const STORAGE_KEY = "news:bookmarks"
const CHANNEL_NAME = "ecosystem.news.bookmarks"

/* ── External store for cross-tab sync ── */
let bookmarkSet: Set<string> = loadFromStorage()
let listeners: Array<() => void> = []

function loadFromStorage(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set()
  } catch {
    return new Set()
  }
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...bookmarkSet]))
  } catch {
    // RZ-31-03: Safari private browsing guard
  }
}

function emitChange() {
  for (const listener of listeners) listener()
}

function getSnapshot(): Set<string> {
  return bookmarkSet
}

function subscribe(listener: () => void): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}

/* ── BroadcastChannel cross-tab sync ── */
let channel: BroadcastChannel | null = null

function ensureChannel() {
  if (channel) return
  try {
    channel = new BroadcastChannel(CHANNEL_NAME)
    channel.onmessage = (event: MessageEvent<string[]>) => {
      bookmarkSet = new Set(event.data)
      emitChange()
    }
  } catch {
    // BroadcastChannel not supported — degrade gracefully
  }
}

function broadcastUpdate() {
  channel?.postMessage([...bookmarkSet])
}

/**
 * Hook for managing news bookmarks.
 * Persisted in localStorage with cross-tab sync via BroadcastChannel.
 */
export function useBookmarks() {
  useEffect(() => { ensureChannel() }, [])

  const bookmarks = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  const isBookmarked = useCallback(
    (id: string) => bookmarks.has(id),
    [bookmarks]
  )

  const toggleBookmark = useCallback((id: string) => {
    const next = new Set(bookmarkSet)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    bookmarkSet = next
    persist()
    broadcastUpdate()
    emitChange()
  }, [])

  const bookmarkCount = bookmarks.size

  return { bookmarks, isBookmarked, toggleBookmark, bookmarkCount } as const
}
