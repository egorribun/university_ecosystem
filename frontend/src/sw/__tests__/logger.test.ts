import { afterEach, describe, expect, it, vi } from "vitest"

import { error, log, warn } from "../logger"

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("service-worker logger", () => {
  it("emits warnings and errors only in development", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)

    vi.stubEnv("DEV", true)
    log("development")
    warn("warning", 1)
    error("failure", 2)
    expect(warnSpy).toHaveBeenCalledWith("[SW]", "warning", 1)
    expect(errorSpy).toHaveBeenCalledWith("[SW]", "failure", 2)

    vi.stubEnv("DEV", false)
    log("production")
    warn("hidden warning")
    error("hidden error")
    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(errorSpy).toHaveBeenCalledTimes(1)
  })
})
