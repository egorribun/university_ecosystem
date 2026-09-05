import { afterEach, describe, expect, it, vi } from "vitest"

import * as dateUtils from "@/utils/date"
import {
  buildTable,
  getEndTimeStr,
  getTimeStr,
  getTodayIdx,
  minutesDiff,
  parseMinutes,
  scheduleQueryKey,
  type Lesson,
} from "@/components/schedule/scheduleUtils"

afterEach(() => {
  vi.useRealTimers()
})

describe("schedule time parser closure", () => {
  it("uses the full-date fallback for valid timestamps and rejects invalid dates", () => {
    const dateOnly = "2026-04-26"
    const parsedDate = new Date(dateOnly)
    expect(parseMinutes(dateOnly)).toBe(parsedDate.getHours() * 60 + parsedDate.getMinutes())
    expect(parseMinutes("not-a-real-date")).toBeNull()
  })

  it("parses a valid clock time through the fast path", () => {
    expect(parseMinutes("09:30")).toBe(9 * 60 + 30)
    expect(parseMinutes("00:00")).toBe(0)
    expect(parseMinutes("23:59")).toBe(23 * 60 + 59)
  })

  it("rejects out-of-range clock values after the fast-path shape match", () => {
    expect(parseMinutes("24:00")).toBeNull()
    expect(parseMinutes("23:60")).toBeNull()
    expect(parseMinutes("00:60")).toBeNull()
  })

  it("uses the fallback date's local hour and minute when no clock token exists", () => {
    const toDateSpy = vi.spyOn(dateUtils, "toDate").mockReturnValue(new Date(2026, 3, 26, 13, 37))
    try {
      expect(parseMinutes("opaque-date-value")).toBe(13 * 60 + 37)
    } finally {
      toDateSpy.mockRestore()
    }
  })

  it("handles nullable lesson times and computes valid minute deltas", () => {
    expect(getTimeStr({} as Lesson)).toBe("")
    expect(getEndTimeStr({} as Lesson)).toBe("")
    expect(minutesDiff("09:00", "10:30")).toBe(90)
    expect(minutesDiff("not-a-real-date", "10:30")).toBe(630)
  })

  it("maps Sunday outside the Monday-first schedule", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 16, 12, 0, 0))

    expect(getTodayIdx()).toBe(-1)
  })

  it("maps Monday to the first schedule index", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 17, 12, 0, 0))

    expect(getTodayIdx()).toBe(0)
  })

  it("uses zero defaults when either minutes-diff input is missing or invalid", () => {
    expect(minutesDiff(null, "not-a-real-date")).toBe(0)
  })

  it("builds sorted, null-padded table rows", () => {
    const lessons: Lesson[] = [
      {
        id: "m-late",
        weekday: "Monday",
        parity: "both",
        start_time: "11:00",
        end_time: "12:00",
      },
      {
        id: "t-only",
        weekday: "Tuesday",
        parity: "both",
        start_time: "10:00",
        end_time: "11:00",
      },
      {
        id: "m-early",
        weekday: "Monday",
        parity: "both",
        start_time: "09:00",
        end_time: "10:00",
      },
    ]

    expect(buildTable(lessons, ["Monday", "Tuesday"])).toEqual([
      [lessons[2], lessons[1]],
      [lessons[0], null],
    ])
    expect(buildTable([], [])).toEqual([])
  })

  it("builds the active schedule query key", () => {
    expect(scheduleQueryKey("group-7")).toEqual(["schedule", "group", "group-7"])
  })
})
