import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

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

describe("RxDBContext closure", () => {
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

  it("does not publish a resolved database after the provider unmounts", async () => {
    let resolveDatabase: (database: unknown) => void = () => undefined
    mockGetDatabase.mockReturnValue(
      new Promise((resolve) => {
        resolveDatabase = resolve
      })
    )
    const { unmount } = render(
      <RxDBProvider>
        <Consumer />
      </RxDBProvider>
    )
    unmount()
    resolveDatabase({ schedule: {} })
    await Promise.resolve()
    expect(mockGetDatabase).toHaveBeenCalledOnce()
  })
})
