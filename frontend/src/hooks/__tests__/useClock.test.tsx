import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"

import { useClock } from "@/hooks/useClock"

function ClockMarkup() {
  const { hh, mm, dateStr } = useClock("en-US")
  return <p>{`${hh}:${mm}|${dateStr}`}</p>
}

function mockLocalTimezone(initialTimezone: string) {
  let timeZone = initialTimezone
  const toLocaleDateString = Date.prototype.toLocaleDateString
  const localTimePart = (date: Date, part: "hour" | "minute") => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date)
    return Number(parts.find(({ type }) => type === part)?.value)
  }

  // Stryker uses Node worker threads, where process.env.TZ cannot change
  // Date's native timezone. Model local reads with IANA timezone data while
  // leaving the frozen instant, UTC methods and timer behavior intact.
  const spies = [
    vi.spyOn(Date.prototype, "getHours").mockImplementation(function (this: Date) {
      return localTimePart(this, "hour")
    }),
    vi.spyOn(Date.prototype, "getMinutes").mockImplementation(function (this: Date) {
      return localTimePart(this, "minute")
    }),
    vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (
      this: Date,
      locales,
      options
    ) {
      return toLocaleDateString.call(this, locales, { timeZone, ...options })
    }),
  ]

  return {
    setTimezone(nextTimezone: string) {
      timeZone = nextTimezone
    },
    restore() {
      spies.forEach((spy) => spy.mockRestore())
    },
  }
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

  it.each([
    ["2026-09-30T03:14:52.000Z", "06:14|Wednesday, September 30"],
    ["2026-09-30T22:14:52.000Z", "01:14|Thursday, October 1"],
  ])("hydrates across server and browser timezones at %s", async (instant, expectedClock) => {
    const timezone = mockLocalTimezone("UTC")
    const recoverableErrors: unknown[] = []
    const container = document.createElement("div")
    let unmount: (() => void) | undefined

    try {
      vi.setSystemTime(new Date(instant))
      const serverMarkup = renderToString(<ClockMarkup />)
      expect(serverMarkup).toBe("<p>--:--|</p>")
      container.innerHTML = serverMarkup

      timezone.setTimezone("Europe/Istanbul")
      const root = hydrateRoot(container, <ClockMarkup />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      unmount = () => root.unmount()

      await act(async () => {})

      expect(recoverableErrors).toEqual([])
      expect(container.textContent).toBe(expectedClock)
      expect(Date.now()).toBe(Date.parse(instant))
    } finally {
      try {
        if (unmount) await act(async () => unmount?.())
      } finally {
        timezone.restore()
      }
    }
  })
})
