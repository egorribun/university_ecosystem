import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  initOfflineQueue,
  processPendingMutations,
  readPendingMutations,
  storePendingMutation,
} from "../offline"

vi.mock("../logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

const enqueue = (overrides: Record<string, unknown> = {}) =>
  storePendingMutation({
    url: "http://localhost/api/mutation",
    method: "POST",
    payload: { value: 1 },
    mutationId: `mutation-${Math.random()}`,
    idempotencyKey: `key-${Math.random()}`,
    ...overrides,
  } as never)

describe("offline mutation queue — retry and sync branches", () => {
  let onlineSpy: ReturnType<typeof vi.spyOn>

  beforeEach(async () => {
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()
  })

  afterEach(() => {
    onlineSpy.mockRestore()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  })

  it("does nothing while offline and when the queue is empty", async () => {
    onlineSpy.mockReturnValue(false)
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processPendingMutations()
    expect(fetchMock).not.toHaveBeenCalled()

    onlineSpy.mockReturnValue(true)
    await processPendingMutations()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("uses deterministic fallback identifiers when crypto.randomUUID is unavailable", async () => {
    const nativeCrypto = globalThis.crypto
    vi.stubGlobal("crypto", { subtle: nativeCrypto.subtle, randomUUID: undefined })
    vi.spyOn(Date, "now").mockReturnValue(1234)
    vi.spyOn(Math, "random").mockReturnValueOnce(0.1).mockReturnValueOnce(0.2)

    await storePendingMutation({
      url: "http://localhost/api/mutation",
      method: "POST",
      payload: { value: 1 },
      mutationId: undefined,
      idempotencyKey: undefined,
    })
    const [record] = await readPendingMutations()
    expect(record?.mutationId).toBe("1234.1")
    expect(record?.idempotencyKey).toBe("1234.2")
  })

  it("uses deterministic fallback identifiers when crypto is unavailable entirely", async () => {
    vi.stubGlobal("crypto", undefined)
    vi.spyOn(Date, "now").mockReturnValue(5678)
    vi.spyOn(Math, "random").mockReturnValueOnce(0.3).mockReturnValueOnce(0.4)

    await storePendingMutation({
      url: "http://localhost/api/no-crypto",
      method: "POST",
      payload: { value: 1 },
      mutationId: undefined,
      idempotencyKey: undefined,
    })

    const [record] = await readPendingMutations()
    expect(record?.mutationId).toBe("5678.3")
    expect(record?.idempotencyKey).toBe("5678.4")
  })

  it("does not open a channel or send an unbound mutation even if the server would succeed", async () => {
    const closeMock = vi.fn()
    class ThrowingBroadcastChannel {
      postMessage() {
        throw new Error("channel unavailable")
      }

      close() {
        closeMock()
      }
    }
    vi.stubGlobal("BroadcastChannel", ThrowingBroadcastChannel)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal("fetch", fetchMock)

    await enqueue({ mutationId: "success", idempotencyKey: "key-success" })
    await processPendingMutations()

    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({ mutationId: "success", retryCount: 0 }),
    ])
    expect(fetchMock).not.toHaveBeenCalled()
    expect(closeMock).not.toHaveBeenCalled()
  })

  it("does not broadcast or increment retries for an unbound mutation", async () => {
    const closeMock = vi.fn()
    class TrackingBroadcastChannel {
      postMessage = vi.fn()

      close() {
        closeMock()
      }
    }
    vi.stubGlobal("BroadcastChannel", TrackingBroadcastChannel)
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"))
    vi.stubGlobal("fetch", fetchMock)

    await enqueue({ mutationId: "failed", idempotencyKey: "key-failed" })
    await processPendingMutations()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(closeMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({ mutationId: "failed", retryCount: 0 }),
    ])
  })

  it("applies mutation defaults and preserves an empty payload without sending", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal("fetch", fetchMock)

    await storePendingMutation({
      url: "http://localhost/api/defaulted-mutation",
      payload: undefined,
      mutationId: "defaulted",
      idempotencyKey: "key-defaulted",
    } as never)
    const [stored] = await readPendingMutations()
    expect(stored).toMatchObject({ method: "POST", retryCount: 0, category: "general" })

    await processPendingMutations()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([stored])
  })

  it("preserves unbound records and retry counts regardless of prior retry state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 400 })
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockRejectedValueOnce(new Error("network down"))
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("BroadcastChannel", undefined)

    await enqueue({ mutationId: "bad-request", idempotencyKey: "key-400" })
    await enqueue({ mutationId: "server-error", idempotencyKey: "key-500" })
    await enqueue({ mutationId: "network-error", idempotencyKey: "key-network" })
    await enqueue({ mutationId: "exhausted", idempotencyKey: "key-exhausted", retryCount: 5 })

    await processPendingMutations()

    const remaining = await readPendingMutations()
    expect(remaining.map((record) => record.mutationId)).toEqual([
      "bad-request",
      "server-error",
      "network-error",
      "exhausted",
    ])
    expect(remaining.map((record) => record.retryCount)).toEqual([0, 0, 0, 5])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([403, 404, 429, 500])(
    "does not send an unbound mutation even when the response would be %s",
    async (status) => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status })
      vi.stubGlobal("fetch", fetchMock)
      await enqueue({ mutationId: `status-${status}`, idempotencyKey: `key-${status}` })

      await processPendingMutations()

      const remaining = await readPendingMutations()
      expect(fetchMock).not.toHaveBeenCalled()
      expect(remaining).toEqual([
        expect.objectContaining({ mutationId: `status-${status}`, retryCount: 0 }),
      ])
    }
  )

  it("retains the idempotency key, custom headers and JSON payload without broadcasting them", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal("fetch", fetchMock)
    await enqueue({
      mutationId: "headers",
      idempotencyKey: "key-headers",
      payload: { value: "payload" },
      headers: { Authorization: "Bearer test" },
    })

    await processPendingMutations()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingMutations()).toEqual([
      expect.objectContaining({
        method: "POST",
        payload: { value: "payload" },
        idempotencyKey: "key-headers",
        headers: { Authorization: "Bearer test" },
      }),
    ])
  })
})
