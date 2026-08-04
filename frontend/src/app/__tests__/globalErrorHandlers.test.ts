import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"

vi.mock("@/app/logger", () => ({
  logError: vi.fn(),
  logWarning: vi.fn(),
  logInfo: vi.fn(),
}))

type Listener = (event: unknown) => void

describe("initGlobalErrorHandlers", () => {
  let listeners: Record<string, Listener[]>
  let addEventListenerMock: Mock
  let removeEventListenerMock: Mock
  let target: {
    addEventListener: typeof window.addEventListener
    removeEventListener: typeof window.removeEventListener
  }
  let logError: Mock
  let logWarning: Mock
  let logInfo: Mock

  beforeEach(async () => {
    listeners = {}
    addEventListenerMock = vi.fn((type: string, listener: Listener) => {
      listeners[type] = listeners[type] ?? []
      listeners[type]!.push(listener)
    })
    removeEventListenerMock = vi.fn((type: string, listener: Listener) => {
      listeners[type] = (listeners[type] ?? []).filter((entry) => entry !== listener)
    })
    target = {
      addEventListener: addEventListenerMock as unknown as typeof window.addEventListener,
      removeEventListener: removeEventListenerMock as unknown as typeof window.removeEventListener,
    }
    const logger = await import("@/app/logger")
    logError = logger.logError as unknown as Mock
    logWarning = logger.logWarning as unknown as Mock
    logInfo = logger.logInfo as unknown as Mock
    logError.mockClear()
    logWarning.mockClear()
    logInfo.mockClear()
    const module = await import("../globalErrorHandlers")
    module.resetGlobalErrorHandlersForTesting()
  })

  afterEach(async () => {
    const module = await import("../globalErrorHandlers")
    module.resetGlobalErrorHandlersForTesting()
  })

  it("registers listeners and logs unhandled errors", async () => {
    const { initGlobalErrorHandlers } = await import("../globalErrorHandlers")
    expect(initGlobalErrorHandlers(target)).toBe(true)
    expect(addEventListenerMock).toHaveBeenCalledTimes(2)
    expect(logInfo).toHaveBeenCalledWith("[GlobalErrors] Handlers registered", expect.any(Object))

    const rejectionHandler = listeners.unhandledrejection?.[0]
    expect(rejectionHandler).toBeTypeOf("function")
    const error = new Error("boom")
    rejectionHandler?.({ reason: error } as PromiseRejectionEvent)
    expect(logError).toHaveBeenCalledWith("[GlobalErrors] Unhandled promise rejection", error)

    const errorHandler = listeners.error?.[0]
    expect(errorHandler).toBeTypeOf("function")
    const thrown = new Error("oops")
    errorHandler?.({ error: thrown } as ErrorEvent)
    expect(logError).toHaveBeenCalledWith("[GlobalErrors] Unhandled error event", thrown)
  })

  it("logs axios-specific rejections and non-error reasons", async () => {
    const { initGlobalErrorHandlers } = await import("../globalErrorHandlers")
    initGlobalErrorHandlers(target)

    const rejectionHandler = listeners.unhandledrejection?.[0]
    const axiosError = Object.assign(new Error("axios"), { isAxiosError: true })
    rejectionHandler?.({ reason: axiosError } as PromiseRejectionEvent)
    expect(logError).toHaveBeenCalledWith("[GlobalErrors] Unhandled Axios error", axiosError)

    rejectionHandler?.({ reason: { data: "bad" } } as PromiseRejectionEvent)
    expect(logWarning).toHaveBeenCalledWith(
      "[GlobalErrors] Promise rejected with a non-error value",
      expect.objectContaining({ data: "bad" })
    )

    rejectionHandler?.({ reason: "plain-value" } as PromiseRejectionEvent)
    expect(logWarning).toHaveBeenCalledWith(
      "[GlobalErrors] Promise rejected with a non-error value",
      "plain-value"
    )

    const cyclic: Record<string, unknown> = {}
    cyclic.self = cyclic
    rejectionHandler?.({ reason: cyclic } as PromiseRejectionEvent)
    expect(logWarning).toHaveBeenCalledWith(
      "[GlobalErrors] Promise rejected with a non-error value",
      expect.objectContaining({ self: cyclic })
    )
  })

  it("is idempotent and reports non-Error window events", async () => {
    const { initGlobalErrorHandlers } = await import("../globalErrorHandlers")
    expect(initGlobalErrorHandlers(target)).toBe(true)
    expect(initGlobalErrorHandlers(target)).toBe(true)
    expect(addEventListenerMock).toHaveBeenCalledTimes(2)

    const errorHandler = listeners.error?.[0]
    errorHandler?.({
      error: null,
      message: "script failed",
      filename: "app.js",
      lineno: 12,
      colno: 7,
    } as ErrorEvent)
    expect(logError).toHaveBeenCalledWith("[GlobalErrors] Error event", "script failed", {
      filename: "app.js",
      lineno: 12,
      colno: 7,
    })
  })

  it("returns false without a browser target", async () => {
    const { initGlobalErrorHandlers, resetGlobalErrorHandlersForTesting } =
      await import("../globalErrorHandlers")
    vi.stubGlobal("window", undefined)
    expect(initGlobalErrorHandlers()).toBe(false)
    resetGlobalErrorHandlersForTesting()
    vi.unstubAllGlobals()
  })

  it("removes listeners when reset is invoked", async () => {
    const { initGlobalErrorHandlers, resetGlobalErrorHandlersForTesting } =
      await import("../globalErrorHandlers")
    initGlobalErrorHandlers(target)
    expect(addEventListenerMock).toHaveBeenCalledTimes(2)

    resetGlobalErrorHandlersForTesting()
    expect(removeEventListenerMock).toHaveBeenCalledTimes(2)
    resetGlobalErrorHandlersForTesting()
  })
})
