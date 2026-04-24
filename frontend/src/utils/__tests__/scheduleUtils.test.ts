import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { pad, fmtTime, nowParity } from "../scheduleUtils"

// ---------------------------------------------------------------------------
// pad
// ---------------------------------------------------------------------------
describe("pad", () => {
  it("pads a single digit with a leading zero", () => {
    expect(pad(5)).toBe("05")
  })

  it("does not pad a two-digit number", () => {
    expect(pad(12)).toBe("12")
  })

  it("pads zero", () => {
    expect(pad(0)).toBe("00")
  })

  it("does not pad numbers with more than 2 digits", () => {
    expect(pad(100)).toBe("100")
  })
})

// ---------------------------------------------------------------------------
// fmtTime
// ---------------------------------------------------------------------------
describe("fmtTime", () => {
  it("returns empty string for undefined", () => {
    expect(fmtTime(undefined)).toBe("")
  })

  it("returns empty string for empty string", () => {
    expect(fmtTime("")).toBe("")
  })

  it("slices HH:MM from a full ISO-style datetime (e.g. '2025-06-15T14:30:00')", () => {
    // length >= 16 and s[10] === 'T' → slice(11,16)
    expect(fmtTime("2025-06-15T14:30:00")).toBe("14:30")
    expect(fmtTime("2025-06-15T08:05:00Z")).toBe("08:05")
  })

  it("slices first 5 chars for plain HH:MM strings", () => {
    expect(fmtTime("14:30")).toBe("14:30")
    expect(fmtTime("08:05")).toBe("08:05")
  })

  it("slices first 5 chars for HH:MM:SS strings", () => {
    expect(fmtTime("09:00:00")).toBe("09:00")
  })

  it("returns correct value for midnight", () => {
    expect(fmtTime("00:00")).toBe("00:00")
    expect(fmtTime("2025-01-01T00:00:00")).toBe("00:00")
  })
})

// ---------------------------------------------------------------------------
// nowParity
// ---------------------------------------------------------------------------
describe("nowParity", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("returns 'odd' or 'even' (string union)", () => {
    vi.setSystemTime(new Date(2025, 0, 1)) // Jan 1, 2025
    const result = nowParity()
    expect(["odd", "even"]).toContain(result)
  })

  it("returns consistent result for the same date (deterministic)", () => {
    vi.setSystemTime(new Date(2025, 0, 6)) // Jan 6, 2025 (week 2 → even)
    const first = nowParity()
    const second = nowParity()
    expect(first).toBe(second)
  })

  it("returns 'odd' for week 1 of the year", () => {
    // January 1, 2025 → week 1 → odd
    vi.setSystemTime(new Date(2025, 0, 1, 12, 0, 0))
    expect(nowParity()).toBe("odd")
  })

  it("returns 'even' for week 2 of the year", () => {
    // January 6, 2025 → week 2 → even
    vi.setSystemTime(new Date(2025, 0, 6, 12, 0, 0))
    expect(nowParity()).toBe("even")
  })
})
