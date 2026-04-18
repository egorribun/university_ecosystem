import { useMemo } from "react"
import { useScheduleData } from "@/hooks/useScheduleData"
import { parseBuildingRoom } from "@/utils/buildingIcons"
import { extractFloorFromRoomId, BUILDING_IDS, type BuildingId } from "@/data/campusBuildings"

/**
 * useNextLesson — bridge between schedule data and campus map.
 *
 * Wraps useScheduleData() to extract the next lesson's building,
 * floor, and room for map highlighting/navigation.
 *
 * Wave 95
 */

interface NextLessonMapInfo {
  /** Building ID (e.g. "ГУК") */
  building: BuildingId
  /** Floor number (e.g. 3 from "ГУК-305") */
  floor: number
  /** Full room ID (e.g. "ГУК-305") */
  roomId: string
  /** Lesson subject */
  subject: string
  /** Time remaining text (e.g. "7ч 22м") */
  timeLeft: string
}

export function useNextLesson(): NextLessonMapInfo | null {
  const { nextLesson, timeLeftShort } = useScheduleData()

  return useMemo(() => {
    if (!nextLesson?.room) return null

    const parsed = parseBuildingRoom(nextLesson.room)
    if (!parsed) return null

    // Type guard — reject unknown building IDs from schedule data
    if (!BUILDING_IDS.includes(parsed.building as BuildingId)) return null
    const buildingId = parsed.building as BuildingId

    const floor = extractFloorFromRoomId(nextLesson.room)
    if (!floor) return null

    return {
      building: buildingId,
      floor,
      roomId: nextLesson.room,
      subject: nextLesson.subject ?? "",
      timeLeft: timeLeftShort,
    }
  }, [nextLesson, timeLeftShort])
}
