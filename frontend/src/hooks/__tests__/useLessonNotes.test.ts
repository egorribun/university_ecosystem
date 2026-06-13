/**
 * Session 11 coverage: src/hooks/useLessonNotes.ts (useLessonNotes + useLessonNotesMap)
 *
 * 300ms debounced save (fake timers) + cleanup-on-unmount + per-id presence map.
 * idb-keyval is mocked with a self-contained in-memory Map (ESM namespace exports
 * are frozen, so vi.spyOn(namespace,...) is impossible — a hoisted vi.mock is the
 * robust path). Happy paths use the map; error branches use mockRejectedValueOnce.
 * logError is mocked to assert the swallowed-error branches.
 */
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { logError } from "@/app/logger"
import { useLessonNotes, useLessonNotesMap, type LessonNote } from "../useLessonNotes"

const idb = vi.hoisted(() => {
  const store = new Map<string, unknown>()
  return {
    store,
    get: vi.fn(async (key: string) => store.get(key)),
    set: vi.fn(async (key: string, value: unknown) => {
      store.set(key, value)
    }),
    del: vi.fn(async (key: string) => {
      store.delete(key)
    }),
  }
})

vi.mock("idb-keyval", () => ({ get: idb.get, set: idb.set, del: idb.del }))
vi.mock("@/app/logger", async (orig) => ({
  ...(await orig<typeof import("@/app/logger")>()),
  logError: vi.fn(),
}))

const KEY = (id: string) => `schedule:notes:${id}`

beforeEach(() => {
  vi.useRealTimers()
  idb.store.clear()
  idb.get.mockClear()
  idb.set.mockClear()
  idb.del.mockClear()
  vi.mocked(logError).mockClear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useLessonNotes", () => {
  it("initial load — no stored note -> null", async () => {
    const { result } = renderHook(() => useLessonNotes("lessonA"))
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.note).toBeNull()
    expect(result.current.hasNote).toBe(false)
  })

  it("initial load — pre-stored note", async () => {
    idb.store.set(KEY("lessonB"), { text: "stored note", updatedAt: 111 })
    const { result } = renderHook(() => useLessonNotes("lessonB"))
    await waitFor(() => expect(result.current.note?.text).toBe("stored note"))
    expect(result.current.hasNote).toBe(true)
  })

  it("null lessonId -> no load, note null", async () => {
    const { result } = renderHook(() => useLessonNotes(null))
    expect(result.current.note).toBeNull()
    expect(result.current.isLoading).toBe(false)
  })

  it("setNote writes to IDB after the 300ms debounce", async () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLessonNotes("lessonC"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setNote("hello"))
    expect(result.current.note?.text).toBe("hello") // immediate state set
    expect(idb.store.get(KEY("lessonC"))).toBeUndefined() // not yet written
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect((idb.store.get(KEY("lessonC")) as LessonNote).text).toBe("hello")
  })

  it("setNote coalesces rapid calls (clearTimeout) — single write of last value", async () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLessonNotes("lessonCo"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => {
      result.current.setNote("a")
      result.current.setNote("ab")
      result.current.setNote("abc")
    })
    expect(result.current.note?.text).toBe("abc")
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect((idb.store.get(KEY("lessonCo")) as LessonNote).text).toBe("abc")
    expect(idb.set).toHaveBeenCalledTimes(1)
  })

  it("setNote with whitespace text deletes instead of writing", async () => {
    idb.store.set(KEY("lessonD"), { text: "existing", updatedAt: 1 })
    vi.useFakeTimers()
    const { result } = renderHook(() => useLessonNotes("lessonD"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setNote("   "))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect(idb.store.get(KEY("lessonD"))).toBeUndefined() // del branch ran
    expect(idb.del).toHaveBeenCalled()
  })

  it("setNote is a no-op when lessonId is null", () => {
    const { result } = renderHook(() => useLessonNotes(null))
    act(() => result.current.setNote("x"))
    expect(result.current.note).toBeNull()
  })

  it("clearNote clears state + deletes from IDB", async () => {
    idb.store.set(KEY("lessonE"), { text: "to clear", updatedAt: 1 })
    const { result } = renderHook(() => useLessonNotes("lessonE"))
    await waitFor(() => expect(result.current.note?.text).toBe("to clear"))
    await act(async () => {
      result.current.clearNote()
      await Promise.resolve()
    })
    expect(result.current.note).toBeNull()
    expect(result.current.hasNote).toBe(false)
    expect(idb.store.get(KEY("lessonE"))).toBeUndefined()
  })

  it("clearNote is a no-op when lessonId is undefined", () => {
    const { result } = renderHook(() => useLessonNotes(undefined))
    act(() => result.current.clearNote())
    expect(result.current.note).toBeNull()
  })

  it("unmount cancels a pending debounced write", async () => {
    vi.useFakeTimers()
    const { result, unmount } = renderHook(() => useLessonNotes("lessonF"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setNote("pending"))
    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect(idb.set).not.toHaveBeenCalled()
    expect(idb.store.get(KEY("lessonF"))).toBeUndefined()
  })

  it("load error -> note null (catch)", async () => {
    idb.get.mockRejectedValueOnce(new Error("idb fail"))
    const { result } = renderHook(() => useLessonNotes("lessonErr"))
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.note).toBeNull()
  })

  it("setNote IDB write error -> logError swallows it", async () => {
    vi.useFakeTimers()
    idb.set.mockRejectedValueOnce(new Error("write fail"))
    const { result } = renderHook(() => useLessonNotes("lessonWr"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setNote("boom"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
      await Promise.resolve() // flush the rejected set()'s .catch microtask
    })
    // NOTE: cannot use waitFor() here — fake timers freeze its polling clock.
    expect(logError).toHaveBeenCalled()
    expect(vi.mocked(logError).mock.calls[0]?.[0]).toBe("[schedule:notes]")
  })
})

describe("useLessonNotesMap", () => {
  it("batch loads a presence map (trims whitespace)", async () => {
    idb.store.set(KEY("m1"), { text: "has note", updatedAt: 1 })
    idb.store.set(KEY("m3"), { text: "  ", updatedAt: 1 })
    const { result } = renderHook(() => useLessonNotesMap(["m1", "m2", "m3"]))
    await waitFor(() => expect(result.current.size).toBe(3))
    expect(result.current.get("m1")).toBe(true)
    expect(result.current.get("m2")).toBe(false)
    expect(result.current.get("m3")).toBe(false)
  })

  it("empty lessonIds -> empty map (no load)", () => {
    const { result } = renderHook(() => useLessonNotesMap([]))
    expect(result.current.size).toBe(0)
  })

  it("stable depKey -> no re-fetch when array ref changes but ids match", async () => {
    const { result, rerender } = renderHook(({ ids }) => useLessonNotesMap(ids), {
      initialProps: { ids: ["x", "y"] },
    })
    await waitFor(() => expect(result.current.size).toBe(2))
    const callsAfterFirst = idb.get.mock.calls.length
    rerender({ ids: ["x", "y"] }) // new array ref, same join key
    expect(idb.get.mock.calls.length).toBe(callsAfterFirst)
  })

  it("get rejection -> entry false (per-id catch)", async () => {
    idb.get.mockRejectedValueOnce(new Error("x"))
    const { result } = renderHook(() => useLessonNotesMap(["e1"]))
    await waitFor(() => expect(result.current.size).toBe(1))
    expect(result.current.get("e1")).toBe(false)
  })
})
