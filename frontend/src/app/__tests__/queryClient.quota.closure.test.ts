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
})
