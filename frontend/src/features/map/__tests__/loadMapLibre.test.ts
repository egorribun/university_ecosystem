import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mockState = vi.hoisted(() => ({
  attempts: 0,
  workerUrl: "/assets/maplibre-worker-hash.mjs",
  setWorkerUrl: vi.fn(),
  createTrustedScriptURL: vi.fn(),
  workerCalls: [] as Array<{ scriptURL: unknown; options: unknown; newTarget: unknown }>,
}))

vi.mock("maplibre-gl", () => ({ setWorkerUrl: mockState.setWorkerUrl }))
vi.mock("@/utils/trustedTypes", () => ({
  createTrustedScriptURL: mockState.createTrustedScriptURL,
}))
vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?url", () => ({
  get default() {
    return mockState.workerUrl
  },
}))

class NativeWorker {
  static readonly marker = "native-worker-static"

  constructor(scriptURL: string | URL, options?: WorkerOptions) {
    mockState.workerCalls.push({ scriptURL, options, newTarget: new.target })
  }
}

describe("loadMapLibre", () => {
  beforeEach(() => {
    mockState.attempts = 0
    mockState.workerUrl = "/assets/maplibre-worker-hash.mjs"
    mockState.setWorkerUrl.mockReset()
    mockState.createTrustedScriptURL.mockReset()
    mockState.createTrustedScriptURL.mockImplementation((value: string) => ({ value }))
    mockState.workerCalls.length = 0
    vi.stubGlobal("Worker", NativeWorker)
    vi.resetModules()
    vi.doUnmock("@/components/map/MapLibreMap")
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("deduplicates preloads and upgrades only the exact Vite module worker at the native sink", async () => {
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const trustedURL = Object.freeze({ toString: () => mockState.workerUrl })
    mockState.createTrustedScriptURL.mockReturnValue(trustedURL)
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")
    const first = loadMapLibre()
    const second = loadMapLibre()

    expect(second).toBe(first)
    await expect(first).resolves.toHaveProperty("default")
    expect(mockState.setWorkerUrl).toHaveBeenCalledWith(mockState.workerUrl)

    const installedWorker = globalThis.Worker
    expect(installedWorker).not.toBe(NativeWorker)
    expect(installedWorker.prototype).toBe(NativeWorker.prototype)
    expect((installedWorker as typeof Worker & { marker: string }).marker).toBe(NativeWorker.marker)

    const mapWorker = new Worker(mockState.workerUrl, { type: "module" })
    expect(mapWorker).toBeInstanceOf(NativeWorker)
    expect(mockState.workerCalls[0]).toMatchObject({
      scriptURL: trustedURL,
      options: { type: "module" },
      newTarget: installedWorker,
    })

    class DerivedWorker extends Worker {}
    const derivedWorker = new DerivedWorker(mockState.workerUrl, { type: "module" })
    expect(derivedWorker).toBeInstanceOf(DerivedWorker)
    expect(derivedWorker).toBeInstanceOf(NativeWorker)
    expect(mockState.workerCalls[1]?.newTarget).toBe(DerivedWorker)

    const trustedCryptoWorker = Object.freeze({ toString: () => "/assets/crypto-worker.mjs" })
    const untouchedUrls = [
      `${mockState.workerUrl}?copy=1`,
      `${mockState.workerUrl}.unexpected`,
      "https://untrusted.example/worker.mjs",
    ]
    for (const url of untouchedUrls) new Worker(url, { type: "module" })
    new Worker(mockState.workerUrl)
    new Worker(mockState.workerUrl, { type: "classic" })
    new Worker(trustedCryptoWorker as unknown as string, { type: "module" })

    expect(mockState.createTrustedScriptURL).toHaveBeenCalledTimes(2)
    expect(mockState.createTrustedScriptURL).toHaveBeenNthCalledWith(1, mockState.workerUrl)
    expect(mockState.createTrustedScriptURL).toHaveBeenNthCalledWith(2, mockState.workerUrl)
    expect(mockState.workerCalls.slice(2).map(({ scriptURL }) => scriptURL)).toEqual([
      ...untouchedUrls,
      mockState.workerUrl,
      mockState.workerUrl,
      trustedCryptoWorker,
    ])
  })

  it.each([
    ["malformed", "http://["],
    ["cross-origin", "https://untrusted.example/maplibre-worker.mjs"],
    ["non-module asset", "/assets/maplibre-worker.js"],
    ["username", "http://user@localhost/assets/maplibre-worker.mjs"],
    ["password", "http://:secret@localhost/assets/maplibre-worker.mjs"],
    ["query", "/assets/maplibre-worker.mjs?v=1"],
    ["fragment", "/assets/maplibre-worker.mjs#worker"],
  ])("rejects a %s imported worker asset before installation", async (_label, assetUrl) => {
    mockState.workerUrl = assetUrl
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).rejects.toThrow("same-origin static .mjs asset")
    expect(mockState.setWorkerUrl).not.toHaveBeenCalled()
    expect(mockState.createTrustedScriptURL).not.toHaveBeenCalled()
    expect(globalThis.Worker).toBe(NativeWorker)
  })

  it("skips browser Worker setup during SSR", async () => {
    vi.stubGlobal("window", undefined)
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).resolves.toHaveProperty("default")
    expect(mockState.setWorkerUrl).toHaveBeenCalledWith(mockState.workerUrl)
    expect(globalThis.Worker).toBe(NativeWorker)
    expect(mockState.createTrustedScriptURL).not.toHaveBeenCalled()
  })

  it("rejects a missing browser Worker constructor", async () => {
    vi.stubGlobal("Worker", undefined)
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).rejects.toThrow("browser Worker constructor")
    expect(mockState.setWorkerUrl).not.toHaveBeenCalled()
  })

  it("reuses its installed proxy after setWorkerUrl fails and the chunk retries", async () => {
    mockState.setWorkerUrl.mockImplementationOnce(() => {
      throw new Error("transient MapLibre configuration failure")
    })
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).rejects.toThrow("transient MapLibre configuration failure")
    const installedWorker = globalThis.Worker
    await expect(loadMapLibre()).resolves.toHaveProperty("default")

    expect(globalThis.Worker).toBe(installedWorker)
    expect(mockState.setWorkerUrl).toHaveBeenCalledTimes(2)
    expect(mockState.createTrustedScriptURL).not.toHaveBeenCalled()

    const trustedURL = Object.freeze({ toString: () => mockState.workerUrl })
    mockState.createTrustedScriptURL.mockReturnValue(trustedURL)
    new Worker(mockState.workerUrl, { type: "module" })
    expect(mockState.createTrustedScriptURL).toHaveBeenCalledExactlyOnceWith(mockState.workerUrl)
    expect(mockState.workerCalls).toHaveLength(1)
    expect(mockState.workerCalls[0]?.scriptURL).toBe(trustedURL)
  })

  it("fails closed when the Trusted Types helper rejects the worker URL", async () => {
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    mockState.createTrustedScriptURL.mockImplementation(() => {
      throw new TypeError("Trusted Types policy rejected the worker URL")
    })
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")
    await loadMapLibre()

    expect(() => new Worker(mockState.workerUrl, { type: "module" })).toThrow(
      "Trusted Types policy rejected the worker URL"
    )
    expect(mockState.createTrustedScriptURL).toHaveBeenCalledExactlyOnceWith(mockState.workerUrl)
    expect(mockState.workerCalls).toHaveLength(0)
  })

  it("preserves native Worker failures without retrying with the raw URL", async () => {
    const workerError = new TypeError("native Worker rejected the trusted URL")
    class RejectingWorker extends NativeWorker {
      constructor(scriptURL: string | URL, options?: WorkerOptions) {
        super(scriptURL, options)
        throw workerError
      }
    }
    vi.stubGlobal("Worker", RejectingWorker)
    vi.doMock("@/components/map/MapLibreMap", () => ({ MapLibreMapComponent: () => null }))
    const trustedURL = Object.freeze({ toString: () => mockState.workerUrl })
    mockState.createTrustedScriptURL.mockReturnValue(trustedURL)
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")
    await loadMapLibre()

    expect(() => new Worker(mockState.workerUrl, { type: "module" })).toThrow(workerError)
    expect(mockState.workerCalls).toHaveLength(1)
    expect(mockState.workerCalls[0]?.scriptURL).toBe(trustedURL)
    expect(mockState.workerCalls[0]?.options).toEqual({ type: "module" })
    expect(mockState.createTrustedScriptURL).toHaveBeenCalledExactlyOnceWith(mockState.workerUrl)
  })

  it("allows a later route activation to retry a failed chunk load", async () => {
    vi.doMock("@/components/map/MapLibreMap", () => {
      mockState.attempts += 1
      if (mockState.attempts === 1) throw new Error("transient chunk failure")
      return { MapLibreMapComponent: () => null }
    })
    const { loadMapLibre } = await import("@/features/map/loadMapLibre")

    await expect(loadMapLibre()).rejects.toThrow()
    await expect(loadMapLibre()).resolves.toHaveProperty("default")
    expect(mockState.attempts).toBe(2)
  })
})
