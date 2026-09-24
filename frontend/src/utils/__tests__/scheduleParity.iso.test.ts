import { afterEach, describe, expect, it, vi } from "vitest"
import { isoWeekNumber, nowParity } from "../scheduleUtils"

/**
 * The dashboard's week parity must match the backend, which uses the ISO
 * week number (``date.isocalendar()``): odd ISO weeks are "odd".
 */
describe("ISO week parity", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it.each([
    [new Date(2021, 0, 1), 53], // Friday: still ISO week 53 of 2020
    [new Date(2021, 0, 3), 53], // Sunday closes that week
    [new Date(2021, 0, 4), 1], // Monday opens ISO week 1
    [new Date(2024, 11, 30), 1], // Monday: ISO week 1 of 2025
    [new Date(2025, 0, 4), 1], // Saturday
    [new Date(2025, 0, 5), 1], // Sunday
    [new Date(2025, 0, 6), 2],
    [new Date(2026, 8, 24), 39],
    [new Date(2026, 11, 28), 53], // 2026 has 53 ISO weeks
    [new Date(2027, 0, 3), 53], // Sunday
    [new Date(2027, 0, 4), 1],
  ])("numbers %s as ISO week %i", (date, week) => {
    expect(isoWeekNumber(date)).toBe(week)
  })

  it.each([
    [new Date(2025, 0, 4, 12), "odd"],
    [new Date(2025, 0, 5, 12), "odd"],
    [new Date(2025, 0, 6, 12), "even"],
    [new Date(2027, 0, 4, 12), "odd"],
    [new Date(2026, 8, 24, 12), "odd"],
  ])("reports %s as an %s week", (now, parity) => {
    vi.useFakeTimers()
    vi.setSystemTime(now)
    expect(nowParity()).toBe(parity)
  })
})
