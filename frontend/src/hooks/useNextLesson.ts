import { useMemo } from "react"
import { useScheduleData } from "@/hooks/useScheduleData"
import { parseBuildingRoom } from "@/utils/buildingIcons"
import { extractFloorFromRoomId, type BuildingLetter } from "@/data/campusBuildings"

/**
 * useNextLesson — bridge between schedule data and campus map.
 *
 * Wraps useScheduleData() to extract the next lesson's building,
 * floor, and room for map highlighting/navigation.
 *
 * Wave 95
 */

interface NextLessonMapInfo {
  /** Building letter (e.g. "А") */
  building: BuildingLetter
  /** Floor number (e.g. 3 from "А-305") */
  floor: number
  /** Full room ID (e.g. "А-305") */
  roomId: string
  /** Lesson subject */
  subject: string
  /** Time remaining text (e.g. "7ч 22м") */
  timeLeft: string
  /** Raw room string */
  room: string
}

export function useNextLesson(): NextLessonMapInfo | null {
  const { nextLesson, timeLeftShort } = useScheduleData()

  return useMemo(() => {
    if (!nextLesson?.room) return null

    const parsed = parseBuildingRoom(nextLesson.room)
    if (!parsed) return null

    const floor = extractFloorFromRoomId(nextLesson.room)
    if (!floor) return null

    return {
      building: parsed.building as BuildingLetter,
      floor,
      roomId: nextLesson.room,
      subject: nextLesson.subject ?? "",
      timeLeft: timeLeftShort,
      room: nextLesson.room,
    }
  }, [nextLesson, timeLeftShort])
}
