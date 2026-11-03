import {
  IDBDatabase as FakeIDBDatabase,
  IDBFactory,
  IDBObjectStore as FakeIDBObjectStore,
} from "fake-indexeddb"
import { openDB, type IDBPDatabase } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  addRecord,
  initOfflineQueue,
  processOfflineQueues,
  readPendingMutations,
  readPendingNavigations,
  readPendingReports,
  storePendingMutation,
  storePendingNavigation,
  storePendingReport,
  STORES,
} from "../offline"
import {
  OTHER_SESSION_RECORD_TTL_MS,
  REPLAY_LEASE_POLL_MS,
  REPLAY_LEASE_RENEW_MS,
  REPLAY_LEASE_TTL_MS,
  REPLAY_MAX_ATTEMPTS,
  REPLAY_REQUEST_TIMEOUT_MS,
} from "../replayPolicy"
import { warn } from "../logger"
import * as offline from "../offline"
import {
  claimReplayLease,
  releaseReplayLease,
  renewReplayLease,
  REPLAY_LEASE_KEY,
  REPLAY_LEASE_STORE,
} from "../replayLease"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME as REPLAY_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION as REPLAY_DB_VERSION,
} from "@/constants/notificationInteractionsDb"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

const NOW = 1_800_000_000_000
const SESSION = "session-A"
const CSRF = "csrf-token-A"
const LOCK_NAME = "ecosystem-offline-queue-replay"
const ORIGIN = window.location.origin

/** A controlled window that answers the replay-credential port with the given payload. */
function answeringWindow(answer: unknown = { csrfToken: CSRF, sessionNonce: SESSION }) {
  return {
    url: "http://localhost/",
    postMessage: vi.fn((_message: unknown, transfer: MessagePort[]) => {
      transfer[0]?.postMessage(answer)
    }),
  }
}

function stubWindows(windows: unknown[]) {
  vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue(windows) })
}

/** Mirrors the Web Locks request contract: callers of one name run strictly in sequence. */
function fakeLockManager() {
  const tails = new Map<string, Promise<unknown>>()
  return {
    request: vi.fn((name: string, _options: unknown, callback: () => unknown) => {
      const run = (tails.get(name) ?? Promise.resolve()).then(() => callback())
      tails.set(
        name,
        run.catch(() => undefined)
      )
      return run
    }),
  }
}

/** Loads a fresh module instance, which models a second worker with its own in-process chain. */
async function loadSecondWorker() {
  vi.resetModules()
  return import("../offline")
}

function okResponse(status = 204) {
  return new Response(null, { status })
}

function mutationRecord(overrides: Partial<Parameters<typeof storePendingMutation>[0]> = {}) {
  return {
    url: "/api/v1/profile",
    method: "PATCH" as const,
    payload: { displayName: "Ada" },
    mutationId: "m-1",
    idempotencyKey: "op-1",
    timestamp: 1,
    sessionNonce: SESSION,
    ...overrides,
  }
}

describe("AUD-375: session-bound records replay under the window's CSRF proof", () => {
  beforeEach(async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, "locks")
  })

  it("replays a bound mutation with the CSRF header, JSON body and idempotency key, then deletes it", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord())
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(`${ORIGIN}/api/v1/profile`, {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "X-CSRF-Token": CSRF,
        "Content-Type": "application/json",
        "Idempotency-Key": "op-1",
      },
      body: JSON.stringify({ displayName: "Ada" }),
      redirect: "manual",
      signal: expect.any(AbortSignal),
    })
    expect(await readPendingMutations()).toEqual([])
  })

  it("replays a bound report to its same-origin reportUrl and deletes it after a 2xx response", async () => {
    stubWindows([answeringWindow()])
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/notifications/report",
      timestamp: 2,
      payload: { notificationId: "n1" },
      sessionNonce: SESSION,
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse(200))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${ORIGIN}/api/v1/notifications/report`,
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": CSRF }),
        body: JSON.stringify({ notificationId: "n1" }),
      })
    )
    expect(await readPendingReports()).toEqual([])
  })

  it("sends GET and HEAD reports without a body, and omits the idempotency key when none was issued", async () => {
    stubWindows([answeringWindow()])
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/report/get",
      timestamp: 1,
      payload: { stale: true },
      method: "GET",
      sessionNonce: SESSION,
    })
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/report/put",
      timestamp: 2,
      payload: { read: true },
      method: "put",
      sessionNonce: SESSION,
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse(200))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenNthCalledWith(1, `${ORIGIN}/api/v1/report/get`, {
      method: "GET",
      headers: { Accept: "application/json", "X-CSRF-Token": CSRF },
      body: undefined,
      redirect: "manual",
      signal: expect.any(AbortSignal),
    })
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${ORIGIN}/api/v1/report/put`, {
      method: "PUT",
      headers: {
        Accept: "application/json",
        "X-CSRF-Token": CSRF,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ read: true }),
      redirect: "manual",
      signal: expect.any(AbortSignal),
    })
    expect(await readPendingReports()).toEqual([])
  })

  it("sends HEAD reports and payload-free DELETE mutations without a body", async () => {
    stubWindows([answeringWindow()])
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/report/head",
      timestamp: 1,
      payload: { probe: true },
      method: "HEAD",
      sessionNonce: SESSION,
    })
    await storePendingMutation(
      mutationRecord({
        url: "/api/v1/profile/avatar",
        method: "DELETE",
        payload: undefined,
        mutationId: "m-delete",
        idempotencyKey: "op-delete",
      })
    )
    const fetchMock = vi.fn().mockResolvedValue(okResponse(200))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledWith(`${ORIGIN}/api/v1/report/head`, {
      method: "HEAD",
      headers: { Accept: "application/json", "X-CSRF-Token": CSRF },
      body: undefined,
      redirect: "manual",
      signal: expect.any(AbortSignal),
    })
    expect(fetchMock).toHaveBeenCalledWith(`${ORIGIN}/api/v1/profile/avatar`, {
      method: "DELETE",
      headers: {
        Accept: "application/json",
        "X-CSRF-Token": CSRF,
        "Idempotency-Key": "op-delete",
      },
      body: undefined,
      redirect: "manual",
      signal: expect.any(AbortSignal),
    })
    expect(await readPendingReports()).toEqual([])
    expect(await readPendingMutations()).toEqual([])
  })

  it("never sends a bound record to another origin and dead-letters it", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(
      mutationRecord({ url: "https://evil.example/collect", mutationId: "m-x" })
    )
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([])
    expect(warn).toHaveBeenCalledWith(
      "Dead-lettered offline record",
      expect.objectContaining({ store: STORES.MUTATION, reason: "cross-origin" })
    )
  })

  it("dead-letters a URL that cannot be parsed as an origin", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord({ url: "http://[bad", mutationId: "m-bad" }))
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([])
    expect(warn).toHaveBeenCalledWith(
      "Dead-lettered offline record",
      expect.objectContaining({ reason: "cross-origin" })
    )
  })

  it("dead-letters a payload that cannot be serialized without stalling the queue", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord({ payload: { big: BigInt(1) }, mutationId: "m-big" }))
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([])
    expect(warn).toHaveBeenCalledWith(
      "Dead-lettered offline record",
      expect.objectContaining({ reason: "unserializable" })
    )
  })

  it.each([400, 403, 404, 409, 410, 422])(
    "deletes a bound record rejected with HTTP %s and logs a dead-letter entry",
    async (status) => {
      stubWindows([answeringWindow()])
      await storePendingMutation(mutationRecord())
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(status)))

      await processOfflineQueues()

      expect(await readPendingMutations()).toEqual([])
      expect(warn).toHaveBeenCalledWith(
        "Dead-lettered offline record",
        expect.objectContaining({ store: STORES.MUTATION, reason: `status-${status}` })
      )
    }
  )

  it.each([408, 425, 429, 500, 503])(
    "keeps a bound record after retryable HTTP %s and defers its next attempt",
    async (status) => {
      stubWindows([answeringWindow()])
      await storePendingMutation(mutationRecord())
      const fetchMock = vi.fn().mockResolvedValue(okResponse(status))
      vi.stubGlobal("fetch", fetchMock)

      await processOfflineQueues()

      expect(await readPendingMutations()).toEqual([
        expect.objectContaining({ retryCount: 1, nextAttemptAt: NOW + 500 }),
      ])
      expect(warn).not.toHaveBeenCalled()

      await processOfflineQueues()
      expect(fetchMock).toHaveBeenCalledOnce()

      vi.mocked(Date.now).mockReturnValue(NOW + 500)
      await processOfflineQueues()
      expect(fetchMock).toHaveBeenCalledTimes(2)
    }
  )

  it("keeps a bound report after a server failure, counting its first retry from zero", async () => {
    stubWindows([answeringWindow()])
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/notifications/report",
      timestamp: 1,
      payload: { notificationId: "n-retry" },
      sessionNonce: SESSION,
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(503)))

    await processOfflineQueues()

    expect(await readPendingReports()).toEqual([
      expect.objectContaining({ retryCount: 1, nextAttemptAt: NOW + 500 }),
    ])
  })

  it("keeps a bound record after a network failure and retries it later", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord())
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))

    await processOfflineQueues()

    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({ retryCount: 1, nextAttemptAt: NOW + 500 }),
    ])
    expect(warn).not.toHaveBeenCalled()
  })

  it("aborts a hung replay after the request timeout and keeps the record for a retry", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord())
    const fetchMock = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError"))
          )
        })
    )
    vi.stubGlobal("fetch", fetchMock)

    const flush = processOfflineQueues()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    await vi.advanceTimersByTimeAsync(REPLAY_REQUEST_TIMEOUT_MS)
    await flush

    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({ retryCount: 1, nextAttemptAt: NOW + 500 }),
    ])
  })

  it("dead-letters a record whose failure repeats until the attempt budget is spent", async () => {
    stubWindows([answeringWindow()])
    await addRecord(STORES.MUTATION, {
      mutationId: "m-exhausted",
      url: "/api/v1/profile",
      method: "PATCH",
      payload: {},
      idempotencyKey: "op-exhausted",
      timestamp: 1,
      retryCount: REPLAY_MAX_ATTEMPTS - 1,
      category: "general",
      sessionNonce: SESSION,
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(503)))

    await processOfflineQueues()

    expect(await readPendingMutations()).toEqual([])
    expect(warn).toHaveBeenCalledWith(
      "Dead-lettered offline record",
      expect.objectContaining({ store: STORES.MUTATION, reason: "retries-exhausted:status-503" })
    )
  })

  it("replays nothing when the answering window refuses or no window is controlled", async () => {
    await storePendingMutation(mutationRecord())
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    stubWindows([answeringWindow(null)])
    await processOfflineQueues()
    stubWindows([])
    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([expect.objectContaining({ mutationId: "m-1" })])
  })

  it("never replays another session's record and drops it only after the retention limit", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord({ mutationId: "m-a", idempotencyKey: "op-a" }))
    await storePendingMutation(
      mutationRecord({
        mutationId: "m-b",
        idempotencyKey: "op-b",
        timestamp: NOW - 1_000,
        sessionNonce: "session-B",
      })
    )
    await storePendingMutation(
      mutationRecord({
        mutationId: "m-c",
        idempotencyKey: "op-c",
        timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
        sessionNonce: "session-C",
      })
    )
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      headers: expect.objectContaining({ "Idempotency-Key": "op-a" }),
    })
    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({ mutationId: "m-b", sessionNonce: "session-B" }),
    ])
    expect(warn).toHaveBeenCalledExactlyOnceWith(
      "Dropped expired offline record from another browser session",
      expect.objectContaining({ store: STORES.MUTATION })
    )
  })

  it("holds navigation records without any network replay and expires only other sessions' entries", async () => {
    stubWindows([answeringWindow()])
    await storePendingNavigation({ url: "/target", timestamp: NOW, sessionNonce: SESSION })
    await storePendingNavigation({ url: "/old", timestamp: 1, sessionNonce: "session-old" })
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingNavigations()).toEqual([
      expect.objectContaining({ url: "/target", sessionNonce: SESSION }),
    ])
    expect(warn).toHaveBeenCalledWith(
      "Dropped expired offline record from another browser session",
      expect.objectContaining({ store: STORES.NAVIGATION })
    )
  })

  it("holds unbound records even when a live window answers the credential request", async () => {
    stubWindows([answeringWindow()])
    await storePendingMutation(mutationRecord({ sessionNonce: undefined }))
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "/api/v1/report",
      timestamp: 1,
      payload: {},
    })
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toHaveLength(1)
    expect(await readPendingReports()).toHaveLength(1)
  })

  it("serializes replay across two workers through navigator.locks so a record is sent once", async () => {
    const locks = fakeLockManager()
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true })
    stubWindows([answeringWindow()])
    const first = offline
    await first.storePendingMutation(
      mutationRecord({ mutationId: "m-lock", idempotencyKey: "op-lock" })
    )
    let inFlight = 0
    let maxInFlight = 0
    const fetchMock = vi.fn(async () => {
      inFlight += 1
      maxInFlight = Math.max(maxInFlight, inFlight)
      await new Promise((resolve) => setTimeout(resolve, 10))
      inFlight -= 1
      return okResponse()
    })
    vi.stubGlobal("fetch", fetchMock)
    const second = await loadSecondWorker()

    await Promise.all([first.processOfflineQueues(), second.processOfflineQueues()])

    expect(locks.request).toHaveBeenCalledWith(
      LOCK_NAME,
      { mode: "exclusive" },
      expect.any(Function)
    )
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(maxInFlight).toBe(1)
    expect(await first.readPendingMutations()).toEqual([])
  })

  it("replays under the in-process chain alone when Web Locks are unavailable", async () => {
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true })
    stubWindows([answeringWindow()])
    await storePendingMutation(
      mutationRecord({ mutationId: "m-nolock", idempotencyKey: "op-nolock" })
    )
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(await readPendingMutations()).toEqual([])
  })
})

/** Promise gates advance only the selected worker boundary, never wall-clock sleeps. */
function replayGate<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

/** Both modules execute their own replay chain against the same real IndexedDB factory. */
async function noLockWorkers() {
  const first = await loadSecondWorker()
  const firstCredentials = await import("../replayCredentials")
  const second = await loadSecondWorker()
  const secondCredentials = await import("../replayCredentials")
  const proof = { csrfToken: CSRF, sessionNonce: SESSION }
  const firstProof = vi.spyOn(firstCredentials, "requestReplayCredentials").mockResolvedValue(proof)
  vi.spyOn(secondCredentials, "requestReplayCredentials").mockResolvedValue(proof)
  await first.initOfflineQueue()
  expect(first.processOfflineQueues).not.toBe(second.processOfflineQueues)
  return { first, second, firstProof, proof }
}

async function withLeaseConnections(
  run: (first: IDBPDatabase, second: IDBPDatabase) => Promise<void>
): Promise<void> {
  await initOfflineQueue()
  const first = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
  const second = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
  try {
    await run(first, second)
  } finally {
    first.close()
    second.close()
  }
}

describe("AUD-375: IndexedDB lease takeover never revives a stale replay pass", () => {
  beforeEach(() => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true })
    // A frozen worker cannot run heartbeat or request-deadline callbacks. Advance only
    // Date.now below; IndexedDB tasks and controlled promise continuations remain real.
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, "locks")
  })

  it("does not resend a stale snapshot after a successor drains and releases", async () => {
    const { first, second, firstProof, proof } = await noLockWorkers()
    const paused = replayGate<void>()
    const resume = replayGate<typeof proof | null>()
    firstProof.mockResolvedValueOnce(proof).mockImplementationOnce(() => {
      paused.resolve(undefined)
      return resume.promise
    })
    await first.storePendingMutation(
      mutationRecord({ mutationId: "m-stale-snapshot", idempotencyKey: "op-stale-snapshot" })
    )
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)

    const firstPass = first.processOfflineQueues()
    try {
      await Promise.race([
        paused.promise,
        firstPass.then(() => {
          throw new Error("First replay settled before its per-record credential boundary")
        }),
      ])
      vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS + 1)
      await second.processOfflineQueues()
      const afterSecond = await first.readPendingMutations()
      resume.resolve(proof)
      await firstPass

      expect(afterSecond).toEqual([])
      expect(fetchMock).toHaveBeenCalledOnce()
      expect(fetchMock).toHaveBeenCalledWith(
        `${ORIGIN}/api/v1/profile`,
        expect.objectContaining({
          headers: expect.objectContaining({ "Idempotency-Key": "op-stale-snapshot" }),
        })
      )
      expect(await first.readPendingMutations()).toEqual([])
    } finally {
      resume.resolve(null)
      await firstPass
    }
  })

  it("does not resurrect a drained row after a stale request returns a retry", async () => {
    const { first, second } = await noLockWorkers()
    const entered = replayGate<void>()
    const response = replayGate<Response>()
    await first.storePendingMutation(
      mutationRecord({ mutationId: "m-stale-retry", idempotencyKey: "op-stale-retry" })
    )
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => {
        entered.resolve(undefined)
        return response.promise
      })
      .mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)

    const firstPass = first.processOfflineQueues()
    try {
      await Promise.race([
        entered.promise,
        firstPass.then(() => {
          throw new Error("First replay settled before its controlled request boundary")
        }),
      ])
      vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS + 1)
      await second.processOfflineQueues()
      const afterSecond = await first.readPendingMutations()
      response.resolve(okResponse(500))
      await firstPass

      expect(afterSecond).toEqual([])
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(fetchMock.mock.calls.every(([url]) => url === `${ORIGIN}/api/v1/profile`)).toBe(true)
      expect(await first.readPendingMutations()).toEqual([])
    } finally {
      response.resolve(okResponse())
      await firstPass
    }
  })

  it("keeps a healthy renewed owner exclusive until that owner releases", async () => {
    await withLeaseConnections(async (first, second) => {
      expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
      expect(await renewReplayLease(first, "owner-a", NOW + REPLAY_LEASE_TTL_MS - 1)).toBe(true)
      expect(await claimReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS)).toBe(false)
      await releaseReplayLease(first, "owner-a")
      expect(await claimReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS)).toBe(true)
    })
  })

  it("allows a new owner to claim an abandoned lease only after its expiry", async () => {
    await withLeaseConnections(async (first, second) => {
      expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
      expect(await claimReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS - 1)).toBe(false)
      expect(await claimReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS)).toBe(true)
    })
  })

  it("does not let an old owner release the lease that another worker took over", async () => {
    await withLeaseConnections(async (first, second) => {
      expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
      expect(await claimReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS)).toBe(true)
      await releaseReplayLease(first, "owner-a")
      expect(await claimReplayLease(first, "owner-c", NOW + REPLAY_LEASE_TTL_MS)).toBe(false)
      expect(await renewReplayLease(second, "owner-b", NOW + REPLAY_LEASE_TTL_MS + 1)).toBe(true)
      await releaseReplayLease(second, "owner-b")
      expect(await claimReplayLease(first, "owner-c", NOW + REPLAY_LEASE_TTL_MS + 1)).toBe(true)
    })
  })
})

/** Fresh worker modules keep production lease/queue code while controlling only external seams. */
async function fencedReplayWorker() {
  const worker = await loadSecondWorker()
  const credentials = await import("../replayCredentials")
  const lease = await import("../replayLease")
  const logger = await import("../logger")
  const messages = await import("../utils")
  const proof = { csrfToken: CSRF, sessionNonce: SESSION }
  const credentialsSpy = vi.spyOn(credentials, "requestReplayCredentials").mockResolvedValue(proof)
  const notices = vi.spyOn(messages, "broadcastMessage").mockResolvedValue(undefined)
  await worker.initOfflineQueue()
  return { worker, lease, logger, proof, credentialsSpy, notices }
}

describe("AUD-375: replay mutations are fenced by the shared live lease", () => {
  beforeEach(() => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true })
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, "locks")
  })

  it.each(["missing", "expired-self", "foreign-live", "foreign-expired", "released-successor"])(
    "never acquires a %s lease through renewal",
    async (state) => {
      await withLeaseConnections(async (first, second) => {
        let now = NOW + REPLAY_LEASE_TTL_MS
        if (state !== "missing") {
          expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
        }
        if (state.startsWith("foreign") || state === "released-successor") {
          expect(await claimReplayLease(second, "owner-b", now)).toBe(true)
          if (state === "foreign-expired") now += REPLAY_LEASE_TTL_MS
          if (state === "released-successor") await releaseReplayLease(second, "owner-b")
        }
        const before = await first.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
        expect(await renewReplayLease(first, "owner-a", now)).toBe(false)
        expect(await first.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual(before)
      })
    }
  )

  it("refuses renewal through a closed connection without changing its lease", async () => {
    await withLeaseConnections(async (first, second) => {
      expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
      const before = await second.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
      first.close()
      expect(await renewReplayLease(first, "owner-a", NOW)).toBe(false)
      expect(await second.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual(before)
    })
  })

  it.each(["claim", "renew"] as const)(
    "samples the %s clock after the lease read rather than before its IDB wait",
    async (operation) => {
      await withLeaseConnections(async (first, second) => {
        expect(await claimReplayLease(first, "owner-a", NOW)).toBe(true)
        let clock = NOW
        const get = FakeIDBObjectStore.prototype.get
        const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "get")
        operationSpy.mockImplementation(function (this: IDBObjectStore, key) {
          const request = get.call(this, key)
          if (this.name === REPLAY_LEASE_STORE) {
            request.addEventListener(
              "success",
              () => {
                clock = NOW + REPLAY_LEASE_TTL_MS
              },
              { once: true }
            )
          }
          return request
        })
        if (operation === "claim") {
          expect(await claimReplayLease(second, "owner-b", () => clock)).toBe(true)
          expect(await first.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual({
            id: REPLAY_LEASE_KEY,
            owner: "owner-b",
            expiresAt: NOW + 2 * REPLAY_LEASE_TTL_MS,
          })
        } else {
          expect(await renewReplayLease(first, "owner-a", () => clock)).toBe(false)
          expect(await first.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual({
            id: REPLAY_LEASE_KEY,
            owner: "owner-a",
            expiresAt: NOW + REPLAY_LEASE_TTL_MS,
          })
        }
      })
    }
  )

  it.each([true, false])(
    "shares one lease when native Web Locks are available to the first worker: %s",
    async (nativeFirst) => {
      const first = await fencedReplayWorker()
      const second = await fencedReplayWorker()
      const locks = fakeLockManager()
      Object.defineProperty(navigator, "locks", {
        value: nativeFirst ? locks : undefined,
        configurable: true,
      })
      await first.worker.storePendingMutation(mutationRecord())
      const entered = replayGate<void>()
      const response = replayGate<Response>()
      const fetchMock = vi
        .fn()
        .mockImplementationOnce(() => {
          entered.resolve(undefined)
          return response.promise
        })
        .mockResolvedValue(okResponse())
      vi.stubGlobal("fetch", fetchMock)
      const firstPass = first.worker.processOfflineQueues()
      let secondPass: Promise<void> | undefined
      try {
        await Promise.race([
          entered.promise,
          firstPass.then(() => {
            throw new Error("First worker settled before sending its held request")
          }),
        ])
        const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
        try {
          expect(await observer.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual({
            id: REPLAY_LEASE_KEY,
            owner: expect.any(String),
            expiresAt: NOW + REPLAY_LEASE_TTL_MS,
          })
        } finally {
          observer.close()
        }
        Object.defineProperty(navigator, "locks", {
          value: nativeFirst ? undefined : locks,
          configurable: true,
        })
        const acquisition = replayGate<boolean>()
        const claim = second.lease.claimReplayLease
        vi.spyOn(second.lease, "claimReplayLease").mockImplementation(async (...args) => {
          const result = await claim(...args)
          acquisition.resolve(result)
          return result
        })
        secondPass = second.worker.processOfflineQueues()
        expect(
          await Promise.race([acquisition.promise, secondPass.then(() => "bypassed-shared-lease")])
        ).toBe(false)
        expect(fetchMock).toHaveBeenCalledOnce()
        response.resolve(okResponse())
        await firstPass
        await vi.advanceTimersByTimeAsync(REPLAY_LEASE_POLL_MS)
        await secondPass
        expect(fetchMock).toHaveBeenCalledOnce()
        expect(locks.request).toHaveBeenCalledOnce()
        expect(await first.worker.readPendingMutations()).toEqual([])
      } finally {
        response.resolve(okResponse())
        await firstPass
        await vi.advanceTimersByTimeAsync(REPLAY_LEASE_POLL_MS)
        await secondPass
      }
    }
  )

  it("does not revive a pass after a heartbeat observed ownership loss", async () => {
    const first = await fencedReplayWorker()
    const paused = replayGate<void>()
    const resume = replayGate<typeof first.proof | null>()
    first.credentialsSpy.mockResolvedValueOnce(first.proof).mockImplementationOnce(() => {
      paused.resolve(undefined)
      return resume.promise
    })
    await first.worker.storePendingMutation(mutationRecord())
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)
    const pass = first.worker.processOfflineQueues()
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    try {
      await paused.promise
      const lease = await observer.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
      expect(lease).toBeDefined()
      await observer.delete(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
      const failed = replayGate<boolean>()
      const renew = first.lease.renewReplayLease
      vi.spyOn(first.lease, "renewReplayLease").mockImplementation(async (...args) => {
        const result = await renew(...args)
        failed.resolve(result)
        return result
      })
      await vi.advanceTimersByTimeAsync(REPLAY_LEASE_RENEW_MS)
      expect(await failed.promise).toBe(false)
      await observer.put(REPLAY_LEASE_STORE, lease)
      resume.resolve(first.proof)
      await pass
      expect(fetchMock).not.toHaveBeenCalled()
      expect(await first.worker.readPendingMutations()).toHaveLength(1)
    } finally {
      resume.resolve(null)
      await pass
      observer.close()
    }
  })

  it.each(["delivered", "rejected", "retry", "network", "exhausted"])(
    "does not apply a stale %s result or announce a false dead letter",
    async (outcome) => {
      const first = await fencedReplayWorker()
      const second = await fencedReplayWorker()
      await first.worker.storePendingMutation(
        mutationRecord({ retryCount: outcome === "exhausted" ? REPLAY_MAX_ATTEMPTS - 1 : 0 })
      )
      const entered = replayGate<void>()
      const response = replayGate<Response>()
      const fetchMock = vi
        .fn()
        .mockImplementationOnce(() => {
          entered.resolve(undefined)
          return response.promise
        })
        .mockResolvedValue(okResponse(outcome === "exhausted" ? 204 : 500))
      vi.stubGlobal("fetch", fetchMock)
      const pass = first.worker.processOfflineQueues()
      try {
        await Promise.race([
          entered.promise,
          pass.then(() => {
            throw new Error("First worker settled before its controlled fetch")
          }),
        ])
        vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS + 1)
        await second.worker.processOfflineQueues()
        const replacement = await first.worker.readPendingMutations()
        if (outcome === "exhausted") {
          expect(replacement).toEqual([])
        } else {
          expect(replacement).toEqual([
            expect.objectContaining({
              retryCount: 1,
              nextAttemptAt: NOW + REPLAY_LEASE_TTL_MS + 501,
            }),
          ])
        }
        const noticeCount = first.notices.mock.calls.length
        const warningCount = vi.mocked(first.logger.warn).mock.calls.length
        if (outcome === "network") {
          response.resolve(Promise.reject(new TypeError("Controlled network failure")))
        } else {
          response.resolve(
            okResponse(outcome === "delivered" ? 204 : outcome === "rejected" ? 403 : 500)
          )
        }
        await pass
        expect(fetchMock).toHaveBeenCalledTimes(2)
        expect(await first.worker.readPendingMutations()).toEqual(replacement)
        expect(first.notices).toHaveBeenCalledTimes(noticeCount)
        expect(first.logger.warn).toHaveBeenCalledTimes(warningCount)
      } finally {
        response.resolve(okResponse())
        await pass
      }
    }
  )

  it("fences expired-session cleanup after a queue-snapshot takeover", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingReport({
      url: "/page",
      reportUrl: "/api/v1/report",
      timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
      sessionNonce: "another-session",
    })
    const before = await first.worker.readPendingReports()
    const successor = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    let takeover: Promise<boolean> | undefined
    const getAll = FakeIDBObjectStore.prototype.getAll
    const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "getAll")
    operationSpy.mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = getAll.apply(this, args)
      if (this.name === STORES.REPORT && !takeover) {
        request.addEventListener(
          "success",
          () => {
            vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS)
            takeover = claimReplayLease(successor, "successor", Date.now())
          },
          { once: true }
        )
      }
      return request
    })
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    try {
      await first.worker.processOfflineQueues()
      expect(takeover).toBeDefined()
      expect(await takeover).toBe(true)
      expect(await first.worker.readPendingReports()).toEqual(before)
      expect(fetchMock).not.toHaveBeenCalled()
      expect(first.logger.warn).not.toHaveBeenCalled()
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      await takeover
      await releaseReplayLease(successor, "successor")
      successor.close()
    }
  })

  it.each(["identity", "retry-state", "removed", "session"])(
    "does not send a queue snapshot whose %s changed during credential renewal",
    async (change) => {
      const first = await fencedReplayWorker()
      await first.worker.storePendingMutation(mutationRecord())
      const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
      const [row] = await first.worker.readPendingMutations()
      first.credentialsSpy.mockResolvedValueOnce(first.proof).mockImplementationOnce(async () => {
        if (change === "removed") {
          await observer.delete(STORES.MUTATION, row.id)
        } else {
          await observer.put(
            STORES.MUTATION,
            change === "identity"
              ? { ...row, mutationId: "replacement", idempotencyKey: "replacement-key" }
              : change === "session"
                ? { ...row, sessionNonce: "other-session" }
                : { ...row, retryCount: 2, nextAttemptAt: NOW + 10_000 }
          )
        }
        return first.proof
      })
      const fetchMock = vi.fn().mockResolvedValue(okResponse())
      vi.stubGlobal("fetch", fetchMock)
      try {
        await first.worker.processOfflineQueues()
        expect(fetchMock).not.toHaveBeenCalled()
        expect(await first.worker.readPendingMutations()).toEqual(
          change === "removed"
            ? []
            : [
                change === "identity"
                  ? { ...row, mutationId: "replacement", idempotencyKey: "replacement-key" }
                  : change === "session"
                    ? { ...row, sessionNonce: "other-session" }
                    : { ...row, retryCount: 2, nextAttemptAt: NOW + 10_000 },
              ]
        )
        expect(first.notices).not.toHaveBeenCalled()
      } finally {
        observer.close()
      }
    }
  )

  it("replays the current stored payload after credential renewal without losing its identity", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const [row] = await first.worker.readPendingMutations()
    const payload = { revised: true }
    first.credentialsSpy.mockResolvedValueOnce(first.proof).mockImplementationOnce(async () => {
      await observer.put(STORES.MUTATION, { ...row, payload })
      return first.proof
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse(500))
    vi.stubGlobal("fetch", fetchMock)
    try {
      await first.worker.processOfflineQueues()
      expect(fetchMock).toHaveBeenCalledOnce()
      expect(fetchMock).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: JSON.stringify(payload),
          headers: expect.objectContaining({
            "X-CSRF-Token": CSRF,
            "Idempotency-Key": row.idempotencyKey,
          }),
        })
      )
      expect(await first.worker.readPendingMutations()).toEqual([
        { ...row, payload, retryCount: 1, nextAttemptAt: NOW + 500 },
      ])
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      observer.close()
    }
  })

  it.each(["identity", "retry-state", "removed"])(
    "does not replace a queue row whose %s changed while its request was pending",
    async (change) => {
      const first = await fencedReplayWorker()
      await first.worker.storePendingMutation(mutationRecord())
      const entered = replayGate<void>()
      const response = replayGate<Response>()
      vi.stubGlobal(
        "fetch",
        vi.fn(() => {
          entered.resolve(undefined)
          return response.promise
        })
      )
      const pass = first.worker.processOfflineQueues()
      const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
      try {
        await entered.promise
        const [row] = await first.worker.readPendingMutations()
        if (change === "removed") {
          await observer.delete(STORES.MUTATION, row.id)
        } else {
          await observer.put(
            STORES.MUTATION,
            change === "identity"
              ? { ...row, mutationId: "replacement", idempotencyKey: "replacement-key" }
              : { ...row, retryCount: 2, nextAttemptAt: NOW + 10_000 }
          )
        }
        const replacement = await first.worker.readPendingMutations()
        response.resolve(okResponse(change === "removed" ? 500 : 204))
        await pass
        expect(await first.worker.readPendingMutations()).toEqual(replacement)
        expect(first.notices).not.toHaveBeenCalled()
      } finally {
        response.resolve(okResponse())
        await pass
        observer.close()
      }
    }
  )

  it("preserves unrelated latest-row metadata on an owned retry", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const entered = replayGate<void>()
    const response = replayGate<Response>()
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        entered.resolve(undefined)
        return response.promise
      })
    )
    const pass = first.worker.processOfflineQueues()
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    try {
      await entered.promise
      const [row] = await first.worker.readPendingMutations()
      await observer.put(STORES.MUTATION, { ...row, retainedMetadata: "keep" })
      response.resolve(okResponse(500))
      await pass
      expect(await first.worker.readPendingMutations()).toEqual([
        { ...row, retainedMetadata: "keep", retryCount: 1, nextAttemptAt: NOW + 500 },
      ])
    } finally {
      response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("keeps takeover outside the transaction that authorizes and updates a queue row", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const successor = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    let takeover: Promise<boolean> | undefined
    let takeoverFinished = false
    let mutationCommitted = false
    let takeoverBeforeCommit = false
    let takeoverAtWriteSuccess: boolean | undefined
    let mutationStores: string[] = []
    const put = FakeIDBObjectStore.prototype.put
    const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "put")
    operationSpy.mockImplementation(function (this: IDBObjectStore, ...args) {
      if (this.name !== STORES.MUTATION) return put.apply(this, args)
      mutationStores = Array.from(this.transaction.objectStoreNames)
      this.transaction.addEventListener(
        "complete",
        () => {
          mutationCommitted = true
        },
        { once: true }
      )
      vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS)
      takeover = claimReplayLease(successor, "successor", Date.now).then((held) => {
        takeoverFinished = true
        takeoverBeforeCommit = !mutationCommitted
        return held
      })
      const request = put.apply(this, args)
      request.addEventListener(
        "success",
        () => {
          takeoverAtWriteSuccess = takeoverFinished
        },
        { once: true }
      )
      return request
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(500)))
    try {
      await first.worker.processOfflineQueues()
      expect(takeover).toBeDefined()
      expect(await takeover).toBe(true)
      expect(mutationStores.sort()).toEqual([STORES.MUTATION, REPLAY_LEASE_STORE].sort())
      expect(mutationCommitted).toBe(true)
      expect(takeoverAtWriteSuccess).toBe(false)
      expect(takeoverBeforeCommit).toBe(false)
      expect(await first.worker.readPendingMutations()).toEqual([
        expect.objectContaining({ retryCount: 1, nextAttemptAt: NOW + 500 }),
      ])
      expect(await successor.get(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)).toEqual({
        id: REPLAY_LEASE_KEY,
        owner: "successor",
        expiresAt: NOW + 2 * REPLAY_LEASE_TTL_MS,
      })
    } finally {
      await takeover
      await releaseReplayLease(successor, "successor")
      successor.close()
    }
  })

  it("checks current expiry after reading the row inside its mutation transaction", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const before = await first.worker.readPendingMutations()
    let observed = false
    let fetchEntered = false
    const get = FakeIDBObjectStore.prototype.get
    const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "get")
    operationSpy.mockImplementation(function (this: IDBObjectStore, key) {
      const request = get.call(this, key)
      if (
        fetchEntered &&
        this.name === STORES.MUTATION &&
        this.transaction.objectStoreNames.contains(REPLAY_LEASE_STORE)
      ) {
        request.addEventListener(
          "success",
          () => {
            observed = true
            vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS)
          },
          { once: true }
        )
      }
      return request
    })
    const fetchMock = vi.fn(async () => {
      fetchEntered = true
      return okResponse(500)
    })
    vi.stubGlobal("fetch", fetchMock)
    await first.worker.processOfflineQueues()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(observed).toBe(true)
    expect(await first.worker.readPendingMutations()).toEqual(before)
    expect(first.notices).not.toHaveBeenCalled()
  })

  it("refuses to send when the lease expires during the pre-send row read", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const before = await first.worker.readPendingMutations()
    let observed = false
    const get = FakeIDBObjectStore.prototype.get
    const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "get")
    operationSpy.mockImplementation(function (this: IDBObjectStore, key) {
      const request = get.call(this, key)
      if (
        this.name === STORES.MUTATION &&
        this.transaction.objectStoreNames.contains(REPLAY_LEASE_STORE)
      ) {
        request.addEventListener(
          "success",
          () => {
            observed = true
            vi.mocked(Date.now).mockReturnValue(NOW + REPLAY_LEASE_TTL_MS)
          },
          { once: true }
        )
      }
      return request
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse(500))
    vi.stubGlobal("fetch", fetchMock)
    await first.worker.processOfflineQueues()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(observed).toBe(true)
    expect(await first.worker.readPendingMutations()).toEqual(before)
    expect(first.notices).not.toHaveBeenCalled()
  })

  it.each(["missing", "foreign"])(
    "refuses to send if a renewed lease becomes %s before the pre-send fence",
    async (state) => {
      const first = await fencedReplayWorker()
      await first.worker.storePendingMutation(mutationRecord())
      const before = await first.worker.readPendingMutations()
      const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
      const renew = first.lease.renewReplayLease
      const renewal = vi
        .spyOn(first.lease, "renewReplayLease")
        .mockImplementation(async (...args) => {
          const held = await renew(...args)
          expect(held).toBe(true)
          if (state === "missing") {
            await observer.delete(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
          } else {
            await observer.put(REPLAY_LEASE_STORE, {
              id: REPLAY_LEASE_KEY,
              owner: "successor",
              expiresAt: NOW + REPLAY_LEASE_TTL_MS,
            })
          }
          return held
        })
      const fetchMock = vi.fn().mockResolvedValue(okResponse())
      vi.stubGlobal("fetch", fetchMock)
      try {
        await first.worker.processOfflineQueues()
        expect(renewal).toHaveBeenCalledOnce()
        expect(fetchMock).not.toHaveBeenCalled()
        expect(await first.worker.readPendingMutations()).toEqual(before)
        expect(first.notices).not.toHaveBeenCalled()
      } finally {
        observer.close()
      }
    }
  )

  it("propagates an aborted pre-send fence without sending or changing the queue", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const before = await first.worker.readPendingMutations()
    const get = FakeIDBObjectStore.prototype.get
    vi.spyOn(FakeIDBObjectStore.prototype, "get").mockImplementation(function (
      this: IDBObjectStore,
      key
    ) {
      const request = get.call(this, key)
      if (
        this.name === STORES.MUTATION &&
        this.transaction.objectStoreNames.contains(REPLAY_LEASE_STORE)
      ) {
        this.transaction.abort()
      }
      return request
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)
    await expect(first.worker.processOfflineQueues()).rejects.toMatchObject({ name: "AbortError" })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await first.worker.readPendingMutations()).toEqual(before)
    expect(first.notices).not.toHaveBeenCalled()
  })

  it("propagates a failed queue commit without deletion or a false notice", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const before = await first.worker.readPendingMutations()
    const remove = FakeIDBObjectStore.prototype.delete
    const operationSpy = vi.spyOn(FakeIDBObjectStore.prototype, "delete")
    operationSpy.mockImplementation(function (this: IDBObjectStore, key) {
      const request = remove.call(this, key)
      if (this.name === STORES.MUTATION) this.transaction.abort()
      return request
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(403)))
    await expect(first.worker.processOfflineQueues()).rejects.toMatchObject({ name: "AbortError" })
    expect(await first.worker.readPendingMutations()).toEqual(before)
    expect(first.logger.warn).not.toHaveBeenCalled()
    expect(first.notices).not.toHaveBeenCalled()
  })

  it("announces a real dead letter only after its deletion is committed", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    let observedMessage: unknown
    let rowsAtNotice: unknown
    first.notices.mockImplementation(async (message) => {
      observedMessage = message
      rowsAtNotice = await first.worker.readPendingMutations()
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(403)))
    await first.worker.processOfflineQueues()
    expect(first.notices).toHaveBeenCalledOnce()
    expect(observedMessage).toEqual({
      type: "offline-dead-letter",
      store: STORES.MUTATION,
      reason: "status-403",
    })
    expect(rowsAtNotice).toEqual([])
    expect(first.logger.warn).toHaveBeenCalledOnce()
    expect(await first.worker.readPendingMutations()).toEqual([])
  })
})

/** Holds the first replay request open until the test settles it, so a row can change mid-flight. */
function gateFirstRequest() {
  const entered = replayGate<void>()
  const response = replayGate<Response>()
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() => {
      entered.resolve(undefined)
      return response.promise
    })
    .mockResolvedValue(okResponse())
  vi.stubGlobal("fetch", fetchMock)
  return { entered, response, fetchMock }
}

describe("AUD-375: replay commits never delete a row that changed while its request was pending", () => {
  beforeEach(() => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true })
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, "locks")
  })

  it("keeps a row whose payload was rewritten during a delivered request and sends the rewrite next", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const gate = gateFirstRequest()
    const pass = first.worker.processOfflineQueues()
    try {
      await gate.entered.promise
      const [row] = await first.worker.readPendingMutations()
      const rewritten = { ...row, payload: { displayName: "Grace" } }
      await observer.put(STORES.MUTATION, rewritten)
      gate.response.resolve(okResponse())
      await pass

      expect(await first.worker.readPendingMutations()).toEqual([rewritten])
      expect(first.notices).not.toHaveBeenCalled()

      await first.worker.processOfflineQueues()
      expect(gate.fetchMock).toHaveBeenCalledTimes(2)
      expect(gate.fetchMock).toHaveBeenNthCalledWith(
        2,
        `${ORIGIN}/api/v1/profile`,
        expect.objectContaining({
          body: JSON.stringify({ displayName: "Grace" }),
          headers: expect.objectContaining({ "Idempotency-Key": "op-1" }),
        })
      )
      expect(await first.worker.readPendingMutations()).toEqual([])
    } finally {
      gate.response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("keeps a row whose payload was rewritten during a retryable failure without counting that failure", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const gate = gateFirstRequest()
    const pass = first.worker.processOfflineQueues()
    try {
      await gate.entered.promise
      const [row] = await first.worker.readPendingMutations()
      const rewritten = { ...row, payload: { displayName: "Grace" } }
      await observer.put(STORES.MUTATION, rewritten)
      gate.response.resolve(okResponse(503))
      await pass

      expect(await first.worker.readPendingMutations()).toEqual([rewritten])
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      gate.response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("skips a row whose identity changed during its request and still replays the next row", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-a", idempotencyKey: "op-a" })
    )
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-b", idempotencyKey: "op-b" })
    )
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const gate = gateFirstRequest()
    const pass = first.worker.processOfflineQueues()
    try {
      await gate.entered.promise
      const [rowA] = await first.worker.readPendingMutations()
      await observer.put(STORES.MUTATION, {
        ...rowA,
        mutationId: "replacement",
        idempotencyKey: "replacement-key",
      })
      gate.response.resolve(okResponse())
      await pass

      expect(gate.fetchMock).toHaveBeenCalledTimes(2)
      expect(gate.fetchMock).toHaveBeenNthCalledWith(
        2,
        `${ORIGIN}/api/v1/profile`,
        expect.objectContaining({
          headers: expect.objectContaining({ "Idempotency-Key": "op-b" }),
        })
      )
      expect(await first.worker.readPendingMutations()).toEqual([
        expect.objectContaining({ mutationId: "replacement", idempotencyKey: "replacement-key" }),
      ])
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      gate.response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("skips a row replaced during credential renewal and still replays the next row", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-a", idempotencyKey: "op-a" })
    )
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-b", idempotencyKey: "op-b" })
    )
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const [rowA] = await first.worker.readPendingMutations()
    first.credentialsSpy.mockResolvedValueOnce(first.proof).mockImplementationOnce(async () => {
      await observer.put(STORES.MUTATION, {
        ...rowA,
        mutationId: "replacement",
        idempotencyKey: "replacement-key",
      })
      return first.proof
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)
    try {
      await first.worker.processOfflineQueues()

      expect(fetchMock).toHaveBeenCalledOnce()
      expect(fetchMock).toHaveBeenCalledWith(
        `${ORIGIN}/api/v1/profile`,
        expect.objectContaining({
          headers: expect.objectContaining({ "Idempotency-Key": "op-b" }),
        })
      )
      expect(await first.worker.readPendingMutations()).toEqual([
        expect.objectContaining({ mutationId: "replacement", idempotencyKey: "replacement-key" }),
      ])
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      observer.close()
    }
  })

  it("stops the pass without deleting or sending further rows when the lease is lost during a request", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-a", idempotencyKey: "op-a" })
    )
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-b", idempotencyKey: "op-b" })
    )
    const before = await first.worker.readPendingMutations()
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const gate = gateFirstRequest()
    const pass = first.worker.processOfflineQueues()
    try {
      await gate.entered.promise
      await observer.delete(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
      gate.response.resolve(okResponse())
      await pass

      expect(gate.fetchMock).toHaveBeenCalledOnce()
      expect(await first.worker.readPendingMutations()).toEqual(before)
      expect(first.notices).not.toHaveBeenCalled()
    } finally {
      gate.response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("sends nothing and stops when the lease is lost at the pre-send credential check", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-a", idempotencyKey: "op-a" })
    )
    await first.worker.storePendingMutation(
      mutationRecord({ mutationId: "m-b", idempotencyKey: "op-b" })
    )
    const before = await first.worker.readPendingMutations()
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    first.credentialsSpy.mockResolvedValueOnce(first.proof).mockImplementationOnce(async () => {
      await observer.delete(REPLAY_LEASE_STORE, REPLAY_LEASE_KEY)
      return first.proof
    })
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal("fetch", fetchMock)
    try {
      await first.worker.processOfflineQueues()

      expect(fetchMock).not.toHaveBeenCalled()
      expect(await first.worker.readPendingMutations()).toEqual(before)
    } finally {
      observer.close()
    }
  })

  it("fences the pre-send row read in a readonly transaction", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const transaction = vi.spyOn(FakeIDBDatabase.prototype, "transaction")
    let fenceAtSend: unknown[] | undefined
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        fenceAtSend = transaction.mock.calls.at(-1)?.slice(0, 2)
        return okResponse()
      })
    )

    await first.worker.processOfflineQueues()

    expect(fenceAtSend).toEqual([[REPLAY_LEASE_STORE, STORES.MUTATION], "readonly"])
    expect(await first.worker.readPendingMutations()).toEqual([])
  })

  it("keeps a row rewritten during a rejected request, so the rejection never dead-letters the new payload", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(mutationRecord())
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    const gate = gateFirstRequest()
    const pass = first.worker.processOfflineQueues()
    try {
      await gate.entered.promise
      const [row] = await first.worker.readPendingMutations()
      const rewritten = { ...row, payload: { displayName: "Grace" } }
      await observer.put(STORES.MUTATION, rewritten)
      gate.response.resolve(okResponse(403))
      await pass

      expect(await first.worker.readPendingMutations()).toEqual([rewritten])
      expect(first.notices).not.toHaveBeenCalled()
      expect(first.logger.warn).not.toHaveBeenCalled()
    } finally {
      gate.response.resolve(okResponse())
      await pass
      observer.close()
    }
  })

  it("keeps an expired other-session row rewritten before its drop, then drops it on a later pass", async () => {
    const first = await fencedReplayWorker()
    await first.worker.storePendingMutation(
      mutationRecord({ sessionNonce: "session-old", timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS })
    )
    const observer = await openDB(REPLAY_DB_NAME, REPLAY_DB_VERSION)
    let rewrite: Promise<unknown> | undefined
    const getAll = FakeIDBObjectStore.prototype.getAll
    vi.spyOn(FakeIDBObjectStore.prototype, "getAll").mockImplementation(function (
      this: IDBObjectStore,
      ...args
    ) {
      const request = getAll.apply(this, args)
      if (this.name === STORES.MUTATION && !rewrite) {
        // Queued while the snapshot is delivered, so it commits before the drop's transaction.
        request.addEventListener(
          "success",
          () => {
            const [snapshot] = request.result as object[]
            rewrite = observer.put(STORES.MUTATION, {
              ...snapshot,
              payload: { rewritten: true },
            })
          },
          { once: true }
        )
      }
      return request
    })

    try {
      await first.worker.processOfflineQueues()
      await rewrite

      expect(await first.worker.readPendingMutations()).toEqual([
        expect.objectContaining({ payload: { rewritten: true } }),
      ])
      expect(first.logger.warn).not.toHaveBeenCalled()

      await first.worker.processOfflineQueues()

      expect(await first.worker.readPendingMutations()).toEqual([])
      expect(first.logger.warn).toHaveBeenCalledExactlyOnceWith(
        "Dropped expired offline record from another browser session",
        expect.objectContaining({ store: STORES.MUTATION })
      )
    } finally {
      observer.close()
    }
  })
})
