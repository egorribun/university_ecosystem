import { describe, expect, it } from "vitest"
import {
  formatCampusDate,
  getCampusClockParts,
  getCampusDateKey,
  getCampusDateRangeKeys,
  shiftCampusDateKey,
} from "@/utils/campusTimezone"

describe("campus timezone calendar behavior", () => {
  it("uses the configured campus date across a browser-zone midnight boundary", () => {
    const instant = "2026-10-12T01:30:00.000Z"

    expect(getCampusDateKey(instant, "America/Los_Angeles")).toBe("2026-10-11")
    expect(getCampusDateKey(instant, "Europe/Istanbul")).toBe("2026-10-12")
    expect(getCampusDateKey(instant, null)).toBeNull()
  })

  it("formats event instants in the configured zone and refuses an absent zone", () => {
    const instant = "2026-06-15T18:00:00.000Z"
    const options = { hour: "2-digit", minute: "2-digit", hour12: false } as const

    expect(formatCampusDate(instant, options, "en-US", "America/Los_Angeles")).toBe("11:00")
    expect(formatCampusDate(instant, options, "en-US", "Europe/Istanbul")).toBe("21:00")
    expect(formatCampusDate(instant, options, "en-US", null)).toBe("")
  })

  it("produces half-open campus calendar ranges without assuming 24-hour DST days", () => {
    const springForwardDay = new Date("2026-03-08T12:00:00.000Z")

    expect(getCampusDateRangeKeys("today", springForwardDay, "America/New_York")).toEqual([
      "2026-03-08",
      "2026-03-09",
    ])
    expect(getCampusDateRangeKeys("week", springForwardDay, "America/New_York")).toEqual([
      "2026-03-02",
      "2026-03-09",
    ])
    expect(getCampusDateRangeKeys("month", springForwardDay, "America/New_York")).toEqual([
      "2026-03-01",
      "2026-04-01",
    ])
    expect(getCampusDateRangeKeys("today", springForwardDay, null)).toBeNull()
    expect(shiftCampusDateKey("2026-03-08", 1)).toBe("2026-03-09")
  })

  it("starts a Sunday campus week on the preceding Monday", () => {
    expect(
      getCampusDateRangeKeys("week", new Date("2026-10-11T12:00:00.000Z"), "Europe/Istanbul")
    ).toEqual(["2026-10-05", "2026-10-12"])
  })

  it("starts a non-Sunday campus week on the preceding Monday", () => {
    expect(
      getCampusDateRangeKeys("week", new Date("2026-10-15T12:00:00.000Z"), "Europe/Istanbul")
    ).toEqual(["2026-10-12", "2026-10-19"])
  })
})

describe("campus clock parts", () => {
  const instant = "2026-10-18T21:30:45.000Z"

  it("returns the campus Gregorian date and h23 clock including seconds", () => {
    expect(getCampusClockParts(instant, "UTC")).toEqual({
      dateKey: "2026-10-18",
      weekday: 0,
      hour: 21,
      minute: 30,
      second: 45,
    })
    expect(getCampusClockParts(instant, "Europe/Moscow")).toEqual({
      dateKey: "2026-10-19",
      weekday: 1,
      hour: 0,
      minute: 30,
      second: 45,
    })
  })

  it("preserves quarter-hour timezone offsets", () => {
    expect(getCampusClockParts(instant, "Asia/Kathmandu")).toEqual({
      dateKey: "2026-10-19",
      weekday: 1,
      hour: 3,
      minute: 15,
      second: 45,
    })
  })

  it("returns null without a usable timezone or instant", () => {
    expect(getCampusClockParts(instant, null)).toBeNull()
    expect(getCampusClockParts("not a date", "Europe/Moscow")).toBeNull()
    expect(getCampusClockParts(instant, "Invalid/Timezone")).toBeNull()
  })
})
