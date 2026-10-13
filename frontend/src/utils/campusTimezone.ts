import { formatDate, toDate, type DateInput } from "@/utils/date"

type CalendarDateParts = { year: number; month: number; day: number }
type CampusDateRange = "today" | "week" | "month" | ""

const datePartFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat("en-CA", {
    calendar: "gregory",
    day: "2-digit",
    month: "2-digit",
    numberingSystem: "latn",
    timeZone,
    year: "numeric",
  })

const getCalendarParts = (date: Date, timeZone: string): CalendarDateParts => {
  const parts = datePartFormatter(timeZone).formatToParts(date)
  return {
    year: Number(parts.find((part) => part.type === "year")!.value),
    month: Number(parts.find((part) => part.type === "month")!.value),
    day: Number(parts.find((part) => part.type === "day")!.value),
  }
}

/** Returns the Gregorian YYYY-MM-DD date of an instant in the configured campus zone. */
export function getCampusDateKey(input: DateInput, timeZone: string | null): string | null {
  const date = toDate(input)
  if (!timeZone || Number.isNaN(date.getTime())) return null
  const { year, month, day } = getCalendarParts(date, timeZone)
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`
}

/** Format an event instant only when the authoritative campus zone is available. */
export function formatCampusDate(
  input: DateInput,
  options: Intl.DateTimeFormatOptions,
  locale: string,
  timeZone: string | null
): string {
  return timeZone ? formatDate(input, { ...options, timeZone }, locale) : ""
}

export function shiftCampusDateKey(dateKey: string, days: number): string {
  const [year, month, day] = dateKey.split("-").map(Number)
  const shifted = new Date(Date.UTC(year!, month! - 1, day! + days))
  const shiftedYear = String(shifted.getUTCFullYear()).padStart(4, "0")
  const shiftedMonth = String(shifted.getUTCMonth() + 1).padStart(2, "0")
  const shiftedDay = String(shifted.getUTCDate()).padStart(2, "0")
  return `${shiftedYear}-${shiftedMonth}-${shiftedDay}`
}

/** Calendar-date boundaries are half-open, independent of host zone and DST day length. */
export function getCampusDateRangeKeys(
  range: CampusDateRange,
  now: Date,
  timeZone: string | null
): [string, string] | null {
  const today = getCampusDateKey(now, timeZone)
  if ((range !== "today" && range !== "week" && range !== "month") || !today || !timeZone) {
    return null
  }

  if (range === "today") return [today, shiftCampusDateKey(today, 1)]

  if (range === "week") {
    const [year, month, day] = today.split("-").map(Number)
    const dayOfWeek = new Date(Date.UTC(year!, month! - 1, day!)).getUTCDay()
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const start = shiftCampusDateKey(today, mondayOffset)
    return [start, shiftCampusDateKey(start, 7)]
  }

  const [year, month] = today.split("-").map(Number)
  const start = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-01`
  const nextMonth = new Date(Date.UTC(year!, month!, 1))
  const nextYear = String(nextMonth.getUTCFullYear()).padStart(4, "0")
  const nextMonthNumber = String(nextMonth.getUTCMonth() + 1).padStart(2, "0")
  const end = `${nextYear}-${nextMonthNumber}-01`
  return [start, end]
}
