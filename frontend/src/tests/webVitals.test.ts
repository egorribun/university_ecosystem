import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("web-vitals", () => ({
  onCLS: vi.fn(),
  onFCP: vi.fn(),
  onINP: vi.fn(),
  onLCP: vi.fn(),
  onTTFB: vi.fn(),
}))

import { onCLS, onFCP, onINP, onLCP, onTTFB } from "web-vitals"
import { initWebVitals, resetWebVitalsForTesting } from "../app/webVitals"

type MutableEnv = ImportMetaEnv & {
  VITE_ENABLE_WEB_VITALS?: string
  VITE_WEB_VITALS_ENDPOINT?: string
}

function createEnv(overrides: Partial<MutableEnv> = {}): MutableEnv {
  return {
    BASE_URL: "http://localhost",
    DEV: false,
    PROD: true,
    MODE: "production",
    VITE_ENABLE_WEB_VITALS: "true",
    ...overrides,
  } as MutableEnv
}

describe("initWebVitals", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetWebVitalsForTesting()
  })

  it("registers listeners when enabled in production", () => {
    const result = initWebVitals(createEnv())

    expect(result).toBe(true)
    expect(onCLS).toHaveBeenCalledTimes(1)
    expect(onFCP).toHaveBeenCalledTimes(1)
    expect(onINP).toHaveBeenCalledTimes(1)
    expect(onLCP).toHaveBeenCalledTimes(1)
    expect(onTTFB).toHaveBeenCalledTimes(1)
  })

  it("skips initialization when the feature flag is disabled", () => {
    const result = initWebVitals(createEnv({ VITE_ENABLE_WEB_VITALS: "false" }))

    expect(result).toBe(false)
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("does not run in development mode", () => {
    const result = initWebVitals(createEnv({ DEV: true, PROD: false, MODE: "development" }))

    expect(result).toBe(false)
    expect(onCLS).not.toHaveBeenCalled()
  })

  it("skips gracefully when the DOM is unavailable", () => {
    vi.stubGlobal("document", undefined)

    try {
      const result = initWebVitals(createEnv())
      expect(result).toBe(false)
      expect(onCLS).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
