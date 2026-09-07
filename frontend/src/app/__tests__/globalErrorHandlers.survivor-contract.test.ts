import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/app/logger", () => ({
  logError: vi.fn(),
  logWarning: vi.fn(),
  logInfo: vi.fn(),
}))

type Listener = (event: unknown) => void

describe("global error handler serialization guard", () => {
  beforeEach(async () => {
    const module = await import("../globalErrorHandlers")
    module.resetGlobalErrorHandlersForTesting()
    const logger = await import("@/app/logger")
    vi.mocked(logger.logError).mockClear()
    vi.mocked(logger.logWarning).mockClear()
    vi.mocked(logger.logInfo).mockClear()
  })

  it("keeps primitive rejection reasons unchanged instead of cloning them", async () => {
    const { initGlobalErrorHandlers } = await import("../globalErrorHandlers")
    const listeners: Record<string, Listener[]> = {}
    const target = {
      addEventListener: (type: string, listener: Listener) => {
        listeners[type] = [...(listeners[type] ?? []), listener]
      },
      removeEventListener: () => undefined,
    } as unknown as Parameters<typeof initGlobalErrorHandlers>[0]
    initGlobalErrorHandlers(target)

    const rejectionHandler = listeners.unhandledrejection?.[0]
    expect(rejectionHandler).toBeTypeOf("function")

    const reasons = [undefined, null, "plain-value", 42, false] as const
    for (const reason of reasons) {
      rejectionHandler?.({ reason } as PromiseRejectionEvent)
    }

    const { logWarning } = await import("@/app/logger")
    expect(logWarning).toHaveBeenCalledTimes(reasons.length)
    reasons.forEach((reason, index) => {
      expect(logWarning).toHaveBeenNthCalledWith(
        index + 1,
        "[GlobalErrors] Promise rejected with a non-error value",
        reason
      )
    })
  })
})
