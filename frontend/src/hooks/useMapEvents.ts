/**
 * useMapEvents.ts — Fetch active events and resolve their campus building locations.
 * Returns geo-positioned MapEvent items ready for EventMarker rendering.
 * Wave 108
 */

import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useEventsListQuery } from "@/api/hooks/events"
import { parseBuildingRoom } from "@/utils/buildingIcons"
import { getCampusBuildings, BUILDING_IDS, type BuildingId } from "@/data/campusBuildings"

/** Geo-positioned event for map rendering */
export interface MapEvent {
  id: string
  title: string
  startsAt: string
  endsAt: string
  buildingId: BuildingId
  participantCount?: number
  location: string
  geoCoords: [number, number]
}

/**
 * Fetch active events and attach campus building geo coordinates.
 * Events with unparseable or unrecognized building locations are silently skipped.
 */
export function useMapEvents(): { events: MapEvent[]; isLoading: boolean } {
  const { i18n } = useTranslation()
  const { events: rawEvents, isLoading } = useEventsListQuery({
    language: i18n.language,
    is_active: true,
    limit: 50,
  })

  const events = useMemo(() => {
    const buildings = getCampusBuildings(i18n.language)
    const buildingMap = new Map(buildings.map((b) => [b.letter, b]))
    const result: MapEvent[] = []

    for (const event of rawEvents) {
      const location = event.location ?? event.location_en
      if (!location) continue

      const parsed = parseBuildingRoom(location)
      if (!parsed) continue

      const buildingId = parsed.building as BuildingId
      if (!(BUILDING_IDS as readonly string[]).includes(buildingId)) continue

      const building = buildingMap.get(buildingId)
      if (!building) continue

      result.push({
        id: event.id,
        title: event.title,
        startsAt: event.starts_at,
        endsAt: event.ends_at,
        buildingId,
        participantCount: event.participant_count ?? undefined,
        location,
        geoCoords: building.geoCoords,
      })
    }

    return result
  }, [rawEvents, i18n.language])

  return { events, isLoading }
}
