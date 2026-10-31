import { IDBFactory } from "fake-indexeddb"
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
  REPLAY_MAX_ATTEMPTS,
  REPLAY_REQUEST_TIMEOUT_MS,
} from "../replayPolicy"
import { warn } from "../logger"
import * as offline from "../offline"

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
