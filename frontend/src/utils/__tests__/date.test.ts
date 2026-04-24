import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { toDate, formatDate, formatRelativeTime, formatForInput, add, isAfter } from "../date"

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
