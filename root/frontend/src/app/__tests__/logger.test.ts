import { describe, expect, it, beforeEach, afterEach, vi, type Mock } from "vitest"

vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
  captureMessage: vi.fn(),
}))

let captureException: Mock
let captureMessage: Mock

const originalConsoleError = console.error
const originalConsoleWarn = console.warn

beforeEach(async () => {
  const sentry = await import("@sentry/react")
  captureException = sentry.captureException as unknown as Mock
  captureMessage = sentry.captureMessage as unknown as Mock
  captureException.mockClear()
  captureMessage.mockClear()
  console.error = vi.fn()
  console.warn = vi.fn()
})

afterEach(() => {
  console.error = originalConsoleError
  console.warn = originalConsoleWarn
})

describe("logger", () => {
  it("captures errors and forwards them to the console", async () => {
    const { logError } = await import("../logger")
    const error = new Error("logger failure")

    logError("Boom", error)

    expect(captureException).toHaveBeenCalledWith(
      error,
      expect.objectContaining({
        extra: expect.any(Object),
        tags: expect.objectContaining({ logger: "app", level: "error" }),
      })
    )
    expect(console.error).toHaveBeenCalledWith("Boom", error)
  })

  it("captures messages when no error object is provided", async () => {
    const { logError } = await import("../logger")

    logError("Only message")

    expect(captureMessage).toHaveBeenCalledWith("Only message", "error")
    expect(console.error).toHaveBeenCalledWith("Only message")
  })

  it("captures warning messages", async () => {
    const { logWarning } = await import("../logger")

    logWarning("Careful!", { context: true })

    expect(captureMessage).toHaveBeenCalledWith("Careful!", "warning")
    expect(console.warn).toHaveBeenCalledWith("Careful!", { context: true })
  })
})
