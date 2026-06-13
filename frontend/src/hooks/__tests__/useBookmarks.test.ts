/**
 * Session 11 coverage: src/hooks/useBookmarks.ts
 *
 * localStorage + BroadcastChannel external store (useSyncExternalStore). No MSW,
 * no QueryClient. The module-level `bookmarkSet`/`channel` singletons persist
 * across tests in this file, so afterEach drains all bookmarks + clears storage.
 * vi.resetModules() gives a fresh module for the load-from-storage branches.
 */
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useBookmarks } from "../useBookmarks"

const STORAGE_KEY = "news:bookmarks"
const CHANNEL_NAME = "ecosystem.news.bookmarks"

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  // Drain the module-level bookmarkSet back to empty (no public reset).
  const { result, unmount } = renderHook(() => useBookmarks())
  act(() => {
    for (const id of [...result.current.bookmarks]) result.current.toggleBookmark(id)
  })
  unmount()
  localStorage.clear()
  vi.restoreAllMocks()
})

describe("useBookmarks", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useBookmarks())
    expect(result.current.bookmarks).toBeInstanceOf(Set)
    expect(result.current.bookmarkCount).toBe(0)
    expect(result.current.isBookmarked("x")).toBe(false)
  })

  it("toggleBookmark adds + persists to localStorage", () => {
    const { result } = renderHook(() => useBookmarks())
    act(() => result.current.toggleBookmark("a1"))
    expect(result.current.isBookmarked("a1")).toBe(true)
    expect(result.current.bookmarkCount).toBe(1)
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toContain("a1")
  })

  it("toggleBookmark toggles off + removes", () => {
    const { result } = renderHook(() => useBookmarks())
    act(() => result.current.toggleBookmark("a1"))
    act(() => result.current.toggleBookmark("a1"))
    expect(result.current.isBookmarked("a1")).toBe(false)
    expect(result.current.bookmarkCount).toBe(0)
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([])
  })

  it("tracks multiple bookmarks + interleaved add/remove", () => {
    const { result } = renderHook(() => useBookmarks())
    act(() => {
      result.current.toggleBookmark("a")
      result.current.toggleBookmark("b")
      result.current.toggleBookmark("c")
    })
    expect(result.current.bookmarkCount).toBe(3)
    act(() => result.current.toggleBookmark("b"))
    expect(result.current.bookmarkCount).toBe(2)
    expect(result.current.isBookmarked("b")).toBe(false)
  })

  it("hydrates bookmarkSet from localStorage on module load", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(["seed1", "seed2"]))
    vi.resetModules()
    const { useBookmarks: freshUseBookmarks } = await import("../useBookmarks")
    const { result } = renderHook(() => freshUseBookmarks())
    expect(result.current.bookmarkCount).toBe(2)
    expect(result.current.isBookmarked("seed1")).toBe(true)
  })

  it("malformed localStorage JSON -> empty Set (catch)", async () => {
    localStorage.setItem(STORAGE_KEY, "{not-json")
    vi.resetModules()
    const { useBookmarks: freshUseBookmarks } = await import("../useBookmarks")
    const { result } = renderHook(() => freshUseBookmarks())
    expect(result.current.bookmarkCount).toBe(0)
  })

  it("persist swallows storage errors (Safari private-browsing guard)", () => {
    const { result } = renderHook(() => useBookmarks())
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded")
    })
    // No throw; in-memory set still updates.
    act(() => result.current.toggleBookmark("x"))
    expect(result.current.isBookmarked("x")).toBe(true)
  })

  it("syncs from another tab via BroadcastChannel", async () => {
    const { result } = renderHook(() => useBookmarks())
    const otherTab = new BroadcastChannel(CHANNEL_NAME)
    act(() => otherTab.postMessage(["x1", "x2"]))
    await waitFor(() => expect(result.current.isBookmarked("x1")).toBe(true))
    expect(result.current.bookmarkCount).toBe(2)
    otherTab.close()
  })

  it("broadcastUpdate emits to other tabs", async () => {
    const { result } = renderHook(() => useBookmarks())
    const otherTab = new BroadcastChannel(CHANNEL_NAME)
    const messages: string[][] = []
    otherTab.onmessage = (e: MessageEvent<string[]>) => messages.push(e.data)
    act(() => result.current.toggleBookmark("o1"))
    await waitFor(() => expect(messages).toContainEqual(["o1"]))
    otherTab.close()
  })

  it("degrades gracefully when BroadcastChannel is unsupported", async () => {
    vi.resetModules()
    vi.stubGlobal(
      "BroadcastChannel",
      class {
        constructor() {
          throw new Error("unsupported")
        }
      }
    )
    const { useBookmarks: freshUseBookmarks } = await import("../useBookmarks")
    const { result } = renderHook(() => freshUseBookmarks())
    // ensureChannel catch -> channel stays null; toggle still works, no throw.
    act(() => result.current.toggleBookmark("nb1"))
    expect(result.current.isBookmarked("nb1")).toBe(true)
    vi.unstubAllGlobals()
  })
})
