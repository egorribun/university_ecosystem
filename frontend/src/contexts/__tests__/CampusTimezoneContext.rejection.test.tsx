import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const refresh = vi.hoisted(() => vi.fn())
vi.mock("@/api/hooks/campusConfig", () => ({ fetchCampusTimezone: refresh }))

import { CampusTimezoneProvider, useCampusTimezone } from "@/contexts/CampusTimezoneContext"

function Probe() {
  return <output>{useCampusTimezone() ?? "unavailable"}</output>
}

function deferred<T>() {
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((_resolve, rejectPromise) => {
    reject = rejectPromise
  })
  return { promise, reject }
}

afterEach(() => {
  cleanup()
  refresh.mockReset()
})

describe("CampusTimezoneProvider rejected refresh defense", () => {
  it("stays unavailable when an active refresh rejects", async () => {
    const pending = deferred<string | null>()
    refresh.mockReturnValueOnce(pending.promise)
    render(
      <CampusTimezoneProvider timeZone={null}>
        <Probe />
      </CampusTimezoneProvider>
    )
    expect(screen.getByText("unavailable")).toBeInTheDocument()
    await act(async () => {
      pending.reject(new Error("synthetic refresh rejection"))
      await pending.promise.catch(() => undefined)
      await Promise.resolve()
    })
    expect(screen.getByText("unavailable")).toBeInTheDocument()
  })

  it("ignores a rejected refresh after the provider unmounts", async () => {
    const pending = deferred<string | null>()
    refresh.mockReturnValueOnce(pending.promise)
    const view = render(
      <CampusTimezoneProvider timeZone={null}>
        <Probe />
      </CampusTimezoneProvider>
    )
    view.unmount()
    await act(async () => {
      pending.reject(new Error("late refresh rejection"))
      await pending.promise.catch(() => undefined)
      await Promise.resolve()
    })
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument()
  })
})
