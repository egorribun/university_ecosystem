import { describe, expect, it, vi } from "vitest"
import { getRoomStatus } from "../roomStatus"

const CAMPUS_ZONE = "Europe/Istanbul"

function instant(value: string): Date {
  return new Date(value)
}

describe("roomStatus utils", () => {
  it("returns free if todayLessons is empty", () => {
    expect(getRoomStatus("ГУК-305", [], CAMPUS_ZONE)).toEqual({ status: "free" })
  })

  it("ignores lessons for other rooms", () => {
    const lessons = [{ room: "ГУК-306", start_time: "08:00", end_time: "10:00" }]
    expect(getRoomStatus("ГУК-305", lessons, CAMPUS_ZONE, instant("2026-07-06T06:00:00Z"))).toEqual(
      {
        status: "free",
      }
    )
  })

  it("ignores lessons with missing start_time or end_time", () => {
    const lessons = [
      { room: "ГУК-305", start_time: null, end_time: "10:00" },
      { room: "ГУК-305", start_time: "08:00", end_time: null },
    ]
    expect(getRoomStatus("ГУК-305", lessons, CAMPUS_ZONE, instant("2026-07-06T06:00:00Z"))).toEqual(
      {
        status: "free",
      }
    )
  })

  it("ignores lessons with malformed start_time or end_time", () => {
    const lessons = [
      { room: "ГУК-305", start_time: "invalid", end_time: "10:00" },
      { room: "ГУК-305", start_time: "08:00", end_time: "invalid" },
    ]
    expect(getRoomStatus("ГУК-305", lessons, CAMPUS_ZONE, instant("2026-07-06T06:00:00Z"))).toEqual(
      {
        status: "free",
      }
    )
  })

  it("identifies busy room during normal lesson hours", () => {
    const lessons = [{ room: "ГУК-305", start_time: "08:30", end_time: "10:00" }]

    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T08:29:00Z"))).toEqual({
      status: "free",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T08:30:00Z"))).toEqual({
      status: "busy",
      busyUntil: "10:00",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T09:15:00Z"))).toEqual({
      status: "busy",
      busyUntil: "10:00",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T10:00:00Z"))).toEqual({
      status: "free",
    })
  })

  it("handles midnight wraparound lessons", () => {
    const lessons = [{ room: "ГУК-305", start_time: "23:00", end_time: "02:00" }]
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T22:59:00Z"))).toEqual({
      status: "free",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-06T23:30:00Z"))).toEqual({
      status: "busy",
      busyUntil: "02:00",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-07T01:00:00Z"))).toEqual({
      status: "busy",
      busyUntil: "02:00",
    })
    expect(getRoomStatus("ГУК-305", lessons, "UTC", instant("2026-07-07T02:00:00Z"))).toEqual({
      status: "free",
    })
  })

  it("marks a room busy from the exact start minute of a lesson crossing midnight", () => {
    expect(
      getRoomStatus(
        "ГУК-305",
        [{ room: "ГУК-305", start_time: "23:00", end_time: "02:00" }],
        "UTC",
        instant("2026-07-06T23:00:00Z")
      )
    ).toEqual({ status: "busy", busyUntil: "02:00" })
  })

  it("treats a zero-length lesson as not occupying the room", () => {
    expect(
      getRoomStatus(
        "R",
        [{ room: "R", start_time: "08:00", end_time: "08:00" }],
        "UTC",
        instant("2026-07-06T12:00:00Z")
      )
    ).toEqual({ status: "free" })
  })

  it.each(["", "noon", "12", ":30", "12:", "x12:00"])(
    "ignores a lesson with an unparseable start time %j",
    (start) => {
      expect(
        getRoomStatus(
          "R",
          [{ room: "R", start_time: start, end_time: "13:00" }],
          "UTC",
          instant("2026-07-06T12:00:00Z")
        )
      ).toEqual({ status: "free" })
    }
  )

  it("accepts seconds and single-digit clock parts", () => {
    expect(
      getRoomStatus(
        "R",
        [{ room: "R", start_time: "9:5", end_time: "12:30:00" }],
        "UTC",
        instant("2026-07-06T12:00:00Z")
      )
    ).toEqual({ status: "busy", busyUntil: "12:30:00" })
  })

  it("accepts fractional seconds in clock and naive ISO campus wall values", () => {
    expect(
      getRoomStatus(
        "R",
        [{ room: "R", start_time: "9:00:01.123456", end_time: "2026-07-06T10:00:59.999" }],
        "UTC",
        instant("2026-07-06T09:30:00Z")
      )
    ).toEqual({ status: "busy", busyUntil: "10:00" })
  })

  it("rejects long malformed tails after optional seconds", () => {
    const invalidTail = `${"1".repeat(20_000)}x`
    const malformedValues = [
      [`09:00:01.${invalidTail}`, "10:00"],
      ["09:00", `2026-07-06T10:00:01.${invalidTail}`],
    ] as const

    for (const [start_time, end_time] of malformedValues) {
      expect(
        getRoomStatus(
          "R",
          [{ room: "R", start_time, end_time }],
          "UTC",
          instant("2026-07-06T09:30:00Z")
        )
      ).toEqual({ status: "free" })
    }
  })

  it("keeps naive ISO date-times as campus wall time", () => {
    const lessons = [
      {
        room: "R",
        start_time: "2026-07-06T09:00:00",
        end_time: "2026-07-06T11:00:00",
      },
    ]
    expect(getRoomStatus("R", lessons, CAMPUS_ZONE, instant("2026-07-06T06:30:00Z"))).toEqual({
      status: "busy",
      busyUntil: "11:00",
    })
  })

  it("converts Z timestamps to the campus timezone before comparing", () => {
    const lessons = [
      {
        room: "R",
        start_time: "2026-07-06T06:30:00Z",
        end_time: "2026-07-06T08:00:00Z",
      },
    ]
    expect(getRoomStatus("R", lessons, CAMPUS_ZONE, instant("2026-07-06T07:45:00Z"))).toEqual({
      status: "busy",
      busyUntil: "11:00",
    })
  })

  it("converts numeric-offset timestamps to the campus timezone before comparing", () => {
    const lessons = [
      {
        room: "R",
        start_time: "2026-07-06T12:00:00+05:00",
        end_time: "2026-07-06T13:30:00+05:00",
      },
    ]
    expect(getRoomStatus("R", lessons, CAMPUS_ZONE, instant("2026-07-06T07:00:00Z"))).toEqual({
      status: "busy",
      busyUntil: "11:30",
    })
  })

  it("omits occupancy when the campus timezone is invalid", () => {
    expect(
      getRoomStatus("R", [{ room: "R", start_time: "08:00", end_time: "10:00" }], "bad-zone")
    ).toBeNull()
  })

  it("returns no occupancy when the current instant is invalid", () => {
    const lessons = [{ room: "R", start_time: "08:00", end_time: "10:00" }]

    expect(getRoomStatus("R", lessons, CAMPUS_ZONE, new Date("not-a-date"))).toBeNull()
  })

  it.each([
    ["24:00", "10:00"],
    ["08:00", "10:60"],
    ["2026-07-06T24:00:00", "2026-07-06T10:00:00"],
    ["2026-07-06T08:00:00", "2026-07-06T10:60:00"],
  ])("ignores out-of-range campus clock values %j", (start_time, end_time) => {
    expect(
      getRoomStatus(
        "R",
        [{ room: "R", start_time, end_time }],
        CAMPUS_ZONE,
        instant("2026-07-06T06:30:00Z")
      )
    ).toEqual({ status: "free" })
  })

  it("ignores a malformed explicit-offset instant instead of treating it as occupancy", () => {
    expect(
      getRoomStatus(
        "R",
        [
          {
            room: "R",
            start_time: "not-a-timestampZ",
            end_time: "2026-07-06T08:00:00Z",
          },
        ],
        CAMPUS_ZONE,
        instant("2026-07-06T07:00:00Z")
      )
    ).toEqual({ status: "free" })
  })

  it("returns no occupancy if Intl cannot provide numeric campus clock parts", () => {
    const formatToParts = vi
      .spyOn(Intl.DateTimeFormat.prototype, "formatToParts")
      .mockReturnValue([])

    try {
      expect(
        getRoomStatus(
          "R",
          [{ room: "R", start_time: "08:00", end_time: "10:00" }],
          CAMPUS_ZONE,
          instant("2026-07-06T06:30:00Z")
        )
      ).toBeNull()
    } finally {
      formatToParts.mockRestore()
    }
  })
})
