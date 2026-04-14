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

export const nowParity = () => {
  const onejan = new Date(new Date().getFullYear(), 0, 1)
  const week = Math.ceil(((+new Date() - +onejan) / 86400000 + onejan.getDay() + 1) / 7)
  return week % 2 === 0 ? "even" : "odd"
}
