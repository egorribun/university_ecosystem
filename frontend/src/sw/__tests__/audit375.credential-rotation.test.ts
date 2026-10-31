import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  initOfflineQueue,
  processOfflineQueues,
  readPendingMutations,
  storePendingMutation,
} from "../offline"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

const NOW = 1_800_000_000_000
const SESSION = "session-A"
const CSRF = "csrf-before-step-up"
const ROTATED_CSRF = "csrf-after-step-up"

type Proof = {
  sessionNonce: string
  csrfToken: string
}

type Attempt = {
  idempotencyKey: string | null
  csrfToken: string | null
}

function stubWindow(proof: Proof) {
  vi.stubGlobal("clients", {
    matchAll: vi.fn().mockResolvedValue([
      {
        url: `${window.location.origin}/`,
        postMessage: vi.fn((_message: unknown, ports: MessagePort[]) => {
          ports[0]?.postMessage({ ...proof })
        }),
      },
    ]),
  })
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

  it("holds the second write or sends it with fresh proof after same-session CSRF rotation", async () => {
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
  })

  it("deletes a genuine 403 under stable proof without retrying it on a later trigger", async () => {
    stubWindow({ sessionNonce: SESSION, csrfToken: CSRF })
    await storePendingMutation(mutation("rejected"))
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }))
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
  })

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
})
