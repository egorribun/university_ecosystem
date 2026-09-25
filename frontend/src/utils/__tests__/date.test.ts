import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  toDate,
  formatDate,
  formatRelativeTime,
  formatForInput,
  add,
  isAfter,
  getMoscowDate,
} from "../date"

// ---------------------------------------------------------------------------
// toDate
// ---------------------------------------------------------------------------
describe("toDate", () => {
  it("returns the same Date instance when passed a Date", () => {
    const date = new Date("2025-06-15T10:00:00Z")
    expect(toDate(date)).toBe(date)
  })

  it("parses an ISO string", () => {
    const result = toDate("2025-06-15T10:00:00Z")
    expect(result).toBeInstanceOf(Date)
    expect(result.getUTCFullYear()).toBe(2025)
    expect(result.getUTCMonth()).toBe(5) // 0-based → June
    expect(result.getUTCDate()).toBe(15)
  })

  it("parses a unix timestamp (number)", () => {
    const ts = new Date("2025-01-01T00:00:00Z").getTime()
    const result = toDate(ts)
    expect(result.getUTCFullYear()).toBe(2025)
  })
})

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------
describe("formatDate", () => {
  it("formats a date with explicit options and locale", () => {
    // Use a fixed date to avoid locale-machine drift
    const date = new Date("2025-09-05T00:00:00Z")
    const result = formatDate(date, { month: "long", day: "numeric", year: "numeric" }, "en-US")
    // The exact string may vary by environment (Node ICU data), so just check structure
    expect(result).toMatch(/September/)
    expect(result).toMatch(/2025/)
  })

  it("returns empty string for an invalid date", () => {
    expect(formatDate("not-a-date")).toBe("")
  })

  it("accepts string input", () => {
    const result = formatDate("2025-03-01", { year: "numeric" }, "en-US")
    expect(result).toContain("2025")
  })
})

// ---------------------------------------------------------------------------
// formatRelativeTime
// ---------------------------------------------------------------------------
describe("formatRelativeTime", () => {
  beforeEach(() => {
    // Pin "now" so tests are reproducible
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2025-06-01T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("formats seconds in the past", () => {
    const pastDate = new Date("2025-06-01T11:59:30Z") // 30 s ago
    const result = formatRelativeTime(pastDate, "en-US")
    expect(result).toMatch(/30 seconds ago/)
  })

  it("formats minutes in the past", () => {
    const pastDate = new Date("2025-06-01T11:55:00Z") // 5 min ago
    const result = formatRelativeTime(pastDate, "en-US")
    expect(result).toMatch(/5 minutes ago/)
  })

  it("formats hours in the past", () => {
    const pastDate = new Date("2025-06-01T09:00:00Z") // 3 h ago
    const result = formatRelativeTime(pastDate, "en-US")
    expect(result).toMatch(/3 hours ago/)
  })

  it("formats days in the past", () => {
    const pastDate = new Date("2025-05-29T12:00:00Z") // 3 days ago
    const result = formatRelativeTime(pastDate, "en-US")
    expect(result).toMatch(/3 days ago/)
  })

  it("formats a future time", () => {
    const futureDate = new Date("2025-06-01T12:05:00Z") // in 5 min
    const result = formatRelativeTime(futureDate, "en-US")
    expect(result).toMatch(/in 5 minutes/)
  })

  const ago = (seconds: number) => new Date(Date.parse("2025-06-01T12:00:00Z") - seconds * 1000)

  it("defaults to English phrasing when no locale is given", () => {
    expect(formatRelativeTime(ago(30))).toBe("30 seconds ago")
  })

  it("uses natural-language phrasing for adjacent units", () => {
    expect(formatRelativeTime(ago(0), "en-US")).toBe("now")
    expect(formatRelativeTime(ago(24 * 3600), "en-US")).toBe("yesterday")
  })

  it("switches to the next unit exactly at each unit boundary", () => {
    expect(formatRelativeTime(ago(59), "en-US")).toBe("59 seconds ago")
    expect(formatRelativeTime(ago(60), "en-US")).toBe("1 minute ago")
    expect(formatRelativeTime(ago(60 * 60), "en-US")).toBe("1 hour ago")
    expect(formatRelativeTime(ago(2 * 3600), "en-US")).toBe("2 hours ago")
    expect(formatRelativeTime(ago(29 * 86400), "en-US")).toBe("29 days ago")
    expect(formatRelativeTime(ago(30 * 86400), "en-US")).toBe("last month")
  })

  it("counts whole 30-day months for older and future dates", () => {
    expect(formatRelativeTime(ago(45 * 86400), "en-US")).toBe("last month")
    expect(formatRelativeTime(ago(60 * 86400), "en-US")).toBe("2 months ago")
    expect(formatRelativeTime(ago(-95 * 86400), "en-US")).toBe("in 3 months")
  })
})

// ---------------------------------------------------------------------------
// formatForInput
// ---------------------------------------------------------------------------
describe("formatForInput", () => {
  it("returns YYYY-MM-DDTHH:mm format", () => {
    // Use a date constructed in local time to avoid TZ offsets
    const date = new Date(2025, 8, 5, 14, 30) // Sep 5, 2025, 14:30 local
    const result = formatForInput(date)
    expect(result).toBe("2025-09-05T14:30")
  })

  it("pads single-digit month, day, hour and minute", () => {
    const date = new Date(2024, 0, 3, 8, 5) // Jan 3, 2024, 08:05 local
    expect(formatForInput(date)).toBe("2024-01-03T08:05")
  })

  it("returns empty string for invalid date", () => {
    expect(formatForInput("invalid")).toBe("")
  })
})

// ---------------------------------------------------------------------------
// add
// ---------------------------------------------------------------------------
describe("add", () => {
  const base = new Date("2025-06-01T12:00:00Z")

  it("adds days", () => {
    expect(add(base, 3, "day").getUTCDate()).toBe(4)
  })

  it("subtracts days with negative count", () => {
    expect(add(base, -1, "day").getUTCDate()).toBe(31) // May 31
  })

  it("adds hours", () => {
    expect(add(base, 5, "hour").getUTCHours()).toBe(17)
  })

  it("adds minutes", () => {
    expect(add(base, 30, "minute").getUTCMinutes()).toBe(30)
    expect(add(base, 15, "minute").toISOString()).toBe("2025-06-01T12:15:00.000Z")
  })

  it("adds months", () => {
    expect(add(base, 2, "month").getUTCMonth()).toBe(7) // August (0-based)
  })

  it("adds years", () => {
    expect(add(base, 1, "year").getUTCFullYear()).toBe(2026)
  })

  it("does not mutate the original date", () => {
    const original = new Date(base)
    add(base, 10, "day")
    expect(base.getTime()).toBe(original.getTime())
  })
})

// ---------------------------------------------------------------------------
// isAfter
// ---------------------------------------------------------------------------
describe("isAfter", () => {
  it("returns true when a is after b", () => {
    expect(isAfter("2025-06-15", "2025-06-01")).toBe(true)
  })

  it("returns false when a is before b", () => {
    expect(isAfter("2025-01-01", "2025-06-01")).toBe(false)
  })

  it("returns false for equal dates", () => {
    const d = "2025-06-01T00:00:00Z"
    expect(isAfter(d, d)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// getMoscowDate
// ---------------------------------------------------------------------------
describe("getMoscowDate", () => {
  it("renders the long date and time in Moscow time regardless of the host zone", () => {
    const result = getMoscowDate("2024-06-15T12:00:00Z") // 15:00 MSK (UTC+3)
    expect(result).toContain("June 15, 2024")
    expect(result).toMatch(/03:00\sPM/u)
  })
})
