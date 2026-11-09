import { afterEach, describe, expect, it, vi } from "vitest"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import * as campusTimezone from "@/utils/campusTimezone"
import { generateGoogleCalendarUrl, selectGoogleCalendarLesson } from "@/utils/scheduleExport"

type SelectionInput = Parameters<typeof selectGoogleCalendarLesson>[0]
type Selection = ReturnType<typeof selectGoogleCalendarLesson>

function lesson(overrides: Partial<Lesson> = {}): Lesson {
  return {
    id: "lesson-first",
    group_id: "group-1",
    weekday: "tuesday",
    parity: "both",
    subject: "Linear Algebra",
    teacher: "Ada Lovelace",
    room: "B-202",
    lesson_type: "lecture",
    start_time: "09:15",
    end_time: "10:45",
    ...overrides,
  }
}

function input(overrides: Partial<SelectionInput> = {}): SelectionInput {
  return {
    schedule: [lesson()],
    selectedGroup: "group-1",
    weekdayConfigs: [
      { id: "mon", backend: ["monday"], long: "Monday", short: "Mon" },
      { id: "tue", backend: ["tuesday"], long: "Tuesday", short: "Tue" },
    ],
    visibleWeekdays: ["monday", "tuesday"],
    now: new Date("2026-10-18T21:30:00Z"),
    weekOffset: 1,
    timeZone: "Europe/Istanbul",
    available: true,
    ...overrides,
  }
}

function ready(selection: Selection) {
  expect(selection.status).toBe("ready")
  if (selection.status !== "ready") {
    throw new Error(`Expected a calendar target, received ${selection.status}`)
  }
  return selection
}

describe("schedule calendar export selection and serialization — AUD-066", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("selects the first filtered campus-week lesson without mutating data", () => {
    const first = lesson()
    const later = lesson({ id: "lesson-later", start_time: "12:00", end_time: "13:30" })
    const hidden = lesson({ id: "hidden-monday", weekday: "monday" })
    const lessons = [later, hidden, first]
    const request = input({ schedule: lessons, visibleWeekdays: ["tuesday"] })

    const selected = ready(selectGoogleCalendarLesson(request))

    expect(selected.lesson.id).toBe("lesson-first")
    expect(selected.lesson.group_id).toBe("group-1")
    expect(selected.occurrence).toEqual({
      dateKey: "2026-10-27",
      timeZone: "Europe/Istanbul",
    })
    expect(lessons).toEqual([later, hidden, first])
    expect(lessons.at(0)).toBe(later)
    expect(first.start_time).toBe("09:15")
  })

  it("preserves legacy lessons without group metadata under the selected query group", () => {
    const request = input({ schedule: [lesson({ group_id: undefined })] })
    const selected = ready(selectGoogleCalendarLesson(request))

    expect(selected.lesson.id).toBe("lesson-first")
    expect(selected.lesson.group_id).toBeUndefined()
    expect(selected.occurrence.dateKey).toBe("2026-10-27")
  })

  it("refuses a contradictory first lesson rather than skipping to a matching group", () => {
    const previousGroup = lesson()
    const matchingLater = lesson({
      id: "matching-later",
      group_id: "group-2",
      start_time: "12:00",
      end_time: "13:30",
    })
    const lessons = [matchingLater, previousGroup]
    const request = input({ selectedGroup: "group-2", schedule: lessons })

    expect(selectGoogleCalendarLesson(request)).toEqual({ status: "unavailable" })
    expect(lessons).toEqual([matchingLater, previousGroup])
  })

  it("refuses invalid first times without silently exporting a later lesson", () => {
    const later = lesson({ id: "valid-later", start_time: "12:00", end_time: "13:30" })
    const invalidTimes: Array<Partial<Lesson>> = [
      { start_time: "", end_time: "10:45" },
      { start_time: "09:15", end_time: null },
      { start_time: "09:15", end_time: "09:00" },
    ]

    for (const times of invalidTimes) {
      const request = input({ schedule: [later, lesson(times)] })
      expect(selectGoogleCalendarLesson(request)).toEqual({ status: "invalid-time" })
    }
  })

  it("normalizes ISO time fields and serializes an explicit campus occurrence", () => {
    const original = lesson({
      start_time: "2024-05-04T09:15:00+03:00",
      end_time: "2024-05-04T10:45:00+03:00",
    })
    const request = input({ schedule: [original] })
    const selected = ready(selectGoogleCalendarLesson(request))

    expect(selected.lesson.start_time).toBe("09:15")
    expect(selected.lesson.end_time).toBe("10:45")
    expect(original.start_time).toBe("2024-05-04T09:15:00+03:00")
    expect(original.end_time).toBe("2024-05-04T10:45:00+03:00")

    const url = new URL(
      generateGoogleCalendarUrl(selected.lesson, selected.occurrence, {
        typePrefix: "Type: Lecture",
      })
    )

    expect(url.origin).toBe("https://calendar.google.com")
    expect(url.pathname).toBe("/calendar/r/eventedit")
    expect(url.searchParams.get("action")).toBe("TEMPLATE")
    expect(url.searchParams.get("text")).toBe("Linear Algebra (Ada Lovelace)")
    expect(url.searchParams.get("dates")).toBe("20261027T091500/20261027T104500")
    expect(url.searchParams.get("location")).toBe("B-202")
    expect(url.searchParams.get("details")).toBe("Type: Lecture")
    expect(url.searchParams.get("ctz")).toBe("Europe/Istanbul")
  })

  it("intersects existing filtered data with the selected week's actual parity", () => {
    const odd = lesson({ parity: "odd" })
    const even = lesson({ id: "even-lesson", parity: "even" })
    const mismatch = input({ schedule: [odd], weekOffset: 1 })
    const current = input({ schedule: [odd], weekOffset: 0 })
    const following = input({ schedule: [even], weekOffset: 1 })

    expect(selectGoogleCalendarLesson(mismatch)).toEqual({ status: "empty" })
    expect(ready(selectGoogleCalendarLesson(current)).occurrence.dateKey).toBe("2026-10-20")
    const selected = ready(selectGoogleCalendarLesson(following))
    expect(selected.lesson.id).toBe("even-lesson")
    expect(selected.occurrence.dateKey).toBe("2026-10-27")
  })

  it("keeps ISO week 53 and week 1 odd across the year boundary", () => {
    const boundary = input({
      now: new Date("2020-12-31T12:00:00Z"),
      timeZone: "UTC",
      schedule: [lesson({ parity: "odd" })],
      weekOffset: 0,
    })
    const current = ready(selectGoogleCalendarLesson(boundary))
    const next = ready(selectGoogleCalendarLesson({ ...boundary, weekOffset: 1 }))
    const even = selectGoogleCalendarLesson({ ...boundary, weekOffset: 2 })

    expect(current.occurrence.dateKey).toBe("2020-12-29")
    expect(next.occurrence.dateKey).toBe("2021-01-05")
    expect(even).toEqual({ status: "empty" })
  })

  it("refuses a safe integer offset outside the Date range before shifting", () => {
    const shift = vi.spyOn(campusTimezone, "shiftCampusDateKey")
    const request = input({ weekOffset: 20_000_000 })

    expect(selectGoogleCalendarLesson(request)).toEqual({ status: "unavailable" })
    expect(shift).not.toHaveBeenCalled()
  })

  it("ignores weekday configs with IDs outside the calendar offset map", () => {
    const request = input({
      schedule: [lesson({ weekday: "holiday" })],
      weekdayConfigs: [{ id: "holiday", backend: ["holiday"], long: "Holiday", short: "Hol" }],
      visibleWeekdays: ["holiday"],
    })

    expect(selectGoogleCalendarLesson(request)).toEqual({ status: "empty" })
  })

  it("refuses empty, hidden, unready, unknown-zone and empty-group inputs", () => {
    expect(selectGoogleCalendarLesson(input({ schedule: [] }))).toEqual({ status: "empty" })
    const hidden = selectGoogleCalendarLesson(input({ visibleWeekdays: [] }))
    expect(hidden).toEqual({ status: "empty" })
    const unavailable: Array<Partial<SelectionInput>> = [
      { available: false },
      { timeZone: null },
      { timeZone: "Invalid/Campus" },
      { selectedGroup: null },
      { selectedGroup: "" },
      { selectedGroup: "   " },
    ]
    for (const overrides of unavailable) {
      expect(selectGoogleCalendarLesson(input(overrides))).toEqual({ status: "unavailable" })
    }
  })

  it("preserves the existing Date-based URL contract without adding a timezone", () => {
    const url = generateGoogleCalendarUrl(lesson(), new Date(2026, 0, 5), {
      typePrefix: "Type: {{type}}",
    })

    expect(url).toBe(
      "https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE" +
        "&text=Linear+Algebra+%28Ada+Lovelace%29" +
        "&dates=20260105T091500%2F20260105T104500" +
        "&location=B-202&details=Type%3A+lecture"
    )
  })
})

describe("schedule calendar export boundary ordering — AUD coverage", () => {
  it("fails closed when the selected week cannot be represented by the date shifter", () => {
    const selection = selectGoogleCalendarLesson(
      input({
        now: new Date("0001-06-01T12:00:00.000Z"),
        timeZone: "UTC",
        weekOffset: 0,
      })
    )

    expect(selection).toEqual({ status: "unavailable" })
  })

  it("uses lesson ID as a deterministic tie-break for equal weekday and start time", () => {
    const selection = ready(
      selectGoogleCalendarLesson(
        input({
          schedule: [
            lesson({ id: "z-last", start_time: "09:15" }),
            lesson({ id: "a-first", start_time: "09:15" }),
          ],
          visibleWeekdays: ["tuesday"],
        })
      )
    )

    expect(selection.lesson.id).toBe("a-first")

    const reversed = ready(
      selectGoogleCalendarLesson(
        input({
          schedule: [
            lesson({ id: "a-first", start_time: "09:15" }),
            lesson({ id: "z-last", start_time: "09:15" }),
          ],
          visibleWeekdays: ["tuesday"],
        })
      )
    )
    expect(reversed.lesson.id).toBe("a-first")
  })

  it("fails closed when the selected occurrence crosses the supported four-digit year", () => {
    const selection = selectGoogleCalendarLesson(
      input({
        schedule: [lesson({ weekday: "sunday" })],
        weekdayConfigs: [{ id: "sun", backend: ["sunday"], long: "Sunday", short: "Sun" }],
        visibleWeekdays: ["sunday"],
        now: new Date("9999-12-31T12:00:00.000Z"),
        timeZone: "UTC",
        weekOffset: 0,
      })
    )

    expect(selection).toEqual({ status: "unavailable" })
  })
})

describe("schedule calendar export stable ID tie", () => {
  it("preserves input order when all three sort keys match", () => {
    const selection = ready(
      selectGoogleCalendarLesson(
        input({
          schedule: [
            lesson({ id: "same-id", subject: "First record", start_time: "09:15" }),
            lesson({ id: "same-id", subject: "Second record", start_time: "09:15" }),
          ],
          visibleWeekdays: ["tuesday"],
        })
      )
    )

    expect(selection.lesson.subject).toBe("First record")
  })
})
