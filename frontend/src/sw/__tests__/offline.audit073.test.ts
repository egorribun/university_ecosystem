import "fake-indexeddb/auto"
import { IDBFactory, IDBObjectStore as FakeIDBObjectStore } from "fake-indexeddb"
import { webcrypto } from "node:crypto"
import { MessageChannel as WorkerMessageChannel } from "node:worker_threads"
import { openDB } from "idb"
import type * as IDBModule from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const raceState = vi.hoisted(() => ({
  queueSnapshotAction: null as null | "delete" | "change",
}))

vi.mock("idb", async (importOriginal) => {
  const actual = await importOriginal<typeof IDBModule>()
  return {
    ...actual,
    openDB: async (...args: Parameters<typeof actual.openDB>) => {
      const db = await actual.openDB(...args)
      return new Proxy(db, {
        get(target, property) {
          if (property === "getAll") {
            return async (
              storeName: string,
              query?: IDBValidKey | IDBKeyRange | null,
              count?: number
            ) => {
              const rows = await Reflect.get(target, property, target).apply(target, [
                storeName,
                query,
                count,
              ])
              const action = raceState.queueSnapshotAction
              if (action && storeName === STORES.MUTATION) {
                raceState.queueSnapshotAction = null
                const snapshot = rows[0] as Record<string, unknown> | undefined
                if (snapshot && action === "delete") {
                  await target.delete(storeName, snapshot.id as number)
                } else if (snapshot && action === "change") {
                  await target.put(storeName, {
                    ...snapshot,
                    url: "/api/v1/profile?changed-after-snapshot=1",
                  })
                }
              }
              return rows
            }
          }
          const value = Reflect.get(target, property, target)
          return typeof value === "function" ? value.bind(target) : value
        },
      })
    },
  }
})

import {
  initOfflineQueue,
  processOfflineQueues,
  readPendingMutations,
  storePendingMutation,
  STORES,
} from "@/sw/offline"
import { REPLAY_ACTIVE_ATTEMPT_KEY, REPLAY_LEASE_STORE } from "@/sw/replayLease"
import { REPLAY_LEASE_POLL_MS } from "@/sw/replayPolicy"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION,
} from "@/constants/notificationInteractionsDb"

const NOW = 1_800_000_000_000
const SESSION = "aud073-session"
const PROOF = { csrfToken: "aud073-csrf", sessionNonce: SESSION }
let now = NOW

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function stubWindow(
  postMessage = (_message: unknown, ports: MessagePort[]) => ports[0]?.postMessage(PROOF)
) {
  const client = { url: "http://localhost/", postMessage: vi.fn(postMessage) }
  vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue([client]) })
  return client
}

function queuedMutation() {
  return storePendingMutation({
    url: "/api/v1/profile",
    method: "PATCH",
    payload: { displayName: "Ada" },
    mutationId: "aud073-mutation-1",
    idempotencyKey: "aud073-op-1",
    timestamp: 1,
    sessionNonce: SESSION,
  })
}

async function openObserver() {
  return openDB(NOTIFICATION_INTERACTIONS_DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
}

describe("AUD-073 offline replay snapshot and attempt fences", () => {
  beforeEach(async () => {
    raceState.queueSnapshotAction = null
    now = NOW
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.stubGlobal("crypto", webcrypto)
    vi.stubGlobal("MessageChannel", WorkerMessageChannel)
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockImplementation(() => now)
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, "locks")
  })

  it("replays a matching queued mutation after credentials and attempt claim", async () => {
    stubWindow()
    await queuedMutation()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 } as Response)
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual([])
  })
  it("holds a snapshot when the queued row disappears before the atomic readiness read", async () => {
    const client = stubWindow()
    await queuedMutation()
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    raceState.queueSnapshotAction = "delete"

    await processOfflineQueues()

    expect(raceState.queueSnapshotAction).toBeNull()
    expect(client.postMessage).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([])
  })

  it("holds a stale snapshot when replay metadata changed before the atomic readiness read", async () => {
    const client = stubWindow()
    await queuedMutation()
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    raceState.queueSnapshotAction = "change"

    await processOfflineQueues()

    expect(raceState.queueSnapshotAction).toBeNull()
    expect(client.postMessage).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({
        mutationId: "aud073-mutation-1",
        url: "/api/v1/profile?changed-after-snapshot=1",
      }),
    ])
  })

  it("waits when an attempt marker appears during credential renewal, then retries after expiry", async () => {
    let messageCount = 0
    let externalMarker: Record<string, unknown> | undefined
    const markerWritten = deferred<void>()
    const waitScheduled = deferred<void>()
    const client = stubWindow((_message, ports) => {
      messageCount += 1
      if (messageCount !== 2) {
        ports[0]?.postMessage(PROOF)
        return
      }
      void (async () => {
        const db = await openObserver()
        externalMarker = {
          id: REPLAY_ACTIVE_ATTEMPT_KEY,
          owner: "takeover-worker",
          attemptId: "takeover-attempt",
          expiresAt: now + REPLAY_LEASE_POLL_MS,
        }
        await db.put(REPLAY_LEASE_STORE, externalMarker)
        db.close()
        markerWritten.resolve()
        ports[0]?.postMessage(PROOF)
      })()
    })
    await queuedMutation()
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchMock)
    const realSetTimeout = globalThis.setTimeout.bind(globalThis)
    vi.spyOn(globalThis, "setTimeout").mockImplementation((callback, delay, ...args) => {
      if (delay === REPLAY_LEASE_POLL_MS) waitScheduled.resolve()
      return realSetTimeout(callback, delay, ...args)
    })

    const pass = processOfflineQueues()
    await markerWritten.promise
    await waitScheduled.promise

    expect(externalMarker).toMatchObject({
      owner: "takeover-worker",
      attemptId: "takeover-attempt",
    })
    expect(fetchMock).not.toHaveBeenCalled()
    now += REPLAY_LEASE_POLL_MS + 1
    await pass

    expect(client.postMessage).toHaveBeenCalledTimes(3)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual([])
  })

  it("rethrows the original marker-write error after a failed IndexedDB claim transaction", async () => {
    stubWindow()
    await queuedMutation()
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const markerWriteError = new Error("AUD073 active marker write failed")
    const originalPut = FakeIDBObjectStore.prototype.put
    vi.spyOn(FakeIDBObjectStore.prototype, "put").mockImplementation(function (
      this: IDBObjectStore,
      ...args: Parameters<typeof FakeIDBObjectStore.prototype.put>
    ) {
      const [value] = args
      if (
        this.name === REPLAY_LEASE_STORE &&
        typeof value === "object" &&
        value !== null &&
        (value as { id?: unknown }).id === REPLAY_ACTIVE_ATTEMPT_KEY
      ) {
        this.transaction.abort()
        throw markerWriteError
      }
      return originalPut.apply(this, args)
    })

    await expect(processOfflineQueues()).rejects.toBe(markerWriteError)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toHaveLength(1)
  })

  it("does not commit a response or delete a successor's different attempt marker", async () => {
    stubWindow()
    await queuedMutation()
    const fetchEntered = deferred<void>()
    const response = deferred<Response>()
    const fetchMock = vi.fn(() => {
      fetchEntered.resolve()
      return response.promise
    })
    vi.stubGlobal("fetch", fetchMock)

    const pass = processOfflineQueues()
    await fetchEntered.promise
    const db = await openObserver()
    const original = await db.get(REPLAY_LEASE_STORE, REPLAY_ACTIVE_ATTEMPT_KEY)
    expect(original).toMatchObject({
      owner: expect.any(String),
      attemptId: expect.any(String),
    })
    const successor = {
      ...original,
      owner: "successor-worker",
      attemptId: "successor-attempt",
    }
    await db.put(REPLAY_LEASE_STORE, successor)
    response.resolve(new Response(null, { status: 204 }))
    await pass

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await db.get(REPLAY_LEASE_STORE, REPLAY_ACTIVE_ATTEMPT_KEY)).toEqual(successor)
    expect(await readPendingMutations()).toHaveLength(1)
    db.close()
  })
})
