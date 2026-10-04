/**
 * Session 11 coverage: src/hooks/useLessonNotes.ts (useLessonNotes + useLessonNotesMap)
 *
 * 300ms debounced save (fake timers) + cleanup-on-unmount + per-id presence map.
 * idb-keyval is mocked with a self-contained in-memory Map (ESM namespace exports
 * are frozen, so vi.spyOn(namespace,...) is impossible — a hoisted vi.mock is the
 * robust path). Happy paths use the map; error branches use mockRejectedValueOnce.
 * logError is mocked to assert the swallowed-error branches.
 */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useAuthStore } from "@/stores/useAuthStore"
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

const dbState = vi.hoisted(() => ({
  getDatabase: vi.fn(async () => {
    throw new Error("RxDB disabled in unit test")
  }),
}))

vi.mock("idb-keyval", () => ({ get: idb.get, set: idb.set, del: idb.del }))
vi.mock("@/app/logger", async (orig) => ({
  ...(await orig<typeof import("@/app/logger")>()),
  logError: vi.fn(),
}))
vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: dbState.getDatabase,
  resetDatabaseForTesting: vi.fn(async () => {}),
}))

const KEY = (id: string, owner = "user-a") => `schedule:notes:v2:${JSON.stringify([owner, id])}`

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function finishDeferredRead(
  waitForRead: () => Promise<unknown>,
  unmount: () => void,
  settleRead: () => Promise<void>
) {
  const errors: unknown[] = []
  try {
    await waitForRead()
  } catch (error) {
    errors.push(error)
  } finally {
    // A failed entry assertion must still unmount and settle the owned read.
    // Run both cleanups even if one fails, without hiding the original error.
    for (const cleanup of [unmount, settleRead]) {
      try {
        await cleanup()
      } catch (error) {
        errors.push(error)
      }
    }
  }
  if (errors.length === 1) throw errors[0]
  if (errors.length > 1) throw new AggregateError(errors, "Deferred note read cleanup failed")
}

let previousAuthState: ReturnType<typeof useAuthStore.getState>

beforeEach(() => {
  vi.useRealTimers()
  previousAuthState = useAuthStore.getState()
  useAuthStore.setState({
    user: { id: "user-a" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
    loading: false,
  })
  idb.store.clear()
  // Restore the in-memory implementations as well as clearing call history and
  // any one-shot results an interrupted load did not consume.
  idb.get.mockReset()
  idb.set.mockReset()
  idb.del.mockReset()
  dbState.getDatabase.mockReset()
  dbState.getDatabase.mockImplementation(async () => {
    throw new Error("RxDB disabled in unit test")
  })
  vi.mocked(logError).mockClear()
})

afterEach(async () => {
  try {
    // Unmount while the test's timer implementation is still installed, then
    // finish already-started storage continuations before resetting the mocks.
    await act(async () => cleanup())
  } finally {
    useAuthStore.setState(previousAuthState, true)
    vi.useRealTimers()
  }
})

describe("useLessonNotes", () => {
  it.each(["-1", "ssr-stub", "lhci-mock-user"])(
    "does not persist under placeholder identity %s",
    async (id) => {
      useAuthStore.setState({
        user: { id } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
      })
      const { result } = renderHook(() => useLessonNotes("shared"))
      act(() => result.current.setNote("private"))
      await act(async () => {
        await Promise.resolve()
      })
      expect(result.current.note).toBeNull()
      expect(idb.get).not.toHaveBeenCalled()
      expect(idb.set).not.toHaveBeenCalled()
    }
  )

  it("loads only the new owner's note and indicator for the same lesson", async () => {
    idb.store.set(KEY("shared"), { text: "private A", updatedAt: 1 })
    idb.store.set(KEY("shared", "user-b"), { text: "private B", updatedAt: 2 })
    const { result } = renderHook(() => ({
      note: useLessonNotes("shared"),
      map: useLessonNotesMap(["shared"]),
    }))
    await waitFor(() => expect(result.current.note.note?.text).toBe("private A"))
    act(() =>
      useAuthStore.setState({
        user: { id: "user-b" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
      })
    )
    expect(result.current.note.note).toBeNull()
    expect(result.current.map.size).toBe(0)
    await waitFor(() => expect(result.current.note.note?.text).toBe("private B"))
    await waitFor(() => expect(result.current.map.get("shared")).toBe(true))
  })

  it("rolls back an IndexedDB write that finishes after account expiry", async () => {
    vi.useFakeTimers()
    const entered = deferred<void>()
    const release = deferred<void>()
    idb.set.mockImplementationOnce(async (key, value) => {
      entered.resolve()
      await release.promise
      idb.store.set(key, value)
    })
    const { result } = renderHook(() => useLessonNotes("delayed"))
    await act(() => vi.advanceTimersByTimeAsync(0))
    act(() => result.current.setNote("late private A"))
    await act(() => vi.advanceTimersByTimeAsync(300))
    await entered.promise
    act(() => useAuthStore.setState({ user: null }))
    await act(async () => {
      release.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(idb.store.get(KEY("delayed"))).toBeUndefined()
    expect(result.current.note).toBeNull()
  })

  it("never reads legacy notes or writes without a confirmed account", async () => {
    useAuthStore.setState({ user: null })
    idb.store.set("schedule:notes:shared", { text: "private A", updatedAt: 1 })
    const { result } = renderHook(() => useLessonNotes("shared"))
    await act(async () => {
      await Promise.resolve()
    })
    act(() => result.current.setNote("anonymous"))
    expect(result.current.note).toBeNull()
    expect(idb.get).not.toHaveBeenCalled()
    expect(idb.set).not.toHaveBeenCalled()
  })

  it("does not carry a debounced note into another account or lesson", async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ lesson }) => useLessonNotes(lesson), {
      initialProps: { lesson: "same" },
    })
    await act(() => vi.advanceTimersByTimeAsync(0))
    act(() => result.current.setNote("private A"))
    act(() =>
      useAuthStore.setState({
        user: { id: "user-b" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
      })
    )
    expect(result.current.note).toBeNull()
    rerender({ lesson: "another" })
    await act(() => vi.advanceTimersByTimeAsync(400))
    expect(idb.store.get(KEY("same", "user-b"))).toBeUndefined()
    expect(idb.store.get(KEY("another", "user-b"))).toBeUndefined()
  })

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

  it("uses an available RxDB note before falling back to IndexedDB", async () => {
    const rxNote = { id: "lessonRx", text: "from RxDB", updated_at: 42, remove: vi.fn() }
    const findOne = vi.fn(() => ({ exec: vi.fn(async () => rxNote) }))
    const upsert = vi.fn(async () => undefined)
    const find = vi.fn(() => ({ exec: vi.fn(async () => [rxNote]) }))
    dbState.getDatabase.mockResolvedValue({ notes: { findOne, upsert, find } } as never)

    const { result } = renderHook(() => useLessonNotes("lessonRx"))
    await waitFor(() => expect(result.current.note?.text).toBe("from RxDB"))
    expect(idb.get).not.toHaveBeenCalled()

    vi.useFakeTimers()
    act(() => result.current.setNote("updated in RxDB"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        id: JSON.stringify(["user-a", "lessonRx"]),
        text: "updated in RxDB",
        updated_at: expect.any(Number),
      })
    )
  })

  it("falls back to IndexedDB when RxDB resolves without a note", async () => {
    idb.store.set(KEY("lessonRxEmpty"), { text: "from IDB", updatedAt: 17 })
    const findOne = vi.fn(() => ({ exec: vi.fn(async () => null) }))
    dbState.getDatabase.mockResolvedValue({
      notes: { findOne, upsert: vi.fn(), find: vi.fn() },
    } as never)

    const { result } = renderHook(() => useLessonNotes("lessonRxEmpty"))

    await waitFor(() => expect(result.current.note?.text).toBe("from IDB"))
    expect(idb.get).toHaveBeenCalledWith(KEY("lessonRxEmpty"))
  })

  it("does not publish an RxDB result after unmount", async () => {
    const database = deferred<{
      notes: { findOne: ReturnType<typeof vi.fn>; upsert: ReturnType<typeof vi.fn> }
    }>()
    const rxNote = { text: "late", updated_at: 42 }
    const findOne = vi.fn(() => ({ exec: vi.fn(async () => rxNote) }))
    dbState.getDatabase.mockImplementation(() => database.promise as never)

    const { unmount } = renderHook(() => useLessonNotes("late-rx"))
    unmount()
    database.resolve({ notes: { findOne, upsert: vi.fn() } })
    await act(async () => {
      await database.promise
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(idb.get).not.toHaveBeenCalled()
  })

  it("does not publish a late IndexedDB result or error after unmount", async () => {
    const stored = deferred<LessonNote | undefined>()
    dbState.getDatabase.mockRejectedValue(new Error("RxDB unavailable"))
    idb.get.mockImplementationOnce(() => stored.promise)

    const first = renderHook(() => useLessonNotes("late-idb"))
    await finishDeferredRead(
      () => waitFor(() => expect(idb.get).toHaveBeenCalledWith(KEY("late-idb"))),
      first.unmount,
      () =>
        act(async () => {
          stored.resolve({ text: "late", updatedAt: 1 })
          await stored.promise
        })
    )

    const failed = deferred<LessonNote | undefined>()
    idb.get.mockImplementationOnce(() => failed.promise)
    const second = renderHook(() => useLessonNotes("late-idb-error"))
    await finishDeferredRead(
      () => waitFor(() => expect(idb.get).toHaveBeenCalledWith(KEY("late-idb-error"))),
      second.unmount,
      () =>
        act(async () => {
          const failure = new Error("late failure")
          const settled = failed.promise.catch((error: unknown) => {
            if (error !== failure) throw error
          })
          failed.reject(failure)
          await settled
        })
    )
  })

  it("handles missing RxDB rows and IndexedDB deletion failures", async () => {
    vi.useFakeTimers()
    const findOne = vi.fn(() => ({ exec: vi.fn(async () => null) }))
    dbState.getDatabase.mockResolvedValue({
      notes: { findOne, upsert: vi.fn(), find: vi.fn() },
    } as never)
    idb.del.mockRejectedValue(new Error("delete unavailable"))

    const { result } = renderHook(() => useLessonNotes("missing-rx"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => result.current.setNote("   "))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
      await Promise.resolve()
    })
    act(() => result.current.clearNote())
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(findOne).toHaveBeenCalled()
    expect(logError).toHaveBeenCalledWith("[schedule:notes]", expect.any(Error))
  })

  it("removes RxDB records when clearing a note and marks mapped notes", async () => {
    const rxNote = {
      id: JSON.stringify(["user-a", "lessonMap"]),
      lesson_id: "lessonMap",
      text: "mapped",
      updated_at: 9,
      remove: vi.fn(),
    }
    const findOne = vi.fn(() => ({ exec: vi.fn(async () => rxNote) }))
    const find = vi.fn(() => ({ exec: vi.fn(async () => [rxNote]) }))
    dbState.getDatabase.mockResolvedValue({ notes: { findOne, find, upsert: vi.fn() } } as never)

    const { result } = renderHook(() => useLessonNotes("lessonMap"))
    await waitFor(() => expect(result.current.note?.text).toBe("mapped"))
    await act(async () => {
      result.current.clearNote()
      await Promise.resolve()
    })
    expect(rxNote.remove).toHaveBeenCalledTimes(1)

    vi.useFakeTimers()
    act(() => result.current.setNote("   "))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
    expect(rxNote.remove).toHaveBeenCalledTimes(2)
    vi.useRealTimers()

    const map = renderHook(() => useLessonNotesMap(["lessonMap", "missing"]))
    await waitFor(() => expect(map.result.current.size).toBe(2))
    expect(map.result.current.get("lessonMap")).toBe(true)
    expect(map.result.current.get("missing")).toBe(false)
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

  it("ignores blank RxDB notes and does not publish a map after unmount", async () => {
    const fallback = deferred<LessonNote | undefined>()
    const find = vi.fn(() => ({
      exec: vi.fn(async () => [{ id: "blank", text: "   " }]),
    }))
    dbState.getDatabase.mockResolvedValue({ notes: { find } } as never)
    idb.get.mockImplementationOnce(() => fallback.promise)

    const { unmount } = renderHook(() => useLessonNotesMap(["blank"]))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    unmount()
    fallback.resolve({ text: "from fallback", updatedAt: 1 })
    await act(async () => {
      await fallback.promise
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(find).toHaveBeenCalled()
  })
})

describe("deferred note storage ownership", () => {
  it("rolls back an RxDB save and discards queued work after account expiry", async () => {
    vi.useFakeTimers()
    const saved = deferred<{ remove: ReturnType<typeof vi.fn> }>()
    const remove = vi.fn(async () => undefined)
    const upsert = vi.fn(() => saved.promise)
    dbState.getDatabase.mockResolvedValue({
      notes: {
        findOne: () => ({ exec: async () => null }),
        upsert,
      },
    } as never)
    const { result } = renderHook(() => useLessonNotes("queued-rx"))
    await act(() => vi.advanceTimersByTimeAsync(0))
    act(() => result.current.setNote("old note"))
    await act(() => vi.advanceTimersByTimeAsync(300))
    expect(upsert).toHaveBeenCalledTimes(1)
    act(() => result.current.clearNote())
    act(() => useAuthStore.setState({ user: null }))
    await act(async () => {
      saved.resolve({ remove })
      await saved.promise
    })
    expect(remove).toHaveBeenCalledOnce()
    expect(idb.set).not.toHaveBeenCalled()
    expect(idb.del).not.toHaveBeenCalled()
  })

  it("does not write after a database opens for an expired session", async () => {
    vi.useFakeTimers()
    const opened = deferred<unknown>()
    const { result } = renderHook(() => useLessonNotes("delayed-open"))
    await act(() => vi.advanceTimersByTimeAsync(0))
    const upsert = vi.fn()
    dbState.getDatabase.mockImplementation(() => opened.promise as never)
    act(() => result.current.setNote("old note"))
    await act(() => vi.advanceTimersByTimeAsync(300))
    act(() => useAuthStore.setState({ user: null }))
    await act(async () => {
      opened.resolve({ notes: { upsert } })
      await opened.promise
    })
    expect(upsert).not.toHaveBeenCalled()
    expect(idb.set).not.toHaveBeenCalled()
  })

  it("does not publish a note when IndexedDB finishes after unmount", async () => {
    const stored = deferred<LessonNote | undefined>()
    idb.get.mockImplementationOnce(() => stored.promise)
    const { result, unmount } = renderHook(() => useLessonNotes("inflight-idb"))
    await waitFor(() => expect(idb.get).toHaveBeenCalledWith(KEY("inflight-idb")))
    unmount()
    await act(async () => {
      stored.resolve({ text: "private", updatedAt: 1 })
      await stored.promise
    })
    expect(result.current.note).toBeNull()
    expect(idb.set).not.toHaveBeenCalled()
  })

  it.each(["opening", "querying"] as const)(
    "does not publish note indicators after unmount while %s RxDB",
    async (phase) => {
      const pending = deferred<unknown>()
      const find = vi.fn(() => ({ exec: () => pending.promise }))
      dbState.getDatabase.mockImplementation(() =>
        phase === "opening"
          ? (pending.promise as never)
          : (Promise.resolve({ notes: { find } }) as never)
      )
      const { result, unmount } = renderHook(() => useLessonNotesMap(["private-map"]))
      await act(async () => {
        await Promise.resolve()
      })
      unmount()
      await act(async () => {
        pending.resolve(
          phase === "opening"
            ? { notes: { find } }
            : [{ lesson_id: "private-map", text: "private" }]
        )
        await pending.promise
      })
      expect(result.current.size).toBe(0)
      expect(idb.get).not.toHaveBeenCalled()
      if (phase === "opening") expect(find).not.toHaveBeenCalled()
    }
  )
})
