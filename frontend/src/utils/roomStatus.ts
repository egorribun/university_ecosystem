/**
 * roomStatus.ts — Determines whether a campus room is currently free or busy
 * based on today's lesson schedule.
 *
 * Wave 108 — room occupancy status for map page.
 */

export type RoomStatus = {
  status: "free" | "busy"
  busyUntil?: string
}

interface LessonSlot {
  room?: string | null
  start_time?: string | null
  end_time?: string | null
}

const CLOCK_TIME = /^(\d{1,2}):(\d{1,2})(?:$|:\d{1,2}$|:\d{1,2}\.\d+$)/
const CAMPUS_WALL_DATETIME = /^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2})(?:$|:\d{2}$|:\d{2}\.\d+$)/
const EXPLICIT_TIME_ZONE = /(?:Z|[+-]\d{2}:\d{2})$/i

function createCampusTimeFormatter(timeZone: string): Intl.DateTimeFormat | null {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
  } catch {
    return null
  }
}

function getMinutesInCampusTime(date: Date, formatter: Intl.DateTimeFormat): number {
  if (!Number.isFinite(date.getTime())) return Number.NaN
  const parts = formatter.formatToParts(date)
  const hour = Number(parts.find((part) => part.type === "hour")?.value)
  const minute = Number(parts.find((part) => part.type === "minute")?.value)
  return Number.isInteger(hour) && Number.isInteger(minute) ? hour * 60 + minute : Number.NaN
}

/**
 * Parse clock-only and naive datetime values as campus wall time. Values with
 * an explicit Z/offset are instants and must first be converted to campus time.
 */
function parseCampusMinutes(
  value: string | null | undefined,
  formatter: Intl.DateTimeFormat
): number {
  if (typeof value !== "string") return Number.NaN

  const clock = CLOCK_TIME.exec(value)
  if (clock) {
    const hour = Number(clock[1])
    const minute = Number(clock[2])
    return hour <= 23 && minute <= 59 ? hour * 60 + minute : Number.NaN
  }

  const wallDateTime = CAMPUS_WALL_DATETIME.exec(value)
  if (wallDateTime) {
    const hour = Number(wallDateTime[1])
    const minute = Number(wallDateTime[2])
    return hour <= 23 && minute <= 59 ? hour * 60 + minute : Number.NaN
  }

  if (!EXPLICIT_TIME_ZONE.test(value)) return Number.NaN
  const instant = new Date(value)
  return getMinutesInCampusTime(instant, formatter)
}

function formatCampusClock(minutes: number): string {
  const hour = Math.floor(minutes / 60)
  const minute = minutes % 60
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`
}

/**
 * Check if a room is currently occupied by a lesson.
 *
 * @param roomId Full room ID, e.g. "ГУК-305"
 * @param todayLessons Today's lessons (may include other rooms)
 * @param timeZone Server-configured campus IANA timezone
 * @param now Override for testability (defaults to the current instant)
 */
export function getRoomStatus(
  roomId: string,
  todayLessons: LessonSlot[],
  timeZone: string,
  now?: Date
): RoomStatus | null {
  const formatter = createCampusTimeFormatter(timeZone)
  if (!formatter) return null

  const current = now ?? new Date()
  const nowMinutes = getMinutesInCampusTime(current, formatter)
  if (!Number.isFinite(nowMinutes)) return null

  for (const lesson of todayLessons) {
    if (lesson.room !== roomId) continue

    const start = parseCampusMinutes(lesson.start_time, formatter)
    const end = parseCampusMinutes(lesson.end_time, formatter)

    // Every comparison with NaN is false, so a missing or unparseable time
    // never marks the room busy.
    // Handle midnight wraparound (e.g. start=22:00, end=02:00); a zero-length
    // lesson occupies nothing.
    const isBusy =
      end < start
        ? nowMinutes >= start || nowMinutes < end
        : start <= nowMinutes && nowMinutes < end

    if (isBusy) {
      // Preserve clock-only display strings; serialize date-time instants as
      // the campus-local clock so users never see the source timezone.
      const busyUntil =
        lesson.end_time && CLOCK_TIME.test(lesson.end_time)
          ? lesson.end_time
          : formatCampusClock(end)
      return { status: "busy", busyUntil }
    }
  }

  return { status: "free" }
}
