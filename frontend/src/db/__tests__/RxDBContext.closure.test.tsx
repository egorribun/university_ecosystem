import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { mockGetDatabase } = vi.hoisted(() => ({ mockGetDatabase: vi.fn() }))

vi.mock("../index", () => ({ getDatabase: mockGetDatabase }))

import { RxDBProvider, useRxDB } from "../RxDBContext"

function Consumer() {
  const db = useRxDB()
  return <output data-testid="db-state">{db ? "ready" : "empty"}</output>
}

beforeEach(() => {
  mockGetDatabase.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function captureInitializationTimer() {
  let timerCallback: (() => void) | undefined
  const requestIdleSpy = vi.fn(() => 19)
  vi.stubGlobal("requestIdleCallback", requestIdleSpy)
  vi.stubGlobal("cancelIdleCallback", vi.fn())
  const setTimeoutSpy = vi.spyOn(window, "setTimeout").mockImplementation(((
    callback: TimerHandler,
    delay?: number
  ) => {
    if (delay === 10_000) timerCallback = callback as () => void
    return 73
  }) as typeof window.setTimeout)
  return { setTimeoutSpy, requestIdleSpy, timerCallback: () => timerCallback?.() }
}

describe("RxDBContext closure", () => {
  it("defers the offline database behind a deterministic ten-second timer", async () => {
    const database = { schedule: {} }
    mockGetDatabase.mockResolvedValue(database)
    const { setTimeoutSpy, requestIdleSpy, timerCallback } = captureInitializationTimer()

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    expect(mockGetDatabase).not.toHaveBeenCalled()
    expect(requestIdleSpy).not.toHaveBeenCalled()
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 10_000)
    await act(async () => {
      timerCallback()
      await Promise.resolve()
    })
    expect(screen.getByTestId("db-state")).toHaveTextContent("ready")
  })

  it("publishes the initialized database through the provider", async () => {
    const database = { schedule: {} }
    mockGetDatabase.mockResolvedValue(database)
    const { timerCallback } = captureInitializationTimer()

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    await act(async () => {
      timerCallback()
      await Promise.resolve()
    })
    expect(screen.getByTestId("db-state")).toHaveTextContent("ready")
  })

  it("keeps the context empty and logs initialization failures", async () => {
    const error = new Error("database unavailable")
    mockGetDatabase.mockRejectedValue(error)
    const { timerCallback } = captureInitializationTimer()
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    await act(async () => {
      timerCallback()
      await Promise.resolve()
    })
    expect(consoleError).toHaveBeenCalledWith("[RxDB] Initialization failed:", error)
    expect(screen.getByTestId("db-state")).toHaveTextContent("empty")
    consoleError.mockRestore()
  })

  it("cancels deferred initialization when the provider unmounts", async () => {
    const timerHandle = 41 as unknown as ReturnType<typeof window.setTimeout>
    const setTimeoutSpy = vi.spyOn(window, "setTimeout").mockReturnValue(timerHandle)
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout").mockImplementation(() => undefined)
    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )
    unmount()

    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 10_000)
    expect(clearTimeoutSpy).toHaveBeenCalledWith(timerHandle)
    expect(mockGetDatabase).not.toHaveBeenCalled()
  })
})
