/**
 * General-purpose schedule utilities.
 * Used by dashboard components and useClock.
 *
 * FIX-67-08: `parseMinutes` re-exported from canonical source
 * to eliminate duplication with components/schedule/scheduleUtils.ts.
 */

import { getCampusClockParts } from "@/utils/campusTimezone"

export { parseMinutes } from "@/components/schedule/scheduleUtils"

export const pad = (n: number) => String(n).padStart(2, "0")

export const fmtTime = (s?: string) =>
  !s ? "" : s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)

const DAY_MS = 86_400_000

/**
 * ISO-8601 week number of the selected calendar date, as Python's
 * ``date.isocalendar()`` reports it: weeks start on Monday and week 1 holds
 * the year's first Thursday.
 */
export const isoWeekNumber = (date: Date, timeZone?: string | null): number => {
  const campusClock = timeZone ? getCampusClockParts(date, timeZone) : null
  let year = date.getFullYear()
  let month = date.getMonth()
  let day = date.getDate()
  if (campusClock) {
    const [campusYear, campusMonth, campusDay] = campusClock.dateKey.split("-").map(Number)
    year = campusYear!
    month = campusMonth! - 1
    day = campusDay!
  }

  const thursday = new Date(0)
  thursday.setUTCFullYear(year, month, day)
  thursday.setUTCHours(0, 0, 0, 0)
  thursday.setUTCDate(thursday.getUTCDate() + 3 - ((thursday.getUTCDay() + 6) % 7))
  const yearStart = new Date(0)
  yearStart.setUTCFullYear(thursday.getUTCFullYear(), 0, 1)
  yearStart.setUTCHours(0, 0, 0, 0)
  return Math.floor((thursday.getTime() - yearStart.getTime()) / DAY_MS / 7) + 1
}

/** Campus ISO parity when configured; existing callers retain the local-calendar default. */
export const nowParity = (date: Date = new Date(), timeZone?: string | null) =>
  isoWeekNumber(date, timeZone) % 2 === 0 ? "even" : "odd"
