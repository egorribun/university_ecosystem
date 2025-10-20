import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@sentry/react", () => ({
  init: vi.fn(),
}))

import * as Sentry from "@sentry/react"
import { initObservability, resetObservabilityForTesting } from "../app/observability"

describe("initObservability", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetObservabilityForTesting()
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

  it("skips initialization when DSN is missing", () => {
    const result = initObservability({
      DEV: false,
      PROD: true,
      BASE_URL: "http://localhost",
      MODE: "production",
    } as unknown as ImportMetaEnv)

    expect(result).toBe(false)
    expect(Sentry.init).not.toHaveBeenCalled()
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
  })
})
