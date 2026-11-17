import type { BuildingHours } from "@/data/campusBuildings"
import { getCampusClockParts } from "@/utils/campusTimezone"

export function isOpenNow(hours: BuildingHours, now?: Date): boolean
export function isOpenNow(hours: BuildingHours, now: Date, timeZone: string | null): boolean | null
export function isOpenNow(
  hours: BuildingHours,
  now: Date = new Date(),
  timeZone?: string | null
): boolean | null {
  // Legacy two-argument callers retain local-clock semantics. Map callers pass
  // the authoritative campus zone explicitly; unavailable config is not "closed".
  const clock = timeZone === undefined ? undefined : getCampusClockParts(now, timeZone)
  if (clock === null) return null
  const day = clock ? clock.weekday : now.getDay()

  let todayHours: string
  if (day === 0) todayHours = hours.sunday
  else if (day === 6) todayHours = hours.saturday
  else todayHours = hours.weekday

  if (!todayHours) return false

  if (todayHours === "24/7") return true
  // "closed"/"закрыто" and any other text without a time range fall through
  // the pattern below.

  const match = todayHours.match(/(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})/)
  if (!match) return false

  const openMinutes = parseInt(match[1]!, 10) * 60 + parseInt(match[2]!, 10)
  const closeMinutes = parseInt(match[3]!, 10) * 60 + parseInt(match[4]!, 10)
  const nowMinutes = clock ? clock.hour * 60 + clock.minute : now.getHours() * 60 + now.getMinutes()

  // Handle midnight wraparound (e.g. "22:00–02:00")
  if (closeMinutes <= openMinutes) {
    return nowMinutes >= openMinutes || nowMinutes < closeMinutes
  }
  return nowMinutes >= openMinutes && nowMinutes < closeMinutes
}

export function getTodayHours(hours: BuildingHours): string {
  const day = new Date().getDay()
  if (day === 0) return hours.sunday
  if (day === 6) return hours.saturday
  return hours.weekday
}
