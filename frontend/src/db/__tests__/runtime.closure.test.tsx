import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { getDatabase } = vi.hoisted(() => ({ getDatabase: vi.fn() }))

vi.mock("../index", () => ({ getDatabase }))

import { getDatabaseLazily } from "../lazy"
import { RxDBProvider, useRxDB } from "../RxDBContext"

function Consumer() {
  return <output data-testid="db-state">{useRxDB() ? "ready" : "empty"}</output>
}

beforeEach(() => {
  getDatabase.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("RxDB runtime closure", () => {
  it("loads the IndexedDB module only when the lazy boundary is invoked", async () => {
    const database = { schedule: {} }
    getDatabase.mockResolvedValue(database)

    await expect(getDatabaseLazily()).resolves.toBe(database)
    expect(getDatabase).toHaveBeenCalledOnce()
  })

  it("ignores a cancelled idle callback even if the browser delivers it late", () => {
    let idleCallback: IdleRequestCallback | undefined
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn((callback: IdleRequestCallback) => {
        idleCallback = callback
        return 37
      })
    )
    vi.stubGlobal("cancelIdleCallback", vi.fn())

    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )
    unmount()
    act(() => idleCallback?.({ didTimeout: true, timeRemaining: () => 0 }))

    expect(getDatabase).not.toHaveBeenCalled()
  })

  it("clears fallback initialization when unmounted before its timer fires", () => {
    let timerCallback: (() => void) | undefined
    const setTimeoutSpy = vi.spyOn(window, "setTimeout").mockImplementation(((
      callback: TimerHandler
    ) => {
      timerCallback = callback as () => void
      return 73
    }) as typeof window.setTimeout)
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout").mockImplementation(() => undefined)

    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )
    unmount()
    act(() => timerCallback?.())

    expect(setTimeoutSpy).toHaveBeenCalledOnce()
    expect(clearTimeoutSpy).toHaveBeenCalledWith(73)
    expect(getDatabase).not.toHaveBeenCalled()
  })

  it("does not publish a database that resolves after provider cleanup", async () => {
    let resolveDatabase: ((database: object) => void) | undefined
    getDatabase.mockReturnValue(
      new Promise((resolve) => {
        resolveDatabase = resolve
      })
    )
    let idleCallback: IdleRequestCallback | undefined
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn((callback: IdleRequestCallback) => {
        idleCallback = callback
        return 81
      })
    )
    vi.stubGlobal("cancelIdleCallback", vi.fn())
    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    act(() => idleCallback?.({ didTimeout: false, timeRemaining: () => 20 }))
    unmount()
    await act(async () => resolveDatabase?.({ schedule: {} }))

    expect(screen.queryByTestId("db-state")).not.toBeInTheDocument()
  })

  it("does not log a rejected initialization after provider cleanup", async () => {
    let rejectDatabase: ((error: Error) => void) | undefined
    getDatabase.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectDatabase = reject
      })
    )
    let idleCallback: IdleRequestCallback | undefined
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn((callback: IdleRequestCallback) => {
        idleCallback = callback
        return 91
      })
    )
    vi.stubGlobal("cancelIdleCallback", vi.fn())
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)
    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    act(() => idleCallback?.({ didTimeout: false, timeRemaining: () => 20 }))
    unmount()
    await act(async () => rejectDatabase?.(new Error("late failure")))

    expect(consoleError).not.toHaveBeenCalled()
  })
})
