import { IDBFactory, IDBObjectStore as FakeIDBObjectStore } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  discardSessionRecords,
  initOfflineQueue,
  readPendingMutations,
  storePendingMutation,
} from "../offline"
import { REPLAY_LEASE_TTL_MS } from "../replayPolicy"
import { REPLAY_LEASE_STORE } from "../replayLease"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

const NOW = 1_800_000_000_000
const SESSION = "session-A"

const mutation = (id: string) => ({
  url: `/api/v1/profile/${id}`,
  method: "PATCH" as const,
  payload: { id },
  mutationId: `m-${id}`,
  idempotencyKey: `k-${id}`,
  timestamp: 1,
  sessionNonce: SESSION,
})

describe("discardSessionRecords keeps the replay lease contract", () => {
  beforeEach(async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("stops without deleting anything when its lease expires during the discard", async () => {
    await storePendingMutation(mutation("1"))
    await storePendingMutation(mutation("2"))
    const getAll = FakeIDBObjectStore.prototype.getAll
    vi.spyOn(FakeIDBObjectStore.prototype, "getAll").mockImplementation(function (
      this: IDBObjectStore,
      ...args: Parameters<typeof getAll>
    ) {
      // The discard snapshot is taken under a live lease; the lease then expires.
      vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS + 1)
      return getAll.apply(this, args)
    })

    const get = FakeIDBObjectStore.prototype.get
    let queueReads = 0
    vi.spyOn(FakeIDBObjectStore.prototype, "get").mockImplementation(function (
      this: IDBObjectStore,
      key: Parameters<typeof get>[0]
    ) {
      // Each delete attempt re-reads its queued record once, after the lease check.
      if (this.name !== REPLAY_LEASE_STORE) queueReads += 1
      return get.call(this, key)
    })

    expect(await discardSessionRecords(SESSION)).toBe(0)
    // The first lost-lease result ends the discard; the second record is not attempted.
    expect(queueReads).toBe(1)

    vi.mocked(FakeIDBObjectStore.prototype.getAll).mockRestore()
    vi.mocked(FakeIDBObjectStore.prototype.get).mockRestore()
    expect(await readPendingMutations()).toHaveLength(2)
  })

  it("does not count a record that disappeared before its delete committed", async () => {
    await storePendingMutation(mutation("1"))
    const get = FakeIDBObjectStore.prototype.get
    vi.spyOn(FakeIDBObjectStore.prototype, "get").mockImplementation(function (
      this: IDBObjectStore,
      key: Parameters<typeof get>[0]
    ) {
      // Leave the lease read intact; the queued record is gone when the delete commits.
      return get.call(this, this.name === REPLAY_LEASE_STORE ? key : "no-such-record")
    })

    expect(await discardSessionRecords(SESSION)).toBe(0)

    vi.mocked(FakeIDBObjectStore.prototype.get).mockRestore()
    expect(await readPendingMutations()).toHaveLength(1)
  })
})
