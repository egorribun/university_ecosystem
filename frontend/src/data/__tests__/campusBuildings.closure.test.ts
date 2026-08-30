import { describe, expect, it } from "vitest"
import { CAMPUS_STRUCTURE_ACADEMIC } from "@/data/campusBuildingsStructureAcademic"
import { CAMPUS_STRUCTURE_ADMINISTRATIVE } from "@/data/campusBuildingsStructureAdministrative"
import { CAMPUS_STRUCTURE_RESIDENTIAL } from "@/data/campusBuildingsStructureResidential"
import {
  BUILDING_IDS,
  MAP_CATEGORIES,
  extractFloorFromRoomId,
  findRoom,
  getBuildingById,
  getCampusBuildings,
} from "@/data/campusBuildings"

const toStructuralShape = (building: {
  letter: string
  structureId: string
  tags: readonly string[]
  geoCoords: readonly [number, number]
  floors: ReadonlyArray<{
    floor: number
    rooms: ReadonlyArray<{
      id: string
      number: string
      type: string
      capacity?: number
    }>
  }>
}) => ({
  letter: building.letter,
  structureId: building.structureId,
  tags: [...building.tags],
  geoCoords: [...building.geoCoords],
  floors: building.floors.map((floor) => ({
    floor: floor.floor,
    rooms: floor.rooms.map(({ id, number, type, capacity }) => ({
      id,
      number,
      type,
      ...(capacity === undefined ? {} : { capacity }),
    })),
  })),
})

describe("campus building data helpers", () => {
  it("keeps the localized result identical to the decomposed structural data", () => {
    const structuralData = [
      ...CAMPUS_STRUCTURE_ACADEMIC,
      ...CAMPUS_STRUCTURE_ADMINISTRATIVE,
      ...CAMPUS_STRUCTURE_RESIDENTIAL,
    ]

    expect(structuralData.map((building) => building.letter)).toEqual(BUILDING_IDS)
    expect(getCampusBuildings("en").map(toStructuralShape)).toEqual(
      structuralData.map(toStructuralShape)
    )
  })

  it("builds localized structures and reuses the locale cache", () => {
    const buildings = getCampusBuildings("en")
    expect(buildings).toHaveLength(BUILDING_IDS.length)
    expect(buildings.map((building) => building.letter)).toEqual(BUILDING_IDS)
    expect(getCampusBuildings("en")).toBe(buildings)
    expect(getCampusBuildings("en-US")).toHaveLength(BUILDING_IDS.length)
    expect(getCampusBuildings("unknown-locale")).toHaveLength(BUILDING_IDS.length)
    expect(getCampusBuildings()).toHaveLength(BUILDING_IDS.length)
    expect(buildings.every((building) => building.floors.length === building.floorCount)).toBe(true)
    expect(
      buildings.some((building) => building.floors.some((floor) => floor.rooms.length > 0))
    ).toBe(true)
  })

  it("finds buildings and rooms, including missing values", () => {
    const building = getBuildingById("ГУК", "en")
    expect(building?.letter).toBe("ГУК")
    expect(getBuildingById("ЦИТ", "ru-RU")?.letter).toBe("ЦИТ")

    const found = findRoom("ГУК-305", "en")
    expect(found?.room.id).toBe("ГУК-305")
    expect(found?.floor.floor).toBe(3)
    expect(found?.building.letter).toBe("ГУК")
    expect(findRoom("missing-room", "en")).toBeUndefined()
  })

  it("extracts floor numbers and exposes map categories", () => {
    expect(extractFloorFromRoomId("ГУК-305")).toBe(3)
    expect(extractFloorFromRoomId("ПА-102")).toBe(1)
    expect(extractFloorFromRoomId("missing")).toBeNull()
    expect(extractFloorFromRoomId("ГУК-X05")).toBeNull()
    expect(extractFloorFromRoomId("ГУК-")).toBeNull()
    expect(MAP_CATEGORIES).toEqual(["study", "food", "sports", "services", "housing", "events"])
  })
})
