import type { BuildingHours } from "@/data/campusBuildings"

export function isOpenNow(hours: BuildingHours): boolean {
  const now = new Date()
  const day = now.getDay()

  let todayHours: string
  if (day === 0) todayHours = hours.sunday
  else if (day === 6) todayHours = hours.saturday
  else todayHours = hours.weekday

  if (!todayHours) return false

  const lower = todayHours.toLowerCase()
  if (lower === "24/7") return true
  if (lower === "closed" || lower === "закрыто") return false

  const match = todayHours.match(/(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})/)
  if (!match) return false

  const openMinutes = parseInt(match[1]!, 10) * 60 + parseInt(match[2]!, 10)
  const closeMinutes = parseInt(match[3]!, 10) * 60 + parseInt(match[4]!, 10)
  const nowMinutes = now.getHours() * 60 + now.getMinutes()

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
