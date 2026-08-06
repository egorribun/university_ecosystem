import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("web-vitals", () => ({
  onCLS: vi.fn(),
  onFCP: vi.fn(),
  onFID: vi.fn(),
  onINP: vi.fn(),
  onLCP: vi.fn(),
  onTTFB: vi.fn(),
}))

vi.mock("@/app/logger", () => ({ logDebug: vi.fn(), logError: vi.fn() }))

import { initWebVitals, reportBootstrapTTI, resetWebVitalsForTesting } from "@/app/webVitals"

const enabledEndpointEnv = {
  DEV: false,
  MODE: "production",
  VITE_ENABLE_WEB_VITALS: "true",
  VITE_WEB_VITALS_ENDPOINT: "https://metrics.test/vitals",
} as never

const readLastBeacon = async (sendBeacon: ReturnType<typeof vi.fn>) => {
  const blob = sendBeacon.mock.calls.at(-1)?.[1] as { parts: string[] }
  return JSON.parse(blob.parts[0]!) as { navigationType: string }
}

beforeEach(() => {
  resetWebVitalsForTesting()
  vi.clearAllMocks()
})

afterEach(() => {
  resetWebVitalsForTesting()
  vi.unstubAllGlobals()
})

describe("webVitals — navigation and reporter fallbacks", () => {
  it("falls back to navigate when performance is unavailable or has no entry", async () => {
    const sendBeacon = vi.fn(() => true)
    class TestBlob {
      constructor(readonly parts: string[]) {}
    }
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    vi.stubGlobal("Blob", TestBlob)
    vi.stubGlobal("performance", undefined)

    initWebVitals(enabledEndpointEnv)
    expect(reportBootstrapTTI(100)).toBe(true)
    expect((await readLastBeacon(sendBeacon)).navigationType).toBe("navigate")

    resetWebVitalsForTesting()
    vi.clearAllMocks()
    vi.stubGlobal("performance", { getEntriesByType: undefined })
    initWebVitals(enabledEndpointEnv)
    expect(reportBootstrapTTI(100)).toBe(true)
    expect((await readLastBeacon(sendBeacon)).navigationType).toBe("navigate")

    resetWebVitalsForTesting()
    vi.clearAllMocks()
    vi.stubGlobal("performance", { getEntriesByType: vi.fn(() => []) })
    initWebVitals(enabledEndpointEnv)
    expect(reportBootstrapTTI(100)).toBe(true)
    expect((await readLastBeacon(sendBeacon)).navigationType).toBe("navigate")
  })

  it("normalizes back-forward navigation and preserves other navigation types", async () => {
    const sendBeacon = vi.fn(() => true)
    class TestBlob {
      constructor(readonly parts: string[]) {}
    }
    vi.stubGlobal("navigator", { ...navigator, sendBeacon })
    vi.stubGlobal("Blob", TestBlob)
    vi.stubGlobal("performance", {
      getEntriesByType: vi.fn(() => [{ type: "back_forward" }]),
    })

    initWebVitals(enabledEndpointEnv)
    expect(reportBootstrapTTI(100)).toBe(true)
    expect((await readLastBeacon(sendBeacon)).navigationType).toBe("back-forward")

    resetWebVitalsForTesting()
    vi.clearAllMocks()
    vi.stubGlobal("performance", {
      getEntriesByType: vi.fn(() => [{ type: "reload" }]),
    })
    initWebVitals(enabledEndpointEnv)
    expect(reportBootstrapTTI(100)).toBe(true)
    expect((await readLastBeacon(sendBeacon)).navigationType).toBe("reload")
  })

  it("returns false when no endpoint and no console reporter are available", () => {
    const originalConsole = globalThis.console
    vi.stubGlobal("console", undefined)

    expect(
      initWebVitals({ DEV: false, MODE: "production", VITE_ENABLE_WEB_VITALS: "true" } as never)
    ).toBe(false)

    vi.stubGlobal("console", originalConsole)
  })
})
