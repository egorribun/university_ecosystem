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

  it("syncs success and tolerates BroadcastChannel postMessage failures", async () => {
    class ThrowingBroadcastChannel {
      postMessage() {
        throw new Error("channel unavailable")
      }
    }
    vi.stubGlobal("BroadcastChannel", ThrowingBroadcastChannel)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200 }))

    await enqueue({ mutationId: "success", idempotencyKey: "key-success" })
    await processPendingMutations()

    expect(await readPendingMutations()).toHaveLength(0)
  })

  it("applies mutation defaults and omits the request body for an empty payload", async () => {
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

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost/api/defaulted-mutation",
      expect.objectContaining({ method: "POST", body: undefined })
    )
    expect(await readPendingMutations()).toHaveLength(0)
  })

  it("deletes non-retriable records, increments retryable records, and discards exhausted ones", async () => {
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
    expect(remaining.map((record) => record.mutationId)).toEqual(["server-error", "network-error"])
    expect(remaining.map((record) => record.retryCount)).toEqual([1, 1])
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
