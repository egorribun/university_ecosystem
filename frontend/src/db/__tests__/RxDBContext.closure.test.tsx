import { act, render, screen, waitFor } from "@testing-library/react"
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

describe("RxDBContext closure", () => {
  it("defers the offline database until the browser is idle", async () => {
    const database = { schedule: {} }
    mockGetDatabase.mockResolvedValue(database)
    let idleCallback: IdleRequestCallback | undefined
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn((callback: IdleRequestCallback) => {
        idleCallback = callback
        return 23
      })
    )
    vi.stubGlobal("cancelIdleCallback", vi.fn())

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    expect(mockGetDatabase).not.toHaveBeenCalled()
    await act(async () => {
      idleCallback?.({ didTimeout: false, timeRemaining: () => 50 })
    })
    await waitFor(() => expect(screen.getByTestId("db-state")).toHaveTextContent("ready"))
  })

  it("publishes the initialized database through the provider", async () => {
    const database = { schedule: {} }
    mockGetDatabase.mockResolvedValue(database)

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    await waitFor(() => expect(screen.getByTestId("db-state")).toHaveTextContent("ready"))
  })

  it("keeps the context empty and logs initialization failures", async () => {
    const error = new Error("database unavailable")
    mockGetDatabase.mockRejectedValue(error)
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)

    render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )

    await waitFor(() =>
      expect(consoleError).toHaveBeenCalledWith("[RxDB] Initialization failed:", error)
    )
    expect(screen.getByTestId("db-state")).toHaveTextContent("empty")
    consoleError.mockRestore()
  })

  it("cancels deferred initialization when the provider unmounts", async () => {
    const cancelIdleCallback = vi.fn()
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn(() => 41)
    )
    vi.stubGlobal("cancelIdleCallback", cancelIdleCallback)
    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )
    unmount()

    expect(cancelIdleCallback).toHaveBeenCalledWith(41)
    expect(mockGetDatabase).not.toHaveBeenCalled()
  })
})
