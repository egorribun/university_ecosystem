import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

vi.mock("web-vitals", () => ({
  onCLS: vi.fn(),
  onFCP: vi.fn(),
  onFID: vi.fn(),
  onINP: vi.fn(),
  onLCP: vi.fn(),
  onTTFB: vi.fn(),
}))
vi.mock("@/app/logger", () => ({ logDebug: vi.fn(), logError: vi.fn() }))

import { onCLS, onFCP, onFID, onINP, onLCP, onTTFB } from "web-vitals"
import { logDebug } from "@/app/logger"
import { initWebVitals, reportBootstrapTTI, resetWebVitalsForTesting } from "@/app/webVitals"

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

  it("returns false when the feature flag is not enabled", () => {
    expect(initWebVitals(PROD_BASE)).toBe(false)
    expect(initWebVitals({ ...PROD_BASE, VITE_ENABLE_WEB_VITALS: "nope" } as never)).toBe(false)
  })

  it("registers all six web-vital callbacks when enabled with an endpoint", () => {
    const sendBeacon = vi.fn(() => true)
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    expect(initWebVitals(enabledEnv({ VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/v" }))).toBe(
      true
    )
    for (const fn of [onCLS, onFCP, onFID, onINP, onLCP, onTTFB]) {
      expect(fn).toHaveBeenCalledOnce()
    }
    const reporter = vi.mocked(onCLS).mock.calls[0]![0]
    reporter(sampleMetric({ label: "main" }) as never)
    expect(sendBeacon).toHaveBeenCalledWith("https://metrics.test/v", expect.any(Blob))
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
})
