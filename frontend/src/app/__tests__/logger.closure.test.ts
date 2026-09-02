import { describe, expect, it, vi } from "vitest"

vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  setTag: vi.fn(),
}))

import * as Sentry from "@sentry/react"
import {
  logDebug,
  logError,
  logInfo,
  logWarning,
  setLoggerClient,
  setTraceContext,
} from "@/app/logger"

const captureException = vi.mocked(Sentry.captureException)
const captureMessage = vi.mocked(Sentry.captureMessage)
const setTag = vi.mocked(Sentry.setTag)

function resetLoggerMocks() {
  captureException.mockReset()
  captureMessage.mockReset()
  setTag.mockReset()
  setLoggerClient({ captureException, captureMessage, setTag })
  setTraceContext(null)
}

describe("logger closure paths", () => {
  it("normalizes errors and forwards trace-aware exception context", () => {
    resetLoggerMocks()
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    const error = new Error("boom")
    const circular: Record<string, unknown> = {}
    circular.self = circular

    setTraceContext(" trace-123 ")
    logError(error, "message", 4, true, null, { safe: true }, circular, undefined, Symbol("x"))

    expect(setTag).toHaveBeenCalledWith("trace_id", " trace-123 ")
    expect(captureException).toHaveBeenCalledOnce()
    expect(captureException.mock.calls[0]?.[0]).toBe(error)
    expect(captureException.mock.calls[0]?.[1]).toMatchObject({
      tags: { logger: "app", trace_id: " trace-123 ", level: "error" },
    })
    const context = captureException.mock.calls[0]?.[1] as
      { extra?: Record<string, unknown> } | undefined
    const normalized = context?.extra?.logArgs as unknown[]
    expect(normalized[0]).toMatchObject({ name: "Error", message: "boom" })
    expect(normalized.slice(1)).toEqual([
      "message",
      4,
      true,
      null,
      { safe: true },
      "[object Object]",
      "undefined",
      "Symbol(x)",
    ])
    expect(consoleError).toHaveBeenCalledOnce()
  })

  it("uses message capture when no Error is present and logs warnings/info/debug", () => {
    resetLoggerMocks()
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const consoleInfo = vi.spyOn(console, "info").mockImplementation(() => {})
    const consoleLog = vi.spyOn(console, "log").mockImplementation(() => {})

    setTraceContext("   ")
    logError("plain error")
    logError(42)
    logError("")
    logWarning("warning")
    logWarning(42)
    logInfo("info")
    logDebug("debug")

    expect(setTag).toHaveBeenCalledWith("trace_id", "")
    expect(captureException).not.toHaveBeenCalled()
    expect(captureMessage).toHaveBeenCalledWith("plain error", "error")
    expect(captureMessage).not.toHaveBeenCalledWith("", "error")
    expect(captureMessage).not.toHaveBeenCalledWith(42, "error")
    expect(captureMessage).toHaveBeenCalledWith("warning", "warning")
    expect(consoleError).toHaveBeenCalledTimes(3)
    expect(consoleWarn).toHaveBeenCalledTimes(2)
    expect(consoleInfo).toHaveBeenCalledWith("info")
    expect(consoleLog).toHaveBeenCalledWith("debug")
  })

  it("fails closed when Sentry forwarding throws", () => {
    resetLoggerMocks()
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    const sentryError = new Error("sentry down")
    const warningError = new Error("warning down")
    const captureExceptionThrow = vi.fn(() => {
      throw sentryError
    })
    const captureMessageThrow = vi.fn(() => {
      throw warningError
    })
    setLoggerClient({
      captureException: captureExceptionThrow,
      captureMessage: captureMessageThrow,
    })

    logError(new Error("app error"))
    logWarning("app warning")

    expect(consoleWarn).toHaveBeenCalledWith(
      "[logger] Failed to forward error to Sentry",
      sentryError
    )
    expect(consoleWarn).toHaveBeenCalledWith(
      "[logger] Failed to forward warning to Sentry",
      warningError
    )
    expect(consoleError).toHaveBeenCalledOnce()
  })

  it("supports a client without setTag and clears trace context", () => {
    resetLoggerMocks()
    setLoggerClient({ setTag: undefined })
    expect(() => setTraceContext(undefined)).not.toThrow()
    expect(() => logError("still logged")).not.toThrow()
  })

  it("normalizes non-string trace ids and keeps message fallback guards strict", () => {
    resetLoggerMocks()
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    setTraceContext(123 as unknown as string)
    logError(42)

    expect(setTag).toHaveBeenCalledWith("trace_id", "123")
    expect(captureMessage).not.toHaveBeenCalled()
    expect(consoleError).toHaveBeenCalledWith(42)
  })

  it("continues safely when a console method and Sentry message capture are unavailable", () => {
    resetLoggerMocks()
    const originalInfo = Object.getOwnPropertyDescriptor(console, "info")
    const originalError = Object.getOwnPropertyDescriptor(console, "error")
    Object.defineProperty(console, "info", { configurable: true, value: undefined })
    Object.defineProperty(console, "error", { configurable: true, value: undefined })
    setLoggerClient({ captureMessage: undefined })

    try {
      expect(() => logInfo("not writable")).not.toThrow()
      expect(() => logError(42)).not.toThrow()
    } finally {
      if (originalInfo) Object.defineProperty(console, "info", originalInfo)
      if (originalError) Object.defineProperty(console, "error", originalError)
      setLoggerClient({ captureMessage })
    }
  })

  it("suppresses debug output outside development", () => {
    resetLoggerMocks()
    const consoleLog = vi.spyOn(console, "log").mockImplementation(() => {})
    vi.stubEnv("DEV", false)

    try {
      logDebug("production detail")
      expect(consoleLog).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it("does not add a trace tag when the trace context is only whitespace", () => {
    resetLoggerMocks()
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    setTag.mockClear()
    setTraceContext("   ")

    logError(new Error("without trace"))

    expect(setTag).toHaveBeenCalledWith("trace_id", "")
    expect(captureException.mock.calls.at(-1)?.[1]).toMatchObject({
      tags: { logger: "app", level: "error" },
    })
    expect(captureException.mock.calls.at(-1)?.[1]).not.toMatchObject({
      tags: { trace_id: expect.anything() },
    })
    expect(consoleError).toHaveBeenCalledOnce()
  })

  it("keeps logger fallbacks inert when optional Sentry methods are unavailable", () => {
    resetLoggerMocks()
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    setLoggerClient({ captureException: undefined, captureMessage: undefined })

    expect(() => logError("plain error")).not.toThrow()
    expect(() => logWarning("plain warning")).not.toThrow()

    expect(consoleWarn).not.toHaveBeenCalledWith(
      "[logger] Failed to forward error to Sentry",
      expect.anything()
    )
    expect(consoleWarn).not.toHaveBeenCalledWith(
      "[logger] Failed to forward warning to Sentry",
      expect.anything()
    )
    expect(consoleError).toHaveBeenCalledWith("plain error")
  })
})
