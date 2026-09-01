import { afterEach, describe, expect, it, vi } from "vitest"

const idbSet = vi.fn((..._args: unknown[]) => Promise.resolve())
const idbGet = vi.fn((..._args: unknown[]) => Promise.resolve(undefined))
const idbDel = vi.fn((..._args: unknown[]) => Promise.resolve())

vi.mock("idb-keyval", () => ({
  set: (...args: unknown[]) => idbSet(...args),
  get: (...args: unknown[]) => idbGet(...args),
  del: (...args: unknown[]) => idbDel(...args),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  vi.resetModules()
  idbSet.mockClear()
  idbGet.mockClear()
  idbDel.mockClear()
})

const makeClient = (payload: unknown = "ok") =>
  ({
    timestamp: 0,
    buster: "",
    clientState: { queries: [{ payload }], mutations: [] },
  }) as never

describe("queryClient quota closure paths", () => {
  it("uses the responsive quota and skips an oversized cache", async () => {
    const estimate = vi.fn().mockResolvedValue({ quota: 1_000 })
    vi.stubGlobal("navigator", { storage: { estimate } })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { createIDBPersister } = await import("@/app/queryClient")

    await createIDBPersister("tiny").persistClient(makeClient("payload"))

    expect(estimate).toHaveBeenCalledOnce()
    expect(idbSet).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("Cache too large"))
  })

  it("skips an oversized cache without development logging in production", async () => {
    vi.stubEnv("DEV", false)
    const estimate = vi.fn().mockResolvedValue({ quota: 1_000 })
    vi.stubGlobal("navigator", { storage: { estimate } })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { createIDBPersister } = await import("@/app/queryClient")

    await createIDBPersister("tiny-production").persistClient(makeClient("payload"))

    expect(idbSet).not.toHaveBeenCalled()
    expect(warn).not.toHaveBeenCalled()
  })

  it("clears a quota-exhausted cache without development logging in production", async () => {
    vi.stubEnv("DEV", false)
    vi.stubGlobal("navigator", { storage: { estimate: vi.fn().mockResolvedValue({ quota: 1e9 }) } })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    idbSet.mockRejectedValueOnce(new DOMException("quota", "QuotaExceededError"))
    const { createIDBPersister } = await import("@/app/queryClient")

    await createIDBPersister("quota-production").persistClient(makeClient())

    expect(idbDel).toHaveBeenCalledWith("quota-production")
    expect(warn).not.toHaveBeenCalled()
  })

  it("falls back to the default quota when the estimate is unavailable and memoizes it", async () => {
    const estimate = vi.fn().mockResolvedValue({ quota: 0 })
    vi.stubGlobal("navigator", { storage: { estimate } })
    const { createIDBPersister } = await import("@/app/queryClient")
    const persister = createIDBPersister("default")

    await persister.persistClient(makeClient())
    await persister.persistClient(makeClient())

    expect(estimate).toHaveBeenCalledOnce()
    expect(idbSet).toHaveBeenCalledTimes(2)
  })

  it("continues with the default quota when storage estimation throws", async () => {
    const estimate = vi.fn().mockRejectedValue(new Error("storage unavailable"))
    vi.stubGlobal("navigator", { storage: { estimate } })
    const { createIDBPersister } = await import("@/app/queryClient")

    await expect(
      createIDBPersister("fallback").persistClient(makeClient())
    ).resolves.toBeUndefined()
    expect(idbSet).toHaveBeenCalledOnce()
  })

  it("falls back safely when storage or its estimate method is unavailable", async () => {
    vi.stubGlobal("navigator", {})
    const { createIDBPersister } = await import("@/app/queryClient")

    await expect(
      createIDBPersister("no-storage").persistClient(makeClient())
    ).resolves.toBeUndefined()
    expect(idbSet).toHaveBeenCalledWith("no-storage", expect.anything())

    vi.resetModules()
    idbSet.mockClear()
    vi.stubGlobal("navigator", { storage: {} })
    const second = await import("@/app/queryClient")
    await expect(
      second.createIDBPersister("no-estimate").persistClient(makeClient())
    ).resolves.toBeUndefined()
    expect(idbSet).toHaveBeenCalledWith("no-estimate", expect.anything())
  })

  it("rejects a negative storage quota instead of treating it as available", async () => {
    vi.stubGlobal("navigator", { storage: { estimate: vi.fn().mockResolvedValue({ quota: -1 }) } })
    const { createIDBPersister } = await import("@/app/queryClient")

    await createIDBPersister("negative-quota").persistClient(makeClient())

    expect(idbSet).toHaveBeenCalledWith("negative-quota", expect.anything())
  })

  it("accepts a payload exactly at the resolved quota boundary", async () => {
    const estimate = vi.fn().mockResolvedValue({ quota: 100 * 1024 * 1024 })
    vi.stubGlobal("navigator", { storage: { estimate } })
    const client = makeClient("boundary")
    const serializedLength = JSON.stringify(client).length

    // The responsive quota is five percent of the estimate. Pick a tiny
    // exact boundary by replacing the estimate with a value that yields the
    // serialized fixture length after flooring.
    vi.resetModules()
    idbSet.mockClear()
    const exactQuota = serializedLength * 20
    vi.stubGlobal("navigator", {
      storage: { estimate: vi.fn().mockResolvedValue({ quota: exactQuota }) },
    })
    const exact = await import("@/app/queryClient")
    await exact.createIDBPersister("exact-boundary").persistClient(client)

    expect(idbSet).toHaveBeenCalledWith("exact-boundary", client)
  })

  it("logs the exact human-readable size and quota when a cache is too large", async () => {
    const estimate = vi.fn().mockResolvedValue({ quota: 100 * 1024 * 1024 })
    vi.stubGlobal("navigator", { storage: { estimate } })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { createIDBPersister } = await import("@/app/queryClient")
    const client = makeClient("x".repeat(6 * 1024 * 1024))
    await createIDBPersister("large").persistClient(client)

    const serializedMb = (JSON.stringify(client).length / 1024 / 1024).toFixed(1)
    expect(warn).toHaveBeenCalledWith(
      `[IDBPersister] Cache too large (${serializedMb} MB, quota 5 MB) — skipping IDB persist`
    )
  })

  it("covers query and mutation dehydration policies", async () => {
    const { persistOptions } = await import("@/app/queryClient")
    const shouldDehydrateQuery = persistOptions.dehydrateOptions?.shouldDehydrateQuery
    const shouldDehydrateMutation = persistOptions.dehydrateOptions?.shouldDehydrateMutation

    expect(shouldDehydrateQuery?.({ state: { status: "success" } } as never)).toBe(true)
    expect(shouldDehydrateQuery?.({ state: { status: "error" } } as never)).toBe(false)
    expect(shouldDehydrateMutation?.({ state: { isPaused: true, status: "idle" } } as never)).toBe(
      true
    )
    expect(
      shouldDehydrateMutation?.({ state: { isPaused: false, status: "pending" } } as never)
    ).toBe(true)
    expect(
      shouldDehydrateMutation?.({ state: { isPaused: false, status: "success" } } as never)
    ).toBe(false)
  })

  it("falls back for malformed and non-positive duration environment values", async () => {
    vi.stubEnv("VITE_QUERY_STALE_TIME_MS", "not-a-duration")
    vi.stubEnv("VITE_QUERY_CACHE_TTL_MS", "-1")
    const { createQueryClient } = await import("@/app/queryClient")
    const defaults = createQueryClient().getDefaultOptions()

    expect(defaults.queries?.staleTime).toBe(5 * 60_000)
    expect(defaults.queries?.gcTime).toBe(30 * 60_000)
  })

  it("does not parse an absent duration environment variable", async () => {
    const parseInt = vi.spyOn(Number, "parseInt")
    const { createQueryClient } = await import("@/app/queryClient")

    createQueryClient()

    expect(parseInt).not.toHaveBeenCalled()
  })

  it("falls back when a duration is exactly zero", async () => {
    vi.stubEnv("VITE_QUERY_STALE_TIME_MS", "0")
    vi.stubEnv("VITE_QUERY_CACHE_TTL_MS", "0")
    const { createQueryClient } = await import("@/app/queryClient")
    const defaults = createQueryClient().getDefaultOptions()

    expect(defaults.queries?.staleTime).toBe(5 * 60_000)
    expect(defaults.queries?.gcTime).toBe(30 * 60_000)
  })

  it("uses the fallback for empty duration values", async () => {
    vi.stubEnv("VITE_QUERY_STALE_TIME_MS", "")
    vi.stubEnv("VITE_QUERY_CACHE_TTL_MS", "")
    const { createQueryClient } = await import("@/app/queryClient")
    const defaults = createQueryClient().getDefaultOptions()

    expect(defaults.queries?.staleTime).toBe(5 * 60_000)
    expect(defaults.queries?.gcTime).toBe(30 * 60_000)
  })

  it("uses valid positive duration environment values", async () => {
    vi.stubEnv("VITE_QUERY_STALE_TIME_MS", "1234")
    vi.stubEnv("VITE_QUERY_CACHE_TTL_MS", "5678")
    const { createQueryClient } = await import("@/app/queryClient")
    const defaults = createQueryClient().getDefaultOptions()

    expect(defaults.queries?.staleTime).toBe(1234)
    expect(defaults.queries?.gcTime).toBe(5678)
  })

  it("pins persistence age and the default application version buster", async () => {
    const { persistOptions } = await import("@/app/queryClient")

    expect(persistOptions.maxAge).toBe(7 * 24 * 60 * 60 * 1000)
    expect(persistOptions.buster).toBe("1.0.0")
  })

  it("uses an explicit application version buster when configured", async () => {
    vi.stubEnv("VITE_APP_VERSION", "2026.09.01")
    const { persistOptions } = await import("@/app/queryClient")

    expect(persistOptions.buster).toBe("2026.09.01")
  })

  it.each([
    ["DOMException with a different name", new DOMException("not quota", "UnknownError")],
    [
      "non-DOMException with a quota-like name",
      Object.assign(new Error("not quota"), { name: "QuotaExceededError" }),
    ],
  ])("rethrows %s instead of clearing IDB", async (_label, error) => {
    idbSet.mockRejectedValueOnce(error)
    const { createIDBPersister } = await import("@/app/queryClient")

    await expect(createIDBPersister("wrong-quota").persistClient(makeClient())).rejects.toBe(error)
    expect(idbDel).not.toHaveBeenCalled()
  })
})
