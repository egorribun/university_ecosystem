/**
 * General-purpose schedule utilities.
 * Used by dashboard components and useClock.
 *
 * FIX-67-08: `parseMinutes` re-exported from canonical source
 * to eliminate duplication with components/schedule/scheduleUtils.ts.
 */

export { parseMinutes } from "@/components/schedule/scheduleUtils"

export const pad = (n: number) => String(n).padStart(2, "0")

export const fmtTime = (s?: string) =>
  !s ? "" : s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)

const DAY_MS = 86_400_000

/**
 * ISO-8601 week number of a local calendar date, as Python's
 * ``date.isocalendar()`` reports it: weeks start on Monday and week 1 holds
 * the year's first Thursday.
 */
export const isoWeekNumber = (date: Date): number => {
  const thursday = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  thursday.setUTCDate(thursday.getUTCDate() + 3 - ((thursday.getUTCDay() + 6) % 7))
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1)
  return Math.floor((thursday.getTime() - yearStart) / DAY_MS / 7) + 1
}

/** Week parity shared with the backend schedule filters (odd ISO week = "odd"). */
export const nowParity = () => (isoWeekNumber(new Date()) % 2 === 0 ? "even" : "odd")
