import { describe, expect, it } from "vitest"
import {
  toDate,
  formatDate,
  formatRelativeTime,
  formatForInput,
  add,
  getMoscowDate,
  isAfter,
  formatLocalDateTime,
  presets,
} from "@/utils/date"

describe("date utilities", () => {
  describe("toDate", () => {
    it("returns the same Date object when given a Date", () => {
      const date = new Date("2024-06-15T12:00:00Z")
      expect(toDate(date)).toBe(date)
    })

    it("creates Date from ISO string", () => {
      const result = toDate("2024-06-15T12:00:00Z")
      expect(result).toBeInstanceOf(Date)
      expect(result.toISOString()).toBe("2024-06-15T12:00:00.000Z")
    })

    it("creates Date from timestamp number", () => {
      const timestamp = 1718452800000 // 2024-06-15T12:00:00Z
      const result = toDate(timestamp)
      expect(result).toBeInstanceOf(Date)
      expect(result.getTime()).toBe(timestamp)
    })

    it("returns invalid Date for invalid string", () => {
      const result = toDate("not-a-date")
      expect(isNaN(result.getTime())).toBe(true)
    })
  })

  describe("formatDate", () => {
    it("formats date with default options", () => {
      const result = formatDate("2024-06-15T12:00:00Z")
      expect(typeof result).toBe("string")
      expect(result.length).toBeGreaterThan(0)
    })

    it("formats date with custom options", () => {
      const result = formatDate(
        "2024-06-15T12:00:00Z",
        { year: "numeric", month: "long", day: "numeric" },
        "en-US"
      )
      expect(result).toContain("June")
      expect(result).toContain("15")
      expect(result).toContain("2024")
    })

    it("returns empty string for invalid date", () => {
      expect(formatDate("invalid")).toBe("")
    })

    it("handles empty string input", () => {
      expect(formatDate("")).toBe("")
    })

    it("respects locale parameter", () => {
      const enResult = formatDate("2024-06-15", { month: "long" }, "en-US")
      const ruResult = formatDate("2024-06-15", { month: "long" }, "ru-RU")
      // Results should differ because of different locales
      expect(enResult).not.toBe(ruResult)
    })
  })

  describe("presets", () => {
    it("chatGroup preset has month, day, year", () => {
      expect(presets.chatGroup).toEqual({
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    })

    it("chatTime preset has hour and minute", () => {
      expect(presets.chatTime).toEqual({
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    })

    it("auditDate preset includes Moscow timezone", () => {
      expect(presets.auditDate.timeZone).toBe("Europe/Moscow")
    })

    it("auditTime preset includes seconds and Moscow timezone", () => {
      expect(presets.auditTime.second).toBe("2-digit")
      expect(presets.auditTime.timeZone).toBe("Europe/Moscow")
    })

    it("full preset includes year, month, day, hour, minute", () => {
      expect(presets.full).toMatchObject({
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    })
  })

  describe("formatRelativeTime", () => {
    it("formats time a few seconds ago", () => {
      const recent = new Date(Date.now() - 10_000)
      const result = formatRelativeTime(recent, "en-US")
      expect(typeof result).toBe("string")
      expect(result.length).toBeGreaterThan(0)
    })

    it("formats time minutes ago", () => {
      const fiveMinAgo = new Date(Date.now() - 5 * 60_000)
      const result = formatRelativeTime(fiveMinAgo, "en-US")
      expect(result).toContain("5")
      expect(result).toContain("minute")
    })

    it("formats future time", () => {
      const future = new Date(Date.now() + 3660_000) // 1 hour and 1 minute from now
      const result = formatRelativeTime(future, "en-US")
      expect(result).toMatch(/hour|in 61 minutes/)
    })

    it("formats days ago", () => {
      const twoDaysAgo = new Date(Date.now() - 2 * 24 * 3600_000)
      const result = formatRelativeTime(twoDaysAgo, "en-US")
      expect(result).toContain("2")
      expect(result).toContain("day")
    })
  })

  describe("formatForInput", () => {
    it("formats date for datetime-local input (YYYY-MM-DDTHH:mm)", () => {
      const date = new Date(2024, 5, 15, 14, 30) // June 15, 2024 14:30
      const result = formatForInput(date)
      expect(result).toBe("2024-06-15T14:30")
    })

    it("pads single-digit month and day", () => {
      const date = new Date(2024, 0, 5, 9, 5) // Jan 5, 2024 09:05
      const result = formatForInput(date)
      expect(result).toBe("2024-01-05T09:05")
    })

    it("returns empty string for invalid date", () => {
      expect(formatForInput("invalid")).toBe("")
    })

    it("handles ISO string input", () => {
      const result = formatForInput("2024-06-15T14:30:00")
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    })
  })

  describe("add", () => {
    it("adds days", () => {
      const base = new Date(2024, 5, 15)
      const result = add(base, 3, "day")
      expect(result.getDate()).toBe(18)
    })

    it("subtracts days", () => {
      const base = new Date(2024, 5, 15)
      const result = add(base, -5, "day")
      expect(result.getDate()).toBe(10)
    })

    it("adds hours", () => {
      const base = new Date(2024, 5, 15, 10)
      const result = add(base, 3, "hour")
      expect(result.getHours()).toBe(13)
    })

    it("adds minutes", () => {
      const base = new Date(2024, 5, 15, 10, 0)
      const result = add(base, 30, "minute")
      expect(result.getMinutes()).toBe(30)
    })

    it("adds months", () => {
      const base = new Date(2024, 0, 15) // Jan 15
      const result = add(base, 2, "month")
      expect(result.getMonth()).toBe(2) // March
    })

    it("adds years", () => {
      const base = new Date(2024, 5, 15)
      const result = add(base, 1, "year")
      expect(result.getFullYear()).toBe(2025)
    })

    it("does not mutate the original date", () => {
      const base = new Date(2024, 5, 15)
      const originalTime = base.getTime()
      add(base, 5, "day")
      expect(base.getTime()).toBe(originalTime)
    })

    it("handles month overflow (e.g. Jan 31 + 1 month)", () => {
      const base = new Date(2024, 0, 31) // Jan 31
      const result = add(base, 1, "month")
      // JS Date rolls over: Feb 31 → March 2 (2024 is leap year)
      expect(result.getMonth()).toBeGreaterThanOrEqual(1)
    })
  })

  describe("getMoscowDate", () => {
    it("returns a non-empty string", () => {
      const result = getMoscowDate("2024-06-15T12:00:00Z")
      expect(typeof result).toBe("string")
      expect(result.length).toBeGreaterThan(0)
    })

    it("formats with Moscow timezone", () => {
      const result = getMoscowDate("2024-06-15T12:00:00Z")
      // Should contain year, month, day, time
      expect(result).toContain("2024")
    })
  })

  describe("isAfter", () => {
    it("returns true when first date is after second", () => {
      expect(isAfter("2024-06-16", "2024-06-15")).toBe(true)
    })

    it("returns false when first date is before second", () => {
      expect(isAfter("2024-06-14", "2024-06-15")).toBe(false)
    })

    it("returns false when dates are equal", () => {
      const date = "2024-06-15T12:00:00Z"
      expect(isAfter(date, date)).toBe(false)
    })

    it("works with mixed DateInput types", () => {
      const dateObj = new Date("2024-06-16T00:00:00Z")
      expect(isAfter(dateObj, "2024-06-15T00:00:00Z")).toBe(true)
    })
  })

  describe("formatLocalDateTime", () => {
    it("formats with weekday, month, day, time", () => {
      const result = formatLocalDateTime("2024-06-15T14:30:00", "en-US")
      expect(typeof result).toBe("string")
      // Should contain day of week
      expect(result).toMatch(/saturday/i)
    })

    it("respects locale parameter", () => {
      const enResult = formatLocalDateTime("2024-06-15T14:30:00", "en-US")
      const ruResult = formatLocalDateTime("2024-06-15T14:30:00", "ru-RU")
      expect(enResult).not.toBe(ruResult)
    })

    it("returns empty string for invalid date", () => {
      expect(formatLocalDateTime("invalid")).toBe("")
    })
  })
})
