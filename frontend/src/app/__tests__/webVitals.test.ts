import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

vi.mock("web-vitals", () => ({
  onCLS: vi.fn(),
  onFCP: vi.fn(),
  onINP: vi.fn(),
  onLCP: vi.fn(),
  onTTFB: vi.fn(),
}))
vi.mock("@/app/logger", () => ({ logDebug: vi.fn(), logError: vi.fn() }))

import { onCLS, onFCP, onINP, onLCP, onTTFB } from "web-vitals"
import { logDebug } from "@/app/logger"
import {
  createCustomMetric,
  initWebVitals,
  isSameOriginEndpoint,
  reportBootstrapTTI,
  resetWebVitalsForTesting,
  resolveNavigationType,
  resolveRating,
} from "@/app/webVitals"

const PROD_BASE = { DEV: false, MODE: "production" } as unknown as ImportMetaEnv
const enabledEnv = (extra: Record<string, unknown> = {}) =>
  ({ ...PROD_BASE, VITE_ENABLE_WEB_VITALS: "true", ...extra }) as unknown as ImportMetaEnv & {
    VITE_ENABLE_WEB_VITALS?: string
    VITE_WEB_VITALS_ENDPOINT?: string
  }

const sampleMetric = (over: Record<string, unknown> = {}) => ({
  name: "CLS",
  value: 0.1,
  delta: 0.1,
  id: "v1-123",
  rating: "good" as const,
  navigationType: "navigate" as const,
  entries: [],
  ...over,
})

describe("webVitals", () => {
  beforeEach(() => {
    resetWebVitalsForTesting()
    vi.clearAllMocks()
  })
  afterEach(() => {
    resetWebVitalsForTesting()
    vi.unstubAllGlobals()
  })

  it("returns false in DEV or test mode", () => {
    expect(initWebVitals({ DEV: true, MODE: "development" } as unknown as ImportMetaEnv)).toBe(
      false
    )
    expect(initWebVitals({ DEV: false, MODE: "test" } as unknown as ImportMetaEnv)).toBe(false)
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("keeps development mode disabled even when the production flag is enabled", () => {
    expect(
      initWebVitals(
        enabledEnv({
          DEV: true,
          MODE: "development",
          VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v",
        })
      )
    ).toBe(false)
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("keeps test mode disabled even when the production flag is enabled", () => {
    expect(
      initWebVitals(
        enabledEnv({
          MODE: "test",
          VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v",
        })
      )
    ).toBe(false)
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("returns false when the feature flag is not enabled", () => {
    expect(initWebVitals(PROD_BASE)).toBe(false)
    expect(initWebVitals({ ...PROD_BASE, VITE_ENABLE_WEB_VITALS: "nope" } as never)).toBe(false)
  })

  it("registers all five supported web-vital callbacks when enabled with an endpoint", () => {
    const sendBeacon = vi.fn(() => true)
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    expect(initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))).toBe(
      true
    )
    for (const fn of [onCLS, onFCP, onINP, onLCP, onTTFB]) {
      expect(fn).toHaveBeenCalledOnce()
    }
    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric({ label: "main" }) as never)
    expect(sendBeacon).toHaveBeenCalledWith("https://metrics.test/v", expect.any(Blob))
  })

  it.each(["true", "1", "yes", " YES "])(
    "accepts the documented web-vitals flag value %s",
    (flag) => {
      expect(
        initWebVitals(
          enabledEnv({ VITE_ENABLE_WEB_VITALS: flag, VITE_WEB_VITALS_ENDPOINT: undefined })
        )
      ).toBe(true)
      expect(onCLS).toHaveBeenCalledOnce()
    }
  )

  it("serializes labelled metrics with the exact beacon payload contract", () => {
    const sendBeacon = vi.fn(() => true)
    class TestBlob {
      constructor(
        readonly parts: string[],
        readonly options: Record<string, unknown>
      ) {}
    }
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    vi.stubGlobal("Blob", TestBlob)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric({ label: "dashboard" }) as never)
    const beaconCalls = sendBeacon.mock.calls as unknown as Array<[string, TestBlob]>
    const labelledBlob = beaconCalls[0]?.[1]
    expect(labelledBlob).toBeDefined()
    expect(labelledBlob!.options).toEqual({ type: "application/json" })
    expect(JSON.parse(labelledBlob!.parts[0]!)).toEqual({
      name: "CLS",
      value: 0.1,
      delta: 0.1,
      id: "v1-123",
      rating: "good",
      navigationType: "navigate",
      label: "dashboard",
    })

    reporter(sampleMetric({ label: 42 }) as never)
    const unlabelledBlob = beaconCalls[1]?.[1]
    expect(unlabelledBlob).toBeDefined()
    expect(JSON.parse(unlabelledBlob!.parts[0]!)).not.toHaveProperty("label")
  })

  it("falls back to fetch when sendBeacon throws", () => {
    const sendBeacon = vi.fn(() => {
      throw new Error("beacon down")
    })
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))
    const reporter = vi.mocked(onLCP).mock.calls[0]![0]
    reporter(sampleMetric({ name: "LCP", value: 2400 }) as never)
    expect(fetchMock).toHaveBeenCalledWith(
      "https://metrics.test/v",
      expect.objectContaining({ method: "POST" })
    )
  })

  it("falls back to fetch when the browser does not expose Blob", async () => {
    const sendBeacon = vi.fn(() => true)
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    vi.stubGlobal("Blob", undefined)
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onLCP).mock.calls[0]![0]
    reporter(sampleMetric({ name: "LCP" }) as never)
    await Promise.resolve()

    expect(sendBeacon).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith(
      "https://metrics.test/v",
      expect.objectContaining({ method: "POST" })
    )
  })

  it("fails closed when Blob changes between its type check and read", async () => {
    const sendBeacon = vi.fn(() => true)
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    class TestBlob {
      constructor(readonly parts: string[]) {}
    }
    const blobDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Blob")
    let blobReads = 0
    Object.defineProperty(globalThis, "Blob", {
      configurable: true,
      get: () => {
        blobReads += 1
        return blobReads === 1 ? TestBlob : undefined
      },
    })
    try {
      vi.stubGlobal("navigator", { ...navigator, sendBeacon })
      vi.stubGlobal("fetch", fetchMock)
      initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

      const reporter = vi.mocked(onLCP).mock.calls[0]![0]
      reporter(sampleMetric({ name: "LCP" }) as never)
      await Promise.resolve()

      expect(blobReads).toBe(2)
      expect(sendBeacon).not.toHaveBeenCalled()
      expect(fetchMock).toHaveBeenCalledWith(
        "https://metrics.test/v",
        expect.objectContaining({ method: "POST" })
      )
    } finally {
      if (blobDescriptor) {
        Object.defineProperty(globalThis, "Blob", blobDescriptor)
      } else {
        Reflect.deleteProperty(globalThis, "Blob")
      }
    }
  })

  it("does not construct a beacon after a missing Blob check", () => {
    const sendBeacon = vi.fn(() => true)
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    class TestBlob {
      constructor(
        readonly parts: string[],
        readonly options: Record<string, unknown>
      ) {}
    }
    const blobDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Blob")
    let blobReads = 0
    Object.defineProperty(globalThis, "Blob", {
      configurable: true,
      get: () => {
        blobReads += 1
        return blobReads === 1 ? undefined : TestBlob
      },
    })
    try {
      vi.stubGlobal("navigator", { ...navigator, sendBeacon })
      vi.stubGlobal("fetch", fetchMock)
      initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

      const reporter = vi.mocked(onLCP).mock.calls[0]![0]
      reporter(sampleMetric({ name: "LCP" }) as never)

      expect(blobReads).toBe(1)
      expect(sendBeacon).not.toHaveBeenCalled()
      expect(fetchMock).toHaveBeenCalledWith(
        "https://metrics.test/v",
        expect.objectContaining({ method: "POST" })
      )
    } finally {
      if (blobDescriptor) {
        Object.defineProperty(globalThis, "Blob", blobDescriptor)
      } else {
        Reflect.deleteProperty(globalThis, "Blob")
      }
    }
  })

  it("uses fetch when the beacon API is unavailable and absorbs rejection", async () => {
    const fetchMock = vi.fn(() => Promise.reject(new Error("metrics endpoint down")))
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: undefined })
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric() as never)
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("does not construct a beacon when sendBeacon is not callable", async () => {
    const BlobSpy = vi.fn(
      class TestBlob {
        constructor(readonly parts: string[]) {}
      }
    )
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: undefined })
    vi.stubGlobal("Blob", BlobSpy)
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric() as never)
    await Promise.resolve()

    expect(BlobSpy).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("uses the exact fetch transport options when beacon transport is unavailable", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: undefined })
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    vi.mocked(onLCP).mock.calls[0]![0](sampleMetric({ name: "LCP" }) as never)
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledWith(
      "https://metrics.test/v",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        keepalive: true,
        credentials: "omit",
      })
    )
    const fetchCalls = fetchMock.mock.calls as unknown as Array<[string, RequestInit | undefined]>
    const body = fetchCalls[0]?.[1]?.body as string
    expect(JSON.parse(body)).toEqual(expect.objectContaining({ name: "LCP", value: 0.1 }))
  })

  it("does not construct a beacon when navigator is unavailable", () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    const BlobSpy = vi.fn(
      class TestBlob {
        constructor(readonly parts: string[]) {}
      }
    )
    vi.stubGlobal("navigator", undefined)
    vi.stubGlobal("Blob", BlobSpy)
    vi.stubGlobal("fetch", fetchMock)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric() as never)

    expect(BlobSpy).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("drops endpoint metrics safely when no browser transport is available", () => {
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: undefined })
    vi.stubGlobal("fetch", undefined)
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))

    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    expect(() => reporter(sampleMetric() as never)).not.toThrow()
  })

  it("does not initialize endpoint reporting without a browser window", () => {
    vi.stubGlobal("window", undefined)

    expect(initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))).toBe(
      false
    )
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("uses the console reporter when no endpoint is configured", () => {
    expect(initWebVitals(enabledEnv())).toBe(true)
    const reporter = vi.mocked(onFCP).mock.calls[0]![0]
    reporter(sampleMetric({ name: "FCP", value: 1200 }) as never)
    expect(logDebug).toHaveBeenCalledWith(
      "[web-vitals] FCP",
      expect.objectContaining({ value: 1200 })
    )
  })

  it("is idempotent — a second init does not re-register", () => {
    initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))
    expect(initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))).toBe(
      true
    )
    expect(onCLS).toHaveBeenCalledOnce()
  })

  it("reportBootstrapTTI returns false before init and reports rated metrics after", () => {
    expect(reportBootstrapTTI(1000)).toBe(false)
    initWebVitals(enabledEnv())
    expect(reportBootstrapTTI(1000)).toBe(true)
    expect(logDebug).toHaveBeenLastCalledWith(
      "[web-vitals] APP_TTI",
      expect.objectContaining({ rating: "good" })
    )
    reportBootstrapTTI(5000)
    expect(logDebug).toHaveBeenLastCalledWith(
      "[web-vitals] APP_TTI",
      expect.objectContaining({ rating: "needs-improvement" })
    )
    reportBootstrapTTI(9000)
    expect(logDebug).toHaveBeenLastCalledWith(
      "[web-vitals] APP_TTI",
      expect.objectContaining({ rating: "poor" })
    )
  })

  it("keeps exact CWV threshold boundaries inclusive", () => {
    initWebVitals(enabledEnv())
    expect(reportBootstrapTTI(3800)).toBe(true)
    expect(logDebug).toHaveBeenLastCalledWith(
      "[web-vitals] APP_TTI",
      expect.objectContaining({ rating: "good" })
    )
    expect(reportBootstrapTTI(7300)).toBe(true)
    expect(logDebug).toHaveBeenLastCalledWith(
      "[web-vitals] APP_TTI",
      expect.objectContaining({ rating: "needs-improvement" })
    )
  })

  it("exposes deterministic metric and navigation helper contracts", () => {
    expect(resolveRating(3800, [3800, 7300])).toBe("good")
    expect(resolveRating(7300, [3800, 7300])).toBe("needs-improvement")
    expect(resolveRating(7301, [3800, 7300])).toBe("poor")

    vi.stubGlobal("performance", {
      getEntriesByType: vi.fn(() => [{ type: "reload" }]),
    })
    expect(resolveNavigationType()).toBe("reload")
    const metric = createCustomMetric("APP_TTI", 100, [3800, 7300])
    expect(metric).toEqual(
      expect.objectContaining({
        name: "APP_TTI",
        value: 100,
        delta: 100,
        rating: "good",
        entries: [],
        navigationType: "reload",
        navigationId: 0,
      })
    )
    expect(metric.id).toMatch(/^APP_TTI-\d+$/)
  })

  it("fails closed for malformed same-origin URLs", () => {
    expect(isSameOriginEndpoint("/api/v1/cwv")).toBe(true)
    expect(isSameOriginEndpoint("http://[invalid")).toBe(false)
    expect(isSameOriginEndpoint("https://metrics.example/v1")).toBe(false)
  })
})
