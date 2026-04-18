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

/** Parse "HH:MM" into minutes since midnight. Returns NaN on invalid input. */
function parseMinutes(time: string): number {
  const [h, m] = time.split(":")
  if (h === undefined || m === undefined) return Number.NaN
  return parseInt(h, 10) * 60 + parseInt(m, 10)
}

/**
 * Check if a room is currently occupied by a lesson.
 *
 * @param roomId    Full room ID, e.g. "ГУК-305"
 * @param todayLessons  Today's lessons (may include other rooms)
 * @param now       Override for testability (defaults to current time)
 */
export function getRoomStatus(
  roomId: string,
  todayLessons: LessonSlot[],
  now?: Date,
): RoomStatus {
  const current = now ?? new Date()
  const nowMinutes = current.getHours() * 60 + current.getMinutes()

  for (const lesson of todayLessons) {
    if (lesson.room !== roomId) continue
    if (!lesson.start_time || !lesson.end_time) continue

    const start = parseMinutes(lesson.start_time)
    const end = parseMinutes(lesson.end_time)

    if (Number.isNaN(start) || Number.isNaN(end)) continue

    // Handle midnight wraparound (e.g. start=22:00, end=02:00)
    const isBusy = end <= start
      ? (nowMinutes >= start || nowMinutes < end)
      : (start <= nowMinutes && nowMinutes < end)

    if (isBusy) {
      return { status: "busy", busyUntil: lesson.end_time }
    }
  }

  return { status: "free" }
}
