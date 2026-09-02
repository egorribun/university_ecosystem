import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@sentry/react", () => ({
  init: vi.fn(),
}))
vi.mock("../app/telemetry", () => ({
  initTelemetry: vi.fn(),
}))
vi.mock("../app/logger", () => ({
  logInfo: vi.fn(),
}))

import * as Sentry from "@sentry/react"
import { initTelemetry } from "../app/telemetry"
import { logInfo } from "../app/logger"
import { initObservability, resetObservabilityForTesting } from "../app/observability"

describe("initObservability", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetObservabilityForTesting()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("initializes Sentry when DSN is provided outside of development", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_ENVIRONMENT: "production",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(true)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: "https://examplePublicKey.ingest.sentry.io/123",
        environment: "production",
        enabled: true,
      })
    )
  })

  it("passes through the release identifier when provided", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_ENVIRONMENT: "production",
      VITE_APP_RELEASE: "2024.04.15+sha.abcdef",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(true)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        release: "2024.04.15+sha.abcdef",
      })
    )
  })

  it("skips initialization when DSN is missing", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(false)
    expect(Sentry.init).not.toHaveBeenCalled()
    expect(logInfo).not.toHaveBeenCalled()
  })

  it("skips initialization in development", () => {
    const result = initObservability({
      DEV: true,
      PROD: false,
      BASE_URL: "http://localhost",
      MODE: "development",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(false)
    expect(Sentry.init).not.toHaveBeenCalled()
    expect(logInfo).toHaveBeenCalledWith(
      "Sentry disabled in development mode; skipping initialization"
    )
  })

  it("skips development logging when the console is unavailable", () => {
    vi.stubGlobal("console", undefined)

    const result = initObservability({
      DEV: true,
      PROD: false,
      BASE_URL: "http://localhost",
      MODE: "development",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(false)
    expect(Sentry.init).not.toHaveBeenCalled()
    expect(logInfo).not.toHaveBeenCalled()
  })

  it("normalizes valid, invalid, and out-of-range sample rates", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "0.25",
      VITE_SENTRY_PROFILES_SAMPLE_RATE: "2",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(true)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        environment: "production",
        tracesSampleRate: 0.25,
        profilesSampleRate: undefined,
      })
    )
  })

  it("accepts exact sample-rate boundaries and rejects empty values", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "0",
      VITE_SENTRY_PROFILES_SAMPLE_RATE: "1",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(true)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({ tracesSampleRate: 0, profilesSampleRate: 1 })
    )

    resetObservabilityForTesting()
    vi.clearAllMocks()
    const emptyResult = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "",
      VITE_SENTRY_PROFILES_SAMPLE_RATE: "-0.1",
    } as unknown as ImportMetaEnv)

    expect(emptyResult).toBe(true)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({ tracesSampleRate: undefined, profilesSampleRate: undefined })
    )
  })

  it("rejects a non-numeric sample rate and returns true on repeated initialization", () => {
    const env = {
      DEV: false,
      PROD: false,
      BASE_URL: "http://localhost",
      MODE: "production",
      VITE_SENTRY_DSN: "https://examplePublicKey.ingest.sentry.io/123",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "not-a-number",
    } as unknown as ImportMetaEnv

    expect(initObservability(env)).toBe(true)
    expect(initObservability(env)).toBe(true)
    expect(Sentry.init).toHaveBeenCalledTimes(1)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        environment: "development",
        tracesSampleRate: undefined,
        profilesSampleRate: undefined,
      })
    )
    expect(initTelemetry).toHaveBeenCalledTimes(1)
  })
})
