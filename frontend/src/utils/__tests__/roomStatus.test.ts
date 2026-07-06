import { describe, expect, it } from "vitest"
import { getRoomStatus } from "../roomStatus"

describe("roomStatus utils", () => {
  it("returns free if todayLessons is empty", () => {
    const status = getRoomStatus("ГУК-305", [])
    expect(status).toEqual({ status: "free" })
  })

  it("ignores lessons for other rooms", () => {
    const lessons = [{ room: "ГУК-306", start_time: "08:00", end_time: "10:00" }]
    const status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T09:00:00"))
    expect(status).toEqual({ status: "free" })
  })

  it("ignores lessons with missing start_time or end_time", () => {
    const lessons = [
      { room: "ГУК-305", start_time: null, end_time: "10:00" },
      { room: "ГУК-305", start_time: "08:00", end_time: null },
    ]
    const status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T09:00:00"))
    expect(status).toEqual({ status: "free" })
  })

  it("ignores lessons with malformed start_time or end_time", () => {
    const lessons = [
      { room: "ГУК-305", start_time: "invalid", end_time: "10:00" },
      { room: "ГУК-305", start_time: "08:00", end_time: "invalid" },
    ]
    const status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T09:00:00"))
    expect(status).toEqual({ status: "free" })
  })

  it("identifies busy room during normal lesson hours", () => {
    const lessons = [{ room: "ГУК-305", start_time: "08:30", end_time: "10:00" }]

    // Before lesson
    let status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T08:29:00"))
    expect(status).toEqual({ status: "free" })

    // Exactly at start
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T08:30:00"))
    expect(status).toEqual({ status: "busy", busyUntil: "10:00" })

    // During lesson
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T09:15:00"))
    expect(status).toEqual({ status: "busy", busyUntil: "10:00" })

    // Exactly at end (exclusive)
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T10:00:00"))
    expect(status).toEqual({ status: "free" })

    // After lesson
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T10:01:00"))
    expect(status).toEqual({ status: "free" })
  })

  it("handles midnight wraparound lessons", () => {
    const lessons = [{ room: "ГУК-305", start_time: "23:00", end_time: "02:00" }]

    // Before lesson
    let status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T22:59:00"))
    expect(status).toEqual({ status: "free" })

    // During lesson (before midnight)
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-06T23:30:00"))
    expect(status).toEqual({ status: "busy", busyUntil: "02:00" })

    // During lesson (after midnight)
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-07T01:00:00"))
    expect(status).toEqual({ status: "busy", busyUntil: "02:00" })

    // Exactly at end
    status = getRoomStatus("ГУК-305", lessons, new Date("2026-07-07T02:00:00"))
    expect(status).toEqual({ status: "free" })
  })
})
