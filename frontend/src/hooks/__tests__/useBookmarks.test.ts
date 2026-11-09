/**
 * Session 11 coverage: src/hooks/useBookmarks.ts
 *
 * localStorage + BroadcastChannel external store (useSyncExternalStore). No MSW,
 * no QueryClient. The module-level `bookmarkSet`/`channel` singletons persist
 * across tests in this file, so afterEach drains all bookmarks + clears storage.
 * vi.resetModules() gives a fresh module for the load-from-storage branches.
 */
import { createElement } from "react"
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useBookmarks } from "../useBookmarks"

const STORAGE_KEY = "news:bookmarks"
const CHANNEL_NAME = "ecosystem.news.bookmarks"

function readPersistedBookmarks(): string[] {
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as
    string[] | { version: 2; items: Record<string, { bookmarked: boolean }> }
  if (Array.isArray(stored)) return stored
  return Object.entries(stored.items)
    .filter(([, record]) => record.bookmarked)
    .map(([id]) => id)
}

async function withTrackedBroadcastChannels<T>(run: (channels: BroadcastChannel[]) => Promise<T>) {
  const NativeBroadcastChannel = globalThis.BroadcastChannel
  const createdChannels: BroadcastChannel[] = []
  class TrackedBroadcastChannel extends NativeBroadcastChannel {
    constructor(name: string) {
      super(name)
      createdChannels.push(this)
    }
  }
  vi.stubGlobal("BroadcastChannel", TrackedBroadcastChannel)
  try {
    return await run(createdChannels)
  } finally {
    for (const channel of createdChannels) channel.close()
    vi.unstubAllGlobals()
  }
}

async function withBroadcastChannelUnavailable<T>(run: () => Promise<T>) {
  vi.stubGlobal(
    "BroadcastChannel",
    class {
      constructor() {
        throw new Error("unsupported")
      }
    }
  )
  try {
    await run()
  } finally {
    vi.unstubAllGlobals()
  }
}

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

  it("uses a readable fallback actor when crypto.randomUUID throws", async () => {
    await withBroadcastChannelUnavailable(async () => {
      const originalCrypto = globalThis.crypto
      const randomUUID = vi.fn(() => {
        throw new Error("randomUUID unavailable")
      })
      vi.spyOn(Math, "random").mockReturnValue(0.5)
      vi.stubGlobal(
        "crypto",
        new Proxy(originalCrypto, {
          get(target, property, receiver) {
            if (property === "randomUUID") return randomUUID
            const value = Reflect.get(target, property, receiver)
            return typeof value === "function" ? value.bind(target) : value
          },
        })
      )
      vi.resetModules()
      const fallbackTab = await import("../useBookmarks")
      const fallback = renderHook(() => fallbackTab.useBookmarks())
      try {
        act(() => fallback.result.current.toggleBookmark("fallback-actor"))

        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          items: Record<string, { actor: string; bookmarked: boolean }>
        }
        expect(randomUUID).toHaveBeenCalledOnce()
        expect(fallback.result.current.isBookmarked("fallback-actor")).toBe(true)
        expect(stored.items["fallback-actor"]?.bookmarked).toBe(true)
        expect(stored.items["fallback-actor"]?.actor).toMatch(/^tab-[a-z0-9]+-[a-z0-9]+$/)
      } finally {
        fallback.unmount()
      }

      vi.stubGlobal(
        "crypto",
        new Proxy(originalCrypto, {
          get(target, property, receiver) {
            if (property === "randomUUID") return () => "reload-actor"
            const value = Reflect.get(target, property, receiver)
            return typeof value === "function" ? value.bind(target) : value
          },
        })
      )
      vi.resetModules()
      const reloadedTab = await import("../useBookmarks")
      const reloaded = renderHook(() => reloadedTab.useBookmarks())
      try {
        expect(reloaded.result.current.isBookmarked("fallback-actor")).toBe(true)
      } finally {
        reloaded.unmount()
      }
    })
  })

  it("toggleBookmark adds + persists to localStorage", () => {
    const { result } = renderHook(() => useBookmarks())
    act(() => result.current.toggleBookmark("a1"))
    expect(result.current.isBookmarked("a1")).toBe(true)
    expect(result.current.bookmarkCount).toBe(1)
    expect(readPersistedBookmarks()).toContain("a1")
  })

  it("toggleBookmark toggles off + removes", () => {
    const { result } = renderHook(() => useBookmarks())
    act(() => result.current.toggleBookmark("a1"))
    act(() => result.current.toggleBookmark("a1"))
    expect(result.current.isBookmarked("a1")).toBe(false)
    expect(result.current.bookmarkCount).toBe(0)
    expect(readPersistedBookmarks()).toEqual([])
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
    await withBroadcastChannelUnavailable(async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(["seed1", "seed2"]))
      vi.resetModules()
      const { useBookmarks: freshUseBookmarks } = await import("../useBookmarks")
      const { result } = renderHook(() => freshUseBookmarks())
      expect(result.current.bookmarkCount).toBe(2)
      expect(result.current.isBookmarked("seed1")).toBe(true)
    })
  })

  it("malformed localStorage JSON -> empty Set (catch)", async () => {
    await withBroadcastChannelUnavailable(async () => {
      localStorage.setItem(STORAGE_KEY, "{not-json")
      vi.resetModules()
      const { useBookmarks: freshUseBookmarks } = await import("../useBookmarks")
      const { result } = renderHook(() => freshUseBookmarks())
      expect(result.current.bookmarkCount).toBe(0)
    })
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
    act(() =>
      otherTab.postMessage({
        type: "bookmark-state",
        id: "x1",
        bookmarked: true,
        clock: 1,
        actor: "remote-tab",
      })
    )
    await waitFor(() => expect(result.current.isBookmarked("x1")).toBe(true))
    expect(result.current.bookmarkCount).toBe(1)
    otherTab.close()
  })

  it("broadcastUpdate emits to other tabs", async () => {
    const { result } = renderHook(() => useBookmarks())
    const otherTab = new BroadcastChannel(CHANNEL_NAME)
    const messages: unknown[] = []
    otherTab.onmessage = (e: MessageEvent<unknown>) => messages.push(e.data)
    act(() => result.current.toggleBookmark("o1"))
    await waitFor(() =>
      expect(messages).toContainEqual(
        expect.objectContaining({
          type: "bookmark-state",
          id: "o1",
          bookmarked: true,
          actor: expect.any(String),
        })
      )
    )
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

  it("merges concurrent changes to different bookmarks across two real tabs", async () => {
    await withTrackedBroadcastChannels(async () => {
      vi.resetModules()
      const leftTab = await import("../useBookmarks")
      vi.resetModules()
      const rightTab = await import("../useBookmarks")
      const left = renderHook(() => leftTab.useBookmarks())
      const right = renderHook(() => rightTab.useBookmarks())
      try {
        act(() => {
          left.result.current.toggleBookmark("left-change")
          right.result.current.toggleBookmark("right-change")
        })

        await waitFor(() => {
          expect([...left.result.current.bookmarks].sort()).toEqual(["left-change", "right-change"])
          expect([...right.result.current.bookmarks].sort()).toEqual([
            "left-change",
            "right-change",
          ])
          expect(readPersistedBookmarks().sort()).toEqual(["left-change", "right-change"])
        })
      } finally {
        left.unmount()
        right.unmount()
      }
    })
  })

  it("resolves same-clock bookmark conflicts consistently regardless of arrival order", async () => {
    await withTrackedBroadcastChannels(async () => {
      vi.resetModules()
      const leftTab = await import("../useBookmarks")
      vi.resetModules()
      const rightTab = await import("../useBookmarks")
      const left = renderHook(() => leftTab.useBookmarks())
      const right = renderHook(() => rightTab.useBookmarks())
      const publisher = new BroadcastChannel(CHANNEL_NAME)
      try {
        act(() => {
          publisher.postMessage({
            type: "bookmark-state",
            id: "z-first",
            bookmarked: true,
            clock: 9,
            actor: "actor-z",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "z-first",
            bookmarked: false,
            clock: 9,
            actor: "actor-a",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "a-first",
            bookmarked: false,
            clock: 9,
            actor: "actor-a",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "a-first",
            bookmarked: true,
            clock: 9,
            actor: "actor-z",
          })
        })

        await waitFor(() => {
          expect(left.result.current.isBookmarked("z-first")).toBe(true)
          expect(right.result.current.isBookmarked("z-first")).toBe(true)
          expect(left.result.current.isBookmarked("a-first")).toBe(true)
          expect(right.result.current.isBookmarked("a-first")).toBe(true)
        })
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          items: Record<string, { actor: string; bookmarked: boolean; clock: number }>
        }
        expect(stored.items["z-first"]).toMatchObject({ actor: "actor-z", bookmarked: true })
        expect(stored.items["a-first"]).toMatchObject({ actor: "actor-z", bookmarked: true })
      } finally {
        publisher.close()
        left.unmount()
        right.unmount()
      }
    })
  })

  it("migrates legacy lists and fails closed on malformed versioned records", async () => {
    await withBroadcastChannelUnavailable(async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(["legacy-id"]))
      vi.resetModules()
      const legacyTab = await import("../useBookmarks")
      const legacy = renderHook(() => legacyTab.useBookmarks())
      try {
        expect(legacy.result.current.isBookmarked("legacy-id")).toBe(true)
        act(() => legacy.result.current.toggleBookmark("new-id"))
        const migrated = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          version: number
          items: Record<string, { bookmarked: boolean; actor: string }>
        }
        expect(migrated.version).toBe(2)
        expect(migrated.items["legacy-id"]).toMatchObject({ bookmarked: true, actor: "legacy" })
        expect(migrated.items["new-id"]?.bookmarked).toBe(true)
      } finally {
        legacy.unmount()
      }

      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: 2,
          items: {
            fractional: { bookmarked: true, clock: 1.5, actor: "valid-actor" },
            unsafeClock: {
              bookmarked: true,
              clock: Number.MAX_SAFE_INTEGER + 1,
              actor: "valid-actor",
            },
            invalidActor: { bookmarked: true, clock: 2, actor: "actor with spaces" },
          },
        })
      )
      vi.resetModules()
      const malformedTab = await import("../useBookmarks")
      const malformed = renderHook(() => malformedTab.useBookmarks())
      try {
        expect(malformed.result.current.bookmarkCount).toBe(0)
        act(() => malformed.result.current.toggleBookmark("__proto__"))
        expect(malformed.result.current.isBookmarked("__proto__")).toBe(true)
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          items: Record<string, { bookmarked: boolean }>
        }
        expect(Object.prototype.hasOwnProperty.call(stored.items, "__proto__")).toBe(true)
        expect(stored.items["__proto__"]?.bookmarked).toBe(true)
        expect(Object.prototype).not.toHaveProperty("polluted")
      } finally {
        malformed.unmount()
      }
    })
  })

  it("does not create an unsafe Lamport clock when the safe integer range is exhausted", async () => {
    await withBroadcastChannelUnavailable(async () => {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: 2,
          items: {
            saved: { bookmarked: true, clock: Number.MAX_SAFE_INTEGER, actor: "seed" },
          },
        })
      )
      vi.resetModules()
      const tab = await import("../useBookmarks")
      const { result } = renderHook(() => tab.useBookmarks())
      act(() => result.current.toggleBookmark("saved"))
      expect(result.current.isBookmarked("saved")).toBe(true)
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
        items: Record<string, { bookmarked: boolean; clock: number }>
      }
      expect(stored.items.saved).toEqual({
        bookmarked: true,
        clock: Number.MAX_SAFE_INTEGER,
        actor: "seed",
      })
    })
  })

  it("notifies mounted consumers when an exhausted toggle merges newer durable records", async () => {
    await withBroadcastChannelUnavailable(async () => {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: 2,
          items: {
            saved: { bookmarked: true, clock: Number.MAX_SAFE_INTEGER, actor: "seed" },
          },
        })
      )
      vi.resetModules()
      const tab = await import("../useBookmarks")
      function BookmarkProbe() {
        const { bookmarks, toggleBookmark } = tab.useBookmarks()
        return createElement(
          "div",
          null,
          createElement("output", { "aria-label": "Bookmarks" }, [...bookmarks].sort().join(",")),
          createElement(
            "button",
            { type: "button", onClick: () => toggleBookmark("attempted") },
            "Toggle"
          )
        )
      }

      const view = render(createElement(BookmarkProbe))
      try {
        expect(screen.getByLabelText("Bookmarks").textContent).toBe("saved")
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            version: 2,
            items: {
              saved: { bookmarked: true, clock: Number.MAX_SAFE_INTEGER, actor: "seed" },
              "external-change": { bookmarked: true, clock: 4, actor: "other-tab" },
            },
          })
        )

        fireEvent.click(screen.getByRole("button", { name: "Toggle" }))

        expect(screen.getByLabelText("Bookmarks").textContent).toBe("external-change,saved")
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          items: Record<string, { actor: string; bookmarked: boolean; clock: number }>
        }
        expect(stored.items["external-change"]).toEqual({
          bookmarked: true,
          clock: 4,
          actor: "other-tab",
        })
        expect(stored.items).not.toHaveProperty("attempted")
      } finally {
        view.unmount()
      }
    })
  })

  it("keeps bookmark changes in memory when localStorage is unavailable", async () => {
    const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: undefined,
    })

    try {
      await withBroadcastChannelUnavailable(async () => {
        vi.resetModules()
        const { useBookmarks: noStorageTab } = await import("../useBookmarks")
        const { result, unmount } = renderHook(() => noStorageTab())
        try {
          act(() => result.current.toggleBookmark("memory-only"))

          expect(result.current.isBookmarked("memory-only")).toBe(true)
          expect(result.current.bookmarkCount).toBe(1)
        } finally {
          unmount()
        }
      })
    } finally {
      if (storageDescriptor) {
        Object.defineProperty(globalThis, "localStorage", storageDescriptor)
      } else {
        Reflect.deleteProperty(globalThis, "localStorage")
      }
    }
  })

  it("uses bookmarked state to break same-clock, same-actor conflicts", async () => {
    await withTrackedBroadcastChannels(async () => {
      vi.resetModules()
      const tab = await import("../useBookmarks")
      const { result, unmount } = renderHook(() => tab.useBookmarks())
      const publisher = new BroadcastChannel(CHANNEL_NAME)
      try {
        act(() => {
          publisher.postMessage({
            type: "bookmark-state",
            id: "true-wins",
            bookmarked: false,
            clock: 12,
            actor: "same-actor",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "true-wins",
            bookmarked: true,
            clock: 12,
            actor: "same-actor",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "false-loses",
            bookmarked: true,
            clock: 12,
            actor: "same-actor",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "false-loses",
            bookmarked: false,
            clock: 12,
            actor: "same-actor",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "true-wins",
            bookmarked: true,
            clock: 12,
            actor: "same-actor",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "completion-sentinel",
            bookmarked: false,
            clock: 13,
            actor: "completion-actor",
          })
        })

        await waitFor(() => {
          const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
            items: Record<string, { actor: string; bookmarked: boolean; clock: number }>
          }
          expect(persisted.items["completion-sentinel"]).toEqual({
            actor: "completion-actor",
            bookmarked: false,
            clock: 13,
          })
          expect([...result.current.bookmarks].sort()).toEqual(["false-loses", "true-wins"])
        })
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as {
          items: Record<string, { actor: string; bookmarked: boolean; clock: number }>
        }
        expect(stored.items["true-wins"]).toEqual({
          actor: "same-actor",
          bookmarked: true,
          clock: 12,
        })
        expect(stored.items["false-loses"]).toEqual({
          actor: "same-actor",
          bookmarked: true,
          clock: 12,
        })
      } finally {
        publisher.close()
        unmount()
      }
    })
  })

  it("ignores malformed cross-tab operations before applying valid messages", async () => {
    await withTrackedBroadcastChannels(async () => {
      vi.resetModules()
      const tab = await import("../useBookmarks")
      const { result, unmount } = renderHook(() => tab.useBookmarks())
      const publisher = new BroadcastChannel(CHANNEL_NAME)
      try {
        act(() => {
          publisher.postMessage({
            type: "bookmark-state",
            id: "",
            bookmarked: true,
            clock: 1,
            actor: "remote-tab",
          })
          publisher.postMessage({
            type: "bookmark-state",
            id: "valid-control",
            bookmarked: true,
            clock: 2,
            actor: "remote-tab",
          })
        })

        await waitFor(() => {
          expect(result.current.isBookmarked("valid-control")).toBe(true)
        })
        expect([...result.current.bookmarks]).toEqual(["valid-control"])
        expect(readPersistedBookmarks()).toEqual(["valid-control"])
      } finally {
        publisher.close()
        unmount()
      }
    })
  })

  it("does not persist a toggle for an invalid bookmark id", () => {
    const { result } = renderHook(() => useBookmarks())
    const setItem = vi.spyOn(Storage.prototype, "setItem")

    act(() => result.current.toggleBookmark(""))

    expect(result.current.bookmarkCount).toBe(0)
    expect(result.current.isBookmarked("")).toBe(false)
    expect(setItem).not.toHaveBeenCalled()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
