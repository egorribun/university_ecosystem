import type { BuildingId, MapCategory, RoomType } from "./campusBuildings"

export interface BuildingStructure {
  letter: BuildingId
  structureId: string
  tags: MapCategory[]
  geoCoords: [number, number]
  floors: Array<{
    floor: number
    rooms: Array<{
      id: string
      number: string
      type: RoomType
      capacity?: number
    }>
  }>
}
