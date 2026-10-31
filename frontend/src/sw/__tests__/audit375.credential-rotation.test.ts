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
import { OTHER_SESSION_RECORD_TTL_MS } from "../replayPolicy"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

const NOW = 1_800_000_000_000
const SESSION = "session-A"
const CSRF = "csrf-before-step-up"
const ROTATED_CSRF = "csrf-after-step-up"
const LOCK_NAME = "ecosystem-offline-queue-replay"

type Proof = {
  sessionNonce: string
  csrfToken: string
}

type Attempt = {
  idempotencyKey: string | null
  csrfToken: string | null
}

function stubWindow(proof: Proof) {
  const postMessage = vi.fn((_message: unknown, ports: MessagePort[]) => {
    ports[0]?.postMessage({ ...proof })
  })
  vi.stubGlobal("clients", {
    matchAll: vi.fn().mockResolvedValue([
      {
        url: `${window.location.origin}/`,
        postMessage,
      },
    ]),
  })
  return postMessage
}

/** Preserve the production lock's asynchronous callback lifetime in this test double. */
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

function mutation(id: string) {
  return {
    url: "/api/v1/profile",
    method: "PATCH" as const,
    payload: { displayName: id },
    mutationId: id,
    idempotencyKey: `op-${id}`,
    timestamp: NOW,
    sessionNonce: SESSION,
  }
}

async function startDelayedBatch() {
  const proof: Proof = { sessionNonce: SESSION, csrfToken: CSRF }
  let cookieToken = CSRF
  stubWindow(proof)

  await storePendingMutation(mutation("first"))
  await storePendingMutation(mutation("second"))
  const original = await readPendingMutations()
  expect(original.map((record) => record.mutationId)).toEqual(["first", "second"])

  let releaseFirst!: () => void
  const firstResponseGate = new Promise<void>((resolve) => {
    releaseFirst = resolve
  })
  const attempts: Attempt[] = []

  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers)
      const attempt = {
        idempotencyKey: headers.get("Idempotency-Key"),
        csrfToken: headers.get("X-CSRF-Token"),
      }
      attempts.push(attempt)

      // Validate at admission: the first write precedes rotation; only its
      // response is delayed. Subsequent requests use the current cookie.
      const response = new Response(null, {
        status: attempt.csrfToken === cookieToken ? 204 : 403,
      })
      if (attempt.idempotencyKey === "op-first") {
        await firstResponseGate
      }
      return response
    })
  )

  const pass = processOfflineQueues()
  return {
    attempts,
    second: original[1],
    pass,
    releaseFirst,
    rotate(next: Proof) {
      Object.assign(proof, next)
      cookieToken = next.csrfToken
    },
  }
}

describe("AUD-375: replay credentials remain current between queued writes", () => {
  let originalLocksDescriptor: PropertyDescriptor | undefined

  beforeEach(async () => {
    originalLocksDescriptor = Object.getOwnPropertyDescriptor(navigator, "locks")
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    vi.spyOn(Date, "now").mockReturnValue(NOW)
    await initOfflineQueue()
  })

  afterEach(() => {
    if (originalLocksDescriptor) {
      Object.defineProperty(navigator, "locks", originalLocksDescriptor)
    } else {
      Reflect.deleteProperty(navigator, "locks")
    }
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("sends the second write with fresh proof after same-session CSRF rotation", async () => {
    const batch = await startDelayedBatch()
    try {
      await vi.waitFor(() =>
        expect(batch.attempts).toEqual([{ idempotencyKey: "op-first", csrfToken: CSRF }])
      )
      batch.rotate({ sessionNonce: SESSION, csrfToken: ROTATED_CSRF })
    } finally {
      batch.releaseFirst()
      await batch.pass
    }

    // Stop and retain the row, or acquire fresh proof before its first send.
    // Sending stale proof then deleting/retrying that rejected write is unsafe.
    expect([
      {
        attempts: [],
        remaining: [batch.second],
      },
      {
        attempts: [{ idempotencyKey: "op-second", csrfToken: ROTATED_CSRF }],
        remaining: [],
      },
    ]).toContainEqual({
      attempts: batch.attempts.slice(1),
      remaining: await readPendingMutations(),
    })
    // The original safety oracle above remains; the selected fix must also make progress.
    expect(batch.attempts.slice(1)).toEqual([
      { idempotencyKey: "op-second", csrfToken: ROTATED_CSRF },
    ])
    expect(await readPendingMutations()).toEqual([])
  })

  it.each([401, 403])(
    "deletes a genuine HTTP %s under stable proof without retrying it on a later trigger",
    async (status) => {
      stubWindow({ sessionNonce: SESSION, csrfToken: CSRF })
      await storePendingMutation(mutation("rejected"))
      const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status }))
      vi.stubGlobal("fetch", fetchMock)

      await processOfflineQueues()

      expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
        `${window.location.origin}/api/v1/profile`,
        expect.objectContaining({
          headers: expect.objectContaining({
            "X-CSRF-Token": CSRF,
            "Idempotency-Key": "op-rejected",
          }),
        })
      )
      expect(await readPendingMutations()).toEqual([])

      vi.mocked(Date.now).mockReturnValue(NOW + 60_000)
      await processOfflineQueues()

      expect(fetchMock).toHaveBeenCalledOnce()
      expect(await readPendingMutations()).toEqual([])
    }
  )

  it("does not send or rebind the second old-owner write after an in-flight account transition", async () => {
    const batch = await startDelayedBatch()
    try {
      await vi.waitFor(() =>
        expect(batch.attempts).toEqual([{ idempotencyKey: "op-first", csrfToken: CSRF }])
      )
      batch.rotate({
        sessionNonce: "session-B",
        csrfToken: "csrf-account-B",
      })
    } finally {
      batch.releaseFirst()
      await batch.pass
    }

    expect(batch.attempts.slice(1)).toEqual([])
    expect(await readPendingMutations()).toEqual([batch.second])
    expect(batch.second).toMatchObject({
      mutationId: "second",
      sessionNonce: SESSION,
      idempotencyKey: "op-second",
      retryCount: 0,
    })

    // A later trigger under B cannot adopt A's unexpired record.
    await processOfflineQueues()

    expect(batch.attempts.slice(1)).toEqual([])
    expect(await readPendingMutations()).toEqual([batch.second])
  })

  it.each([
    { mode: "with Web Locks", useWebLocks: true },
    { mode: "without Web Locks", useWebLocks: false },
  ])("holds on missing proof and recovers on a later trigger $mode", async ({ useWebLocks }) => {
    const locks = useWebLocks ? fakeLockManager() : undefined
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true })
    const batch = await startDelayedBatch()
    try {
      await vi.waitFor(() =>
        expect(batch.attempts).toEqual([{ idempotencyKey: "op-first", csrfToken: CSRF }])
      )
      vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue([]) })
    } finally {
      batch.releaseFirst()
      await batch.pass
    }

    expect(batch.attempts).toEqual([{ idempotencyKey: "op-first", csrfToken: CSRF }])
    expect(await readPendingMutations()).toEqual([batch.second])

    // Recovery uses another real queue trigger, not a manual lock release.
    stubWindow({ sessionNonce: SESSION, csrfToken: CSRF })
    await processOfflineQueues()

    expect(batch.attempts).toEqual([
      { idempotencyKey: "op-first", csrfToken: CSRF },
      { idempotencyKey: "op-second", csrfToken: CSRF },
    ])
    expect(await readPendingMutations()).toEqual([])
    if (locks) {
      expect(locks.request).toHaveBeenCalledTimes(2)
      expect(locks.request).toHaveBeenNthCalledWith(
        1,
        LOCK_NAME,
        { mode: "exclusive" },
        expect.any(Function)
      )
      expect(locks.request).toHaveBeenNthCalledWith(
        2,
        LOCK_NAME,
        { mode: "exclusive" },
        expect.any(Function)
      )
    }
  })

  it("stops the whole pass before later stores after the owner changes", async () => {
    const proof: Proof = { sessionNonce: SESSION, csrfToken: CSRF }
    let cookieToken = CSRF
    stubWindow(proof)
    for (const label of ["report-first", "report-second"]) {
      await storePendingReport({
        url: "/notification",
        reportUrl: "/api/v1/notifications/report",
        method: "POST",
        payload: { label },
        timestamp: NOW,
        sessionNonce: SESSION,
      })
    }
    await storePendingMutation({
      ...mutation("other-owner"),
      sessionNonce: "session-B",
      timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
    })
    const reportsBefore = await readPendingReports()
    const mutationsBefore = await readPendingMutations()
    expect(reportsBefore.map((record) => record.payload)).toEqual([
      { label: "report-first" },
      { label: "report-second" },
    ])
    expect(reportsBefore.map((record) => record.idempotencyKey)).toEqual([
      expect.any(String),
      expect.any(String),
    ])
    const firstKey = reportsBefore[0].idempotencyKey
    expect(reportsBefore[1].idempotencyKey).not.toBe(firstKey)
    expect(mutationsBefore).toEqual([
      expect.objectContaining({
        mutationId: "other-owner",
        sessionNonce: "session-B",
        timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
      }),
    ])

    let releaseFirst!: () => void
    const firstResponseGate = new Promise<void>((resolve) => {
      releaseFirst = resolve
    })
    const attempts: Attempt[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        const headers = new Headers(init?.headers)
        const attempt = {
          idempotencyKey: headers.get("Idempotency-Key"),
          csrfToken: headers.get("X-CSRF-Token"),
        }
        attempts.push(attempt)
        const response = new Response(null, {
          status: attempt.csrfToken === cookieToken ? 204 : 403,
        })
        if (attempt.idempotencyKey === firstKey) await firstResponseGate
        return response
      })
    )

    const pass = processOfflineQueues()
    try {
      await vi.waitFor(() =>
        expect(attempts).toEqual([{ idempotencyKey: firstKey, csrfToken: CSRF }])
      )
      Object.assign(proof, { sessionNonce: "session-B", csrfToken: "csrf-account-B" })
      cookieToken = "csrf-account-B"
    } finally {
      releaseFirst()
      await pass
    }

    expect(attempts).toEqual([{ idempotencyKey: firstKey, csrfToken: CSRF }])
    expect(await readPendingReports()).toEqual([reportsBefore[1]])
    // Continuing to the mutation store under A would prune this expired B row;
    // switching the pass to B could send it. Neither is allowed after the stop.
    expect(await readPendingMutations()).toEqual(mutationsBefore)
  })

  it("does not refresh proof for held, not-due or other-owner rows and preserves TTL cleanup", async () => {
    const postMessage = stubWindow({ sessionNonce: SESSION, csrfToken: CSRF })
    await storePendingNavigation({
      url: "/current-navigation",
      timestamp: NOW,
      sessionNonce: SESSION,
    })
    await storePendingNavigation({
      url: "/expired-navigation",
      timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
      sessionNonce: "expired-owner",
    })
    await addRecord(STORES.MUTATION, {
      ...mutation("future"),
      retryCount: 2,
      nextAttemptAt: NOW + 60_000,
    })
    await storePendingMutation({
      ...mutation("other"),
      sessionNonce: "session-B",
      timestamp: NOW - 1_000,
    })
    await storePendingMutation({
      ...mutation("expired-other"),
      sessionNonce: "session-C",
      timestamp: NOW - OTHER_SESSION_RECORD_TTL_MS,
    })
    await storePendingMutation({ ...mutation("unbound"), sessionNonce: null })
    const navigationsBefore = await readPendingNavigations()
    const mutationsBefore = await readPendingMutations()
    expect(navigationsBefore.map((record) => record.url)).toEqual([
      "/current-navigation",
      "/expired-navigation",
    ])
    expect(mutationsBefore.map((record) => record.mutationId)).toEqual([
      "future",
      "other",
      "expired-other",
      "unbound",
    ])
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(postMessage).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingNavigations()).toEqual([navigationsBefore[0]])
    expect(await readPendingMutations()).toEqual([
      mutationsBefore[0],
      mutationsBefore[1],
      mutationsBefore[3],
    ])
  })
})
