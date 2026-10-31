import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  initOfflineQueue,
  processOfflineQueues,
  processPendingMutations,
  processPendingNavigations,
  processPendingReports,
  STORES,
} from "../offline"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))
vi.mock("idb", async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>()
  return {
    ...original,
    openDB: (...args: unknown[]) => {
      const override = (globalThis as Record<string, unknown>).__audit375_openDB__ as
        ((...values: unknown[]) => unknown) | undefined
      const open = original.openDB as (...values: unknown[]) => unknown
      return override ? override(...args) : open(...args)
    },
  }
})

const { openDB: realOpenDB } = await vi.importActual<typeof import("idb")>("idb")

/** Every trigger closes the connection it opened, so each one receives its own handle. */
function freshConnection() {
  return realOpenDB("notification-interactions", 4)
}

describe("AUD-375: overlapping worker queue triggers", () => {
  beforeEach(async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("serializes overlapping holds until the previous database open settles", async () => {
    const db = await openDB("notification-interactions", 4)
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    let openCount = 0
    const open = vi.fn(async () => {
      openCount += 1
      if (openCount === 1) await pending
      return freshConnection()
    })
    vi.stubGlobal("__audit375_openDB__", open)

    const first = processOfflineQueues()
    const second = processOfflineQueues()
    try {
      await vi.waitFor(() => expect(open).toHaveBeenCalledOnce())
      await new Promise((resolve) => setTimeout(resolve, 100))
      expect(open).toHaveBeenCalledOnce()
    } finally {
      release()
      await Promise.allSettled([first, second])
      db.close()
    }
    expect(open).toHaveBeenCalledTimes(2)
  })

  it("preserves a record added during a hold and runs the later trigger", async () => {
    const db = await openDB("notification-interactions", 4)
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    let openCount = 0
    const open = vi.fn(async () => {
      openCount += 1
      if (openCount === 1) await pending
      return freshConnection()
    })
    vi.stubGlobal("__audit375_openDB__", open)

    const first = processOfflineQueues()
    await vi.waitFor(() => expect(open).toHaveBeenCalledOnce())
    const record = { url: "/private", timestamp: 1 }
    await db.add(STORES.NAVIGATION, record)
    const second = processOfflineQueues()
    release()
    await Promise.all([first, second])

    expect(open).toHaveBeenCalledTimes(2)
    expect(await db.getAll(STORES.NAVIGATION)).toEqual([{ ...record, id: 1 }])
    db.close()
  })

  it("runs a later trigger after the first database open rejects", async () => {
    const open = vi
      .fn()
      .mockRejectedValueOnce(new Error("database unavailable"))
      .mockImplementation(() => freshConnection())
    vi.stubGlobal("__audit375_openDB__", open)

    const results = await Promise.allSettled([processOfflineQueues(), processOfflineQueues()])

    expect(results.map((result) => result.status)).toEqual(["rejected", "fulfilled"])
    expect(open).toHaveBeenCalledTimes(2)
  })

  it("serializes direct processors with the common hold", async () => {
    const db = await openDB("notification-interactions", 4)
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    let openCount = 0
    const open = vi.fn(async () => {
      openCount += 1
      if (openCount === 1) await pending
      return freshConnection()
    })
    vi.stubGlobal("__audit375_openDB__", open)

    const first = processPendingMutations()
    const second = processPendingNavigations()
    const third = processPendingReports()
    try {
      await vi.waitFor(() => expect(open).toHaveBeenCalledOnce())
      await new Promise((resolve) => setTimeout(resolve, 100))
      expect(open).toHaveBeenCalledOnce()
    } finally {
      release()
      await Promise.allSettled([first, second, third])
      db.close()
    }
    expect(open).toHaveBeenCalledTimes(3)
  })
})
