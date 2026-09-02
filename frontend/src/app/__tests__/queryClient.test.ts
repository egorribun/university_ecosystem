import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Mock idb-keyval so the persister exercises set/get/del without a real IndexedDB.
const idbSet = vi.fn<(...a: unknown[]) => Promise<void>>(() => Promise.resolve())
const idbGet = vi.fn<(...a: unknown[]) => Promise<unknown>>(() => Promise.resolve(undefined))
const idbDel = vi.fn<(...a: unknown[]) => Promise<void>>(() => Promise.resolve())

vi.mock("idb-keyval", () => ({
  set: (...args: unknown[]) => idbSet(...args),
  get: (...args: unknown[]) => idbGet(...args),
  del: (...args: unknown[]) => idbDel(...args),
}))

import { createIDBPersister, createQueryClient, idbPersister, queryClient } from "@/app/queryClient"
import type { PersistedClient } from "@tanstack/react-query-persist-client"

const makeClient = (overrides: Partial<PersistedClient> = {}): PersistedClient =>
  ({
    timestamp: 0,
    buster: "",
    clientState: { queries: [], mutations: [] },
    ...overrides,
  }) as PersistedClient

beforeEach(() => {
  vi.clearAllMocks()
})

describe("queryClient — default options", () => {
  it("createQueryClient constructs a client with the documented query defaults", () => {
    const client = createQueryClient()
    const defaults = client.getDefaultOptions()

    expect(defaults.queries?.retry).toBe(1)
    expect(defaults.queries?.refetchOnWindowFocus).toBe(true)
    expect(defaults.queries?.refetchOnReconnect).toBe("always")
    expect(typeof defaults.queries?.staleTime).toBe("number")
    expect(defaults.queries?.staleTime as number).toBeGreaterThan(0)
    expect(defaults.queries?.gcTime as number).toBeGreaterThan(0)
  })

  it("applies the standard 5-minute stale / 30-minute gc fallbacks", () => {
    const client = createQueryClient()
    const defaults = client.getDefaultOptions()
    expect(defaults.queries?.staleTime).toBe(5 * 60_000)
    expect(defaults.queries?.gcTime).toBe(30 * 60_000)
  })

  it("disables mutation retries and gc", () => {
    const client = createQueryClient()
    const defaults = client.getDefaultOptions()
    expect(defaults.mutations?.retry).toBe(0)
    expect(defaults.mutations?.gcTime).toBe(0)
  })

  it("exports a singleton queryClient instance", () => {
    expect(queryClient).toBeDefined()
    expect(queryClient.getDefaultOptions().queries?.retry).toBe(1)
  })

  it("createQueryClient returns a fresh instance each call", () => {
    expect(createQueryClient()).not.toBe(createQueryClient())
  })
})

describe("queryClient — IDB persister", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("exports a default idbPersister with the persist/restore/remove contract", () => {
    expect(typeof idbPersister.persistClient).toBe("function")
    expect(typeof idbPersister.restoreClient).toBe("function")
    expect(typeof idbPersister.removeClient).toBe("function")
  })

  it("uses the canonical key for the default persister", async () => {
    const client = makeClient()

    await idbPersister.persistClient(client)
    await idbPersister.restoreClient()
    await idbPersister.removeClient()

    expect(idbSet).toHaveBeenCalledWith("reactQuery", client)
    expect(idbGet).toHaveBeenCalledWith("reactQuery")
    expect(idbDel).toHaveBeenCalledWith("reactQuery")
  })

  it("persistClient writes the client to IDB under the given key", async () => {
    const persister = createIDBPersister("myKey")
    const client = makeClient()
    await persister.persistClient(client)
    expect(idbSet).toHaveBeenCalledWith("myKey", client)
  })

  it("restoreClient reads back from IDB", async () => {
    const stored = makeClient({ timestamp: 123 })
    idbGet.mockResolvedValueOnce(stored)
    const persister = createIDBPersister("restoreKey")
    await expect(persister.restoreClient()).resolves.toBe(stored)
    expect(idbGet).toHaveBeenCalledWith("restoreKey")
  })

  it("removeClient deletes the IDB entry", async () => {
    const persister = createIDBPersister("removeKey")
    await persister.removeClient()
    expect(idbDel).toHaveBeenCalledWith("removeKey")
  })

  // NOTE: the quota threshold is resolved + memoized at module load via
  // navigator.storage.estimate(); stubbing it afterwards has no effect. The
  // default 20 MB quota is far larger than any test fixture, so the
  // size-skip branch isn't reliably reachable from a unit test — the
  // QuotaExceededError + re-throw branches below cover the failure paths
  // (they pass the size check, then the mocked `set` rejects).

  it("clears the cache when IDB throws a QuotaExceededError", async () => {
    idbSet.mockRejectedValueOnce(new DOMException("over quota", "QuotaExceededError"))
    const persister = createIDBPersister("qeKey")
    await persister.persistClient(makeClient())
    expect(idbDel).toHaveBeenCalledWith("qeKey")
  })

  it("re-throws non-quota errors from persistClient", async () => {
    const boom = new Error("unexpected idb failure")
    idbSet.mockRejectedValueOnce(boom)
    const persister = createIDBPersister("errKey")
    await expect(persister.persistClient(makeClient())).rejects.toBe(boom)
  })

  it("falls back to the default quota when storage estimation rejects", async () => {
    // Import a fresh module after installing the rejecting browser API so the
    // lazy quota resolver exercises its asynchronous catch contract directly.
    vi.resetModules()
    vi.stubGlobal("navigator", {
      storage: { estimate: vi.fn().mockRejectedValue(new Error("storage unavailable")) },
    })

    const isolated = await import("@/app/queryClient")
    await expect(
      isolated.createIDBPersister("estimate-error").persistClient(makeClient())
    ).resolves.toBeUndefined()
    expect(idbSet).toHaveBeenCalledWith("estimate-error", expect.anything())
  })
})
