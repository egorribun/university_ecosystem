import { StrictMode } from "react"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { CampusTimezoneProvider, useCampusTimezone } from "@/contexts/CampusTimezoneContext"

function CampusTimezoneProbe() {
  const timeZone = useCampusTimezone()
  return <output data-testid="campus-timezone">{timeZone ?? "unavailable"}</output>
}

function response(payload: unknown): Response {
  return {
    ok: true,
    json: async () => payload,
  } as Response
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("CampusTimezoneProvider prerender recovery", () => {
  it("refreshes a prerendered null from the public config and ignores the cleaned-up StrictMode mount", async () => {
    const firstMount = deferred<Response>()
    const activeMount = deferred<Response>()
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(firstMount.promise)
      .mockReturnValueOnce(activeMount.promise)
    vi.stubGlobal("fetch", fetchMock)

    render(
      <StrictMode>
        <CampusTimezoneProvider timeZone={null}>
          <CampusTimezoneProbe />
        </CampusTimezoneProvider>
      </StrictMode>
    )

    expect(screen.getByTestId("campus-timezone")).toHaveTextContent("unavailable")
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    await act(async () => {
      activeMount.resolve(response({ campus_timezone: "Europe/Istanbul" }))
      await activeMount.promise
    })
    await waitFor(() => {
      expect(screen.getByTestId("campus-timezone")).toHaveTextContent("Europe/Istanbul")
    })

    await act(async () => {
      firstMount.resolve(response({ campus_timezone: "America/Los_Angeles" }))
      await firstMount.promise
      await Promise.resolve()
    })
    expect(screen.getByTestId("campus-timezone")).toHaveTextContent("Europe/Istanbul")
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/campus/config",
      expect.objectContaining({ cache: "no-store" })
    )
  })

  it("does not refetch when the root loader already supplied the campus zone", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    render(
      <StrictMode>
        <CampusTimezoneProvider timeZone="Europe/Istanbul">
          <CampusTimezoneProbe />
        </CampusTimezoneProvider>
      </StrictMode>
    )

    expect(screen.getByTestId("campus-timezone")).toHaveTextContent("Europe/Istanbul")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  const failClosedResponses: Array<[string, () => Promise<Response>]> = [
    ["a malformed zone", () => Promise.resolve(response({ campus_timezone: "Not/A_Timezone" }))],
    ["a failed request", () => Promise.reject(new Error("offline"))],
  ]

  it.each(failClosedResponses)("stays fail-closed after %s", async (_label, createResponse) => {
    const fetchMock = vi.fn().mockImplementation(createResponse)
    vi.stubGlobal("fetch", fetchMock)

    render(
      <CampusTimezoneProvider timeZone={null}>
        <CampusTimezoneProbe />
      </CampusTimezoneProvider>
    )

    expect(screen.getByTestId("campus-timezone")).toHaveTextContent("unavailable")
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByTestId("campus-timezone")).toHaveTextContent("unavailable")
  })
})
