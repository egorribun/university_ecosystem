import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { isOpenNow, getTodayHours } from "../buildingHours"
import type { BuildingHours } from "@/data/campusBuildings"

describe("buildingHours utils", () => {
  const sampleHours: BuildingHours = {
    weekday: "08:00-22:00",
    saturday: "10:00-18:00",
    sunday: "closed",
  }

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe("getTodayHours", () => {
    it("returns sunday hours on Sunday", () => {
      // 2026-07-05 is a Sunday
      vi.setSystemTime(new Date("2026-07-05T12:00:00"))
      expect(getTodayHours(sampleHours)).toBe("closed")
    })

    it("returns saturday hours on Saturday", () => {
      // 2026-07-04 is a Saturday
      vi.setSystemTime(new Date("2026-07-04T12:00:00"))
      expect(getTodayHours(sampleHours)).toBe("10:00-18:00")
    })

    it("returns weekday hours on a weekday", () => {
      // 2026-07-06 is a Monday
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(getTodayHours(sampleHours)).toBe("08:00-22:00")
    })
  })

  describe("isOpenNow", () => {
    it("returns false if todayHours is falsy", () => {
      const emptyHours: BuildingHours = {
        weekday: "",
        saturday: "",
        sunday: "",
      }
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(isOpenNow(emptyHours)).toBe(false)
    })

    it("returns true for 24/7", () => {
      const h: BuildingHours = {
        weekday: "24/7",
        saturday: "24/7",
        sunday: "24/7",
      }
      vi.setSystemTime(new Date("2026-07-06T03:00:00"))
      expect(isOpenNow(h)).toBe(true)

      vi.setSystemTime(new Date("2026-07-05T03:00:00"))
      expect(isOpenNow(h)).toBe(true)
    })

    it("returns false for closed or закрыто", () => {
      const h: BuildingHours = {
        weekday: "closed",
        saturday: "закрыто",
        sunday: "closed",
      }
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(isOpenNow(h)).toBe(false)

      vi.setSystemTime(new Date("2026-07-04T12:00:00"))
      expect(isOpenNow(h)).toBe(false)
    })

    it("returns false for malformed hour format", () => {
      const h: BuildingHours = {
        weekday: "not-a-time-format",
        saturday: "",
        sunday: "",
      }
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(isOpenNow(h)).toBe(false)
    })

    it("handles regular hours (openMinutes < closeMinutes)", () => {
      // weekday: "08:00-22:00"
      // Before open
      vi.setSystemTime(new Date("2026-07-06T07:59:00"))
      expect(isOpenNow(sampleHours)).toBe(false)

      // Exactly open
      vi.setSystemTime(new Date("2026-07-06T08:00:00"))
      expect(isOpenNow(sampleHours)).toBe(true)

      // During
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(isOpenNow(sampleHours)).toBe(true)

      // Exactly close (exclusive)
      vi.setSystemTime(new Date("2026-07-06T22:00:00"))
      expect(isOpenNow(sampleHours)).toBe(false)
    })

    it("handles midnight wraparound hours (closeMinutes <= openMinutes)", () => {
      const wrapHours: BuildingHours = {
        weekday: "22:00-02:00",
        saturday: "",
        sunday: "",
      }

      // During wrap-around (before midnight)
      vi.setSystemTime(new Date("2026-07-06T23:00:00"))
      expect(isOpenNow(wrapHours)).toBe(true)

      // During wrap-around (after midnight)
      vi.setSystemTime(new Date("2026-07-06T01:00:00"))
      expect(isOpenNow(wrapHours)).toBe(true)

      // Outside wrap-around
      vi.setSystemTime(new Date("2026-07-06T12:00:00"))
      expect(isOpenNow(wrapHours)).toBe(false)
    })
  })
})
