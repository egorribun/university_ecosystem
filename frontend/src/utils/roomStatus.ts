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

/** Parse "HH:MM[:SS]" into minutes since midnight. Returns NaN on invalid input. */
function parseMinutes(time: string | null | undefined): number {
  // String(null) is "null", which never matches, so a missing time is NaN.
  const match = /^(\d+):(\d+)/.exec(String(time))
  return match ? Number(match[1]) * 60 + Number(match[2]) : Number.NaN
}

/**
 * Check if a room is currently occupied by a lesson.
 *
 * @param roomId    Full room ID, e.g. "ГУК-305"
 * @param todayLessons  Today's lessons (may include other rooms)
 * @param now       Override for testability (defaults to current time)
 */
export function getRoomStatus(roomId: string, todayLessons: LessonSlot[], now?: Date): RoomStatus {
  const current = now ?? new Date()
  const nowMinutes = current.getHours() * 60 + current.getMinutes()

  for (const lesson of todayLessons) {
    if (lesson.room !== roomId) continue

    // Every comparison with NaN is false, so a missing or unparseable time
    // never marks the room busy.
    const start = parseMinutes(lesson.start_time)
    const end = parseMinutes(lesson.end_time)

    // Handle midnight wraparound (e.g. start=22:00, end=02:00); a zero-length
    // lesson occupies nothing.
    const isBusy =
      end < start
        ? nowMinutes >= start || nowMinutes < end
        : start <= nowMinutes && nowMinutes < end

    if (isBusy) {
      // A busy lesson parsed its end time, so it is a string.
      return { status: "busy", busyUntil: String(lesson.end_time) }
    }
  }

  return { status: "free" }
}
