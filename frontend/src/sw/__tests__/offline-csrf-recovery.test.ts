import { IDBFactory, IDBObjectStore as FakeIDBObjectStore } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  NOTIFICATION_INTERACTIONS_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION,
} from "@/constants/notificationInteractionsDb"
import {
  initOfflineQueue,
  processOfflineQueues,
  readPendingMutations,
  readPendingReports,
  storePendingMutation,
  storePendingReport,
  STORES,
} from "../offline"
import { REPLAY_ACTIVE_ATTEMPT_KEY, REPLAY_LEASE_KEY, REPLAY_LEASE_STORE } from "../replayLease"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

const SESSION = "session-a"
const INITIAL_CSRF = "csrf-before"
const FRESH_CSRF = "csrf-after"
const V2 = "REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2"

type CredentialMessage = { type: string; version?: number; sessionNonce?: string }

function installWindow(refresh: (message: CredentialMessage) => unknown | Promise<unknown>) {
  let currentToken = INITIAL_CSRF
  const postMessage = vi.fn((message: CredentialMessage, ports?: MessagePort[]) => {
    const port = ports?.[0]
    if (!port) return
    if (message.type === V2) {
      void Promise.resolve(refresh(message)).then((answer) => port.postMessage(answer))
    } else {
      port.postMessage({ csrfToken: currentToken, sessionNonce: SESSION })
    }
  })
  vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue([{ postMessage }]) })
  return {
    postMessage,
    useFreshToken: () => {
      currentToken = FRESH_CSRF
    },
  }
}

async function queueMutation(label = "operation-1") {
  await storePendingMutation({
    url: "/api/v1/profile",
    method: "PATCH",
    payload: { displayName: label === "operation-1" ? "queued" : label },
    mutationId: label,
    idempotencyKey: `idempotency-${label === "operation-1" ? "1" : label}`,
    timestamp: Date.now(),
    sessionNonce: SESSION,
  })
}

function markedDenial(
  url = new URL("/api/v1/profile", window.location.origin).href,
  redirected = false
) {
  const response = new Response(null, { status: 403, headers: { "X-CSRF-Rejected": "1" } })
  Object.defineProperties(response, { url: { value: url }, redirected: { value: redirected } })
  return response
}

function freshAnswer() {
  return { version: 2, csrfToken: FRESH_CSRF, sessionNonce: SESSION }
}

describe("offline replay after a marked CSRF rejection", () => {
  beforeEach(async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("replays the same queued write once using newly bootstrapped credentials", async () => {
    const client = installWindow(() => freshAnswer())
    await queueMutation()
    const attempts: Array<{
      method: string | undefined
      body: BodyInit | null | undefined
      csrf: string | null
      dedupe: string | null
    }> = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
        const headers = new Headers(init?.headers)
        attempts.push({
          method: init?.method,
          body: init?.body,
          csrf: headers.get("X-CSRF-Token"),
          dedupe: headers.get("Idempotency-Key"),
        })
        return attempts.length === 1 ? markedDenial() : new Response(null, { status: 204 })
      })
    )

    await processOfflineQueues()

    expect(attempts).toEqual([
      {
        method: "PATCH",
        body: '{"displayName":"queued"}',
        csrf: INITIAL_CSRF,
        dedupe: "idempotency-1",
      },
      {
        method: "PATCH",
        body: '{"displayName":"queued"}',
        csrf: FRESH_CSRF,
        dedupe: "idempotency-1",
      },
    ])
    expect(client.postMessage).toHaveBeenCalledWith(
      { type: V2, version: 2, sessionNonce: SESSION, expiresAt: expect.any(Number) },
      [expect.any(MessagePort)]
    )
    expect(await readPendingMutations()).toEqual([])
  })

  it("preserves the generated idempotency key and body when replaying a queued report", async () => {
    installWindow(() => freshAnswer())
    await storePendingReport({
      url: "/notifications",
      reportUrl: "/api/v1/profile",
      method: "POST",
      payload: { action: "open" },
      timestamp: Date.now(),
      sessionNonce: SESSION,
    })
    const [original] = await readPendingReports()
    const attempts: Array<{
      dedupe: string | null
      csrf: string | null
      body: BodyInit | null | undefined
    }> = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
        const headers = new Headers(init?.headers)
        attempts.push({
          dedupe: headers.get("Idempotency-Key"),
          csrf: headers.get("X-CSRF-Token"),
          body: init?.body,
        })
        return attempts.length === 1 ? markedDenial() : new Response(null, { status: 204 })
      })
    )

    await processOfflineQueues()

    expect(attempts).toEqual([
      { dedupe: original.idempotencyKey, csrf: INITIAL_CSRF, body: '{"action":"open"}' },
      { dedupe: original.idempotencyKey, csrf: FRESH_CSRF, body: '{"action":"open"}' },
    ])
    expect(await readPendingReports()).toEqual([])
  })

  it.each([
    ["a refusal", null],
    ["an old window's unversioned response", { csrfToken: FRESH_CSRF, sessionNonce: SESSION }],
    ["an incorrect version", { version: 1, csrfToken: FRESH_CSRF, sessionNonce: SESSION }],
    ["another session", { version: 2, csrfToken: FRESH_CSRF, sessionNonce: "session-b" }],
    ["the rejected token", { version: 2, csrfToken: INITIAL_CSRF, sessionNonce: SESSION }],
  ])("holds the unchanged row without consuming an attempt after %s", async (_name, answer) => {
    const client = installWindow(() => answer)
    await queueMutation()
    await queueMutation("second")
    const original = await readPendingMutations()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(markedDenial())
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual(original)
    client.useFreshToken()
    await processOfflineQueues()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(await readPendingMutations()).toEqual([])
  })

  it("holds the original record after a second marked denial and stops the pass", async () => {
    const client = installWindow(() => freshAnswer())
    await queueMutation()
    await queueMutation("second")
    const original = await readPendingMutations()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(markedDenial())
      .mockResolvedValueOnce(markedDenial())
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(client.postMessage.mock.calls.filter(([message]) => message.type === V2)).toHaveLength(1)
    expect(await readPendingMutations()).toEqual(original)
    client.useFreshToken()
    await processOfflineQueues()
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(await readPendingMutations()).toEqual([])
  })

  it.each([null, "0", "true", "01"])(
    "keeps ordinary 403 behavior for marker %s",
    async (marker) => {
      const client = installWindow(() => freshAnswer())
      await queueMutation()
      const headers = marker === null ? undefined : { "X-CSRF-Rejected": marker }
      const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403, headers }))
      vi.stubGlobal("fetch", fetchMock)

      await processOfflineQueues()

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(client.postMessage.mock.calls.filter(([message]) => message.type === V2)).toHaveLength(
        0
      )
      expect(await readPendingMutations()).toEqual([])
    }
  )

  it.each([
    ["redirected", new URL("/api/v1/profile", window.location.origin).href, true],
    ["a different endpoint", new URL("/api/v1/other", window.location.origin).href, false],
    ["another origin", "https://example.invalid/api/v1/profile", false],
    ["an unknown response URL", "", false],
  ])("does not treat a marked %s response as a safe replay", async (_name, url, redirected) => {
    const client = installWindow(() => freshAnswer())
    await queueMutation()
    const fetchMock = vi.fn().mockResolvedValue(markedDenial(url, redirected))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(client.postMessage.mock.calls.filter(([message]) => message.type === V2)).toHaveLength(0)
    expect(await readPendingMutations()).toEqual([])
  })

  it("keeps the existing network ambiguity policy after the one permitted retry", async () => {
    installWindow(() => freshAnswer())
    await queueMutation()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(markedDenial())
      .mockRejectedValueOnce(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({
        mutationId: "operation-1",
        retryCount: 1,
        nextAttemptAt: expect.any(Number),
      }),
    ])
  })

  it("retains the row after a refresh timeout and ignores a late acknowledgment", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    let release!: (answer: unknown) => void
    let notifyRequested!: () => void
    const requested = new Promise<void>((resolve) => {
      notifyRequested = resolve
    })
    installWindow(
      () =>
        new Promise((resolve) => {
          release = resolve
          notifyRequested()
        })
    )
    await queueMutation()
    const original = await readPendingMutations()
    const fetchMock = vi.fn().mockResolvedValue(markedDenial())
    vi.stubGlobal("fetch", fetchMock)

    const running = processOfflineQueues()
    await requested
    await vi.advanceTimersByTimeAsync(9_000)
    await running
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual(original)

    release(freshAnswer())
    await new Promise<void>((resolve) => setImmediate(resolve))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual(original)
  })

  it("holds the row if an acknowledgment runs after its deadline before the timer fires", async () => {
    let monotonicNow = performance.now()
    vi.spyOn(performance, "now").mockImplementation(() => monotonicNow)
    installWindow(() => {
      monotonicNow += 9_001
      return freshAnswer()
    })
    await queueMutation()
    const original = await readPendingMutations()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(markedDenial())
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual(original)
  })

  it("keeps the queued write if its refresh fence transaction aborts", async () => {
    let abortFence = false
    installWindow(() => {
      abortFence = true
      return freshAnswer()
    })
    await queueMutation()
    const original = await readPendingMutations()
    const get = FakeIDBObjectStore.prototype.get
    vi.spyOn(FakeIDBObjectStore.prototype, "get").mockImplementation(function (
      this: IDBObjectStore,
      key
    ) {
      const request = get.call(this, key)
      if (
        abortFence &&
        this.name === STORES.MUTATION &&
        this.transaction.objectStoreNames.contains(REPLAY_LEASE_STORE)
      ) {
        abortFence = false
        this.transaction.abort()
      }
      return request
    })
    const fetchMock = vi.fn().mockResolvedValue(markedDenial())
    vi.stubGlobal("fetch", fetchMock)

    await expect(processOfflineQueues()).rejects.toMatchObject({ name: "AbortError" })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await readPendingMutations()).toEqual(original)
  })

  it.each(["body", "session", "lease", "lease-expired", "attempt", "attempt-expired"])(
    "does not replay when the %s changes during forced refresh",
    async (changed) => {
      let release!: (answer: unknown) => void
      const client = installWindow(
        () =>
          new Promise((resolve) => {
            release = resolve
          })
      )
      await queueMutation()
      const [original] = await readPendingMutations()
      const fetchMock = vi.fn().mockResolvedValue(markedDenial())
      vi.stubGlobal("fetch", fetchMock)

      const running = processOfflineQueues()
      try {
        await vi.waitFor(() =>
          expect(client.postMessage.mock.calls.some(([message]) => message.type === V2)).toBe(true)
        )
        const db = await openDB(
          NOTIFICATION_INTERACTIONS_DB_NAME,
          NOTIFICATION_INTERACTIONS_DB_VERSION
        )
        try {
          if (changed === "body" || changed === "session") {
            await db.put(STORES.MUTATION, {
              ...original,
              ...(changed === "body"
                ? { payload: { displayName: "changed" } }
                : { sessionNonce: "session-b" }),
            })
          } else {
            const id = changed.startsWith("lease") ? REPLAY_LEASE_KEY : REPLAY_ACTIVE_ATTEMPT_KEY
            const existing = await db.get(REPLAY_LEASE_STORE, id)
            await db.put(REPLAY_LEASE_STORE, {
              ...existing,
              ...(changed === "lease" ? { owner: "other-worker" } : {}),
              ...(changed === "attempt" ? { attemptId: "another-attempt" } : {}),
              expiresAt: Date.now() + (changed.endsWith("expired") ? -1 : 60_000),
            })
          }
        } finally {
          db.close()
        }
      } finally {
        release(freshAnswer())
        await running
      }

      expect(fetchMock).toHaveBeenCalledTimes(1)
      const [remaining] = await readPendingMutations()
      expect(remaining.mutationId).toBe(original.mutationId)
      expect(remaining.retryCount).toBe(original.retryCount)
      if (changed === "body") expect(remaining.payload).toEqual({ displayName: "changed" })
      if (changed === "session") expect(remaining.sessionNonce).toBe("session-b")
      if (changed === "attempt") {
        const db = await openDB(
          NOTIFICATION_INTERACTIONS_DB_NAME,
          NOTIFICATION_INTERACTIONS_DB_VERSION
        )
        try {
          expect(await db.get(REPLAY_LEASE_STORE, REPLAY_ACTIVE_ATTEMPT_KEY)).toMatchObject({
            attemptId: "another-attempt",
          })
        } finally {
          db.close()
        }
      }
    }
  )
})
