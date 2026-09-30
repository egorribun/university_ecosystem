import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"

import { useClock } from "@/hooks/useClock"

function ClockMarkup() {
  const { hh, mm, dateStr } = useClock("en-US")
  return <p>{`${hh}:${mm}|${dateStr}`}</p>
}

describe("useClock", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-08-14T10:20:30.250"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("aligns the first tick to a minute and then updates every minute", () => {
    const { result, unmount } = renderHook(() => useClock("en-US"))
    expect(result.current.isReady).toBe(true)
    expect(result.current.hh).toBe("10")
    expect(result.current.mm).toBe("20")
    expect(result.current.time.getSeconds()).toBe(0)

    act(() => vi.advanceTimersByTime(29_750))
    expect(result.current.mm).toBe("21")

    act(() => vi.advanceTimersByTime(60_000))
    expect(result.current.mm).toBe("22")
    unmount()
  })

  it("cleans up safely before the minute-alignment timeout fires", () => {
    const { unmount } = renderHook(() => useClock("ru-RU"))
    expect(() => unmount()).not.toThrow()
  })

  it("hydrates the same clock snapshot when server and browser timezones differ", async () => {
    const originalTimezone = process.env.TZ
    const recoverableErrors: unknown[] = []
    const container = document.createElement("div")
    let unmount: (() => void) | undefined

    try {
      vi.setSystemTime(new Date("2026-09-30T03:14:52.000Z"))
      process.env.TZ = "UTC"
      const serverMarkup = renderToString(<ClockMarkup />)
      expect(serverMarkup).toContain("--:--|")
      container.innerHTML = serverMarkup

      process.env.TZ = "Europe/Istanbul"
      const root = hydrateRoot(container, <ClockMarkup />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      unmount = () => root.unmount()

      await act(async () => {})

      expect(recoverableErrors).toEqual([])
      expect(container.textContent).toContain("06:14")
    } finally {
      if (unmount) await act(async () => unmount?.())
      if (originalTimezone === undefined) delete process.env.TZ
      else process.env.TZ = originalTimezone
    }
  })
})
