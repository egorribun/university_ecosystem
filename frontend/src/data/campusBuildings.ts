/**
 * campusBuildings.ts — Real GUU campus building/floor/room data model.
 *
 * Structural data (rooms, floors, SVG IDs, positions, geo coords) is locale-independent.
 * Localized metadata (names, descriptions) is loaded from map.json.
 *
 * Wave 88 — foundation; Wave 99 — real GUU data (8 buildings from 2GIS/Wikipedia).
 */

/* ── Type Definitions ────────────��───────────────── */

export type BuildingLetter = "А" | "Б" | "В" | "Г" | "Д" | "Е" | "Ж" | "З"

export type RoomType =
  | "lecture"
  | "lab"
  | "office"
  | "seminar"
  | "library"
  | "sports"
  | "cafeteria"
  | "admin"
  | "study"
  | "other"

export type MapCategory =
  | "all"
  | "study"
  | "food"
  | "sports"
  | "services"
  | "housing"
  | "events"

export interface CampusRoom {
  /** Full room ID, e.g. "А-305" */
  id: string
  /** Room number only, e.g. "305" */
  number: string
  /** Functional type for filtering */
  type: RoomType
  /** Max occupancy */
  capacity?: number
  /** Localized display name (merged from map.json) */
  name?: string
  /** SVG element ID for highlight in FloorPlanSVG */
  svgId: string
}

export interface BuildingFloor {
  /** 1-based floor number */
  floor: number
  /** Rooms on this floor */
  rooms: CampusRoom[]
  /** SVG ref for the floor plan component */
  svgFloorId: string
}

export interface CampusBuilding {
  /** Cyrillic letter, e.g. "А" */
  letter: BuildingLetter
  /** Real structure number, e.g. "стр. 8" */
  structureId: string
  /** Localized building name */
  name: string
  /** Localized description */
  description: string
  /** Localized address */
  address: string
  /** Operating hours */
  hours: string
  /** Localized amenity labels */
  amenities: string[]
  /** Filterable categories */
  tags: MapCategory[]
  /** CSS color variable from buildingIcons.ts */
  colorVar: string
  /** Hex fallback for SVG inline use */
  colorHex: string
  /** Number of floors */
  floorCount: number
  /** All floor/room data */
  floors: BuildingFloor[]
  /** SVG group ID in CampusMapSVG */
  svgBuildingId: string
  /** Position in the isometric viewport (pixel offsets) */
  isoPosition: { x: number; y: number }
  /** WGS84 coordinates for Leaflet map [lat, lng] */
  geoCoords: [number, number]
}

/* ── Building Colors ─────────────────────────────── */

const BUILDING_COLORS: Record<BuildingLetter, { colorVar: string; colorHex: string }> = {
  А: { colorVar: "var(--color-blue-500)", colorHex: "#3b82f6" },
  Б: { colorVar: "var(--color-amber-500)", colorHex: "#f59e0b" },
  В: { colorVar: "var(--color-emerald-500)", colorHex: "#10b981" },
  Г: { colorVar: "var(--color-slate-500)", colorHex: "#64748b" },
  Д: { colorVar: "var(--color-rose-500)", colorHex: "#f43f5e" },
  Е: { colorVar: "var(--color-indigo-500)", colorHex: "#6366f1" },
  Ж: { colorVar: "var(--color-sky-500)", colorHex: "#0ea5e9" },
  З: { colorVar: "var(--color-violet-500)", colorHex: "#8b5cf6" },
}

/* ── Structural Data (locale-independent) ─────────── */

interface BuildingStructure {
  letter: BuildingLetter
  structureId: string
  tags: MapCategory[]
  svgBuildingId: string
  isoPosition: { x: number; y: number }
  geoCoords: [number, number]
  floors: Array<{
    floor: number
    svgFloorId: string
    rooms: Array<{
      id: string
      number: string
      type: RoomType
      capacity?: number
      svgId: string
    }>
  }>
}

const CAMPUS_STRUCTURE: BuildingStructure[] = [
  /* ── А — Главный учебный корпус (стр. 8, 8 этажей) ── */
  {
    letter: "А",
    structureId: "стр. 8",
    tags: ["study", "services", "events"],
    svgBuildingId: "bldg-a",
    isoPosition: { x: 450, y: 260 },
    geoCoords: [55.71400, 37.81500],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-a-1",
        rooms: [
          { id: "А-101", number: "101", type: "lecture", capacity: 200, svgId: "room-a-101" },
          { id: "А-102", number: "102", type: "cafeteria", capacity: 300, svgId: "room-a-102" },
          { id: "А-103", number: "103", type: "admin", capacity: 20, svgId: "room-a-103" },
          { id: "А-104", number: "104", type: "other", capacity: 15, svgId: "room-a-104" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-a-2",
        rooms: [
          { id: "А-201", number: "201", type: "lecture", capacity: 120, svgId: "room-a-201" },
          { id: "А-202", number: "202", type: "seminar", capacity: 40, svgId: "room-a-202" },
          { id: "А-203", number: "203", type: "office", capacity: 10, svgId: "room-a-203" },
          { id: "А-204", number: "204", type: "seminar", capacity: 35, svgId: "room-a-204" },
        ],
      },
      {
        floor: 3,
        svgFloorId: "floor-a-3",
        rooms: [
          { id: "А-301", number: "301", type: "lecture", capacity: 80, svgId: "room-a-301" },
          { id: "А-302", number: "302", type: "seminar", capacity: 30, svgId: "room-a-302" },
          { id: "А-303", number: "303", type: "office", capacity: 8, svgId: "room-a-303" },
          { id: "А-304", number: "304", type: "seminar", capacity: 30, svgId: "room-a-304" },
        ],
      },
    ],
  },
  /* ── Б — Корпус поточных аудиторий + Библиотека (стр. 5) ── */
  {
    letter: "Б",
    structureId: "стр. 5",
    tags: ["study", "services"],
    svgBuildingId: "bldg-b",
    isoPosition: { x: 200, y: 300 },
    geoCoords: [55.71380, 37.81430],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-b-1",
        rooms: [
          { id: "Б-101", number: "101", type: "lecture", capacity: 250, svgId: "room-b-101" },
          { id: "Б-102", number: "102", type: "lecture", capacity: 200, svgId: "room-b-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-b-2",
        rooms: [
          { id: "Б-201", number: "201", type: "lecture", capacity: 150, svgId: "room-b-201" },
          { id: "Б-202", number: "202", type: "library", capacity: 100, svgId: "room-b-202" },
          { id: "Б-203", number: "203", type: "study", capacity: 50, svgId: "room-b-203" },
        ],
      },
      {
        floor: 3,
        svgFloorId: "floor-b-3",
        rooms: [
          { id: "Б-301", number: "301", type: "lecture", capacity: 120, svgId: "room-b-301" },
          { id: "Б-302", number: "302", type: "seminar", capacity: 40, svgId: "room-b-302" },
        ],
      },
    ],
  },
  /* ── В — Лабораторный корпус + Приёмная комиссия (стр. 4) ── */
  {
    letter: "В",
    structureId: "стр. 4",
    tags: ["study", "services"],
    svgBuildingId: "bldg-c",
    isoPosition: { x: 700, y: 220 },
    geoCoords: [55.71420, 37.81400],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-c-1",
        rooms: [
          { id: "В-101", number: "101", type: "admin", capacity: 20, svgId: "room-c-101" },
          { id: "В-102", number: "102", type: "lab", capacity: 30, svgId: "room-c-102" },
          { id: "В-103", number: "103", type: "lab", capacity: 25, svgId: "room-c-103" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-c-2",
        rooms: [
          { id: "В-201", number: "201", type: "lab", capacity: 20, svgId: "room-c-201" },
          { id: "В-202", number: "202", type: "lab", capacity: 25, svgId: "room-c-202" },
        ],
      },
      {
        floor: 3,
        svgFloorId: "floor-c-3",
        rooms: [
          { id: "В-301", number: "301", type: "lab", capacity: 20, svgId: "room-c-301" },
          { id: "В-302", number: "302", type: "lab", capacity: 20, svgId: "room-c-302" },
        ],
      },
    ],
  },
  /* ── Г — Административный корпус (стр. 1) ── */
  {
    letter: "Г",
    structureId: "стр. 1",
    tags: ["services"],
    svgBuildingId: "bldg-d",
    isoPosition: { x: 300, y: 480 },
    geoCoords: [55.71360, 37.81520],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-d-1",
        rooms: [
          { id: "Г-101", number: "101", type: "admin", capacity: 15, svgId: "room-d-101" },
          { id: "Г-102", number: "102", type: "admin", capacity: 10, svgId: "room-d-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-d-2",
        rooms: [
          { id: "Г-201", number: "201", type: "admin", capacity: 12, svgId: "room-d-201" },
          { id: "Г-202", number: "202", type: "office", capacity: 8, svgId: "room-d-202" },
          { id: "Г-203", number: "203", type: "office", capacity: 6, svgId: "room-d-203" },
        ],
      },
    ],
  },
  /* ── Д — Бассейн / Спорткомплекс (стр. 3) ── */
  {
    letter: "Д",
    structureId: "стр. 3",
    tags: ["sports", "events"],
    svgBuildingId: "bldg-e",
    isoPosition: { x: 850, y: 400 },
    geoCoords: [55.71440, 37.81550],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-e-1",
        rooms: [
          { id: "Д-101", number: "101", type: "sports", capacity: 60, svgId: "room-e-101" },
          { id: "Д-102", number: "102", type: "sports", capacity: 40, svgId: "room-e-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-e-2",
        rooms: [
          { id: "Д-201", number: "201", type: "sports", capacity: 30, svgId: "room-e-201" },
          { id: "Д-202", number: "202", type: "other", capacity: 20, svgId: "room-e-202" },
        ],
      },
    ],
  },
  /* ── Е — Общежитие №2 (стр. 2, 1976 г.) ── */
  {
    letter: "Е",
    structureId: "стр. 2",
    tags: ["housing"],
    svgBuildingId: "bldg-f",
    isoPosition: { x: 120, y: 160 },
    geoCoords: [55.71350, 37.81350],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-f-1",
        rooms: [
          { id: "Е-101", number: "101", type: "study", capacity: 20, svgId: "room-f-101" },
          { id: "Е-102", number: "102", type: "cafeteria", capacity: 40, svgId: "room-f-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-f-2",
        rooms: [
          { id: "Е-201", number: "201", type: "study", capacity: 15, svgId: "room-f-201" },
          { id: "Е-202", number: "202", type: "other", capacity: 10, svgId: "room-f-202" },
        ],
      },
    ],
  },
  /* ── Ж — Общежитие №6 (к. 6, 1987 г.) ── */
  {
    letter: "Ж",
    structureId: "к. 6",
    tags: ["housing"],
    svgBuildingId: "bldg-g",
    isoPosition: { x: 600, y: 500 },
    geoCoords: [55.71330, 37.81420],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-g-1",
        rooms: [
          { id: "Ж-101", number: "101", type: "study", capacity: 25, svgId: "room-g-101" },
          { id: "Ж-102", number: "102", type: "cafeteria", capacity: 50, svgId: "room-g-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-g-2",
        rooms: [
          { id: "Ж-201", number: "201", type: "study", capacity: 20, svgId: "room-g-201" },
          { id: "Ж-202", number: "202", type: "other", capacity: 15, svgId: "room-g-202" },
        ],
      },
    ],
  },
  /* ── З — Институт подготовки научно-педагогических кадров (стр. 16) ── */
  {
    letter: "З",
    structureId: "стр. 16",
    tags: ["study", "services"],
    svgBuildingId: "bldg-h",
    isoPosition: { x: 950, y: 180 },
    geoCoords: [55.71450, 37.81470],
    floors: [
      {
        floor: 1,
        svgFloorId: "floor-h-1",
        rooms: [
          { id: "З-101", number: "101", type: "seminar", capacity: 30, svgId: "room-h-101" },
          { id: "З-102", number: "102", type: "office", capacity: 10, svgId: "room-h-102" },
        ],
      },
      {
        floor: 2,
        svgFloorId: "floor-h-2",
        rooms: [
          { id: "З-201", number: "201", type: "seminar", capacity: 25, svgId: "room-h-201" },
          { id: "З-202", number: "202", type: "office", capacity: 8, svgId: "room-h-202" },
        ],
      },
    ],
  },
]

/* ── Locale-aware data loading ────────────────────── */

interface LocalizedBuildingMeta {
  name: string
  description: string
  address: string
  hours: string
  amenities: string[]
}

interface LocalizedMapData {
  buildings: Record<string, LocalizedBuildingMeta>
  rooms: Record<string, { name: string }>
}

const localeDataModules = import.meta.glob<{ default: LocalizedMapData }>(
  "../i18n/locales/*/map.json",
  { eager: true },
)

const localePattern = /locales\/([^/]+)\/map\.json$/

const mapDataByLocale = Object.entries(localeDataModules).reduce(
  (acc, [path, module]) => {
    const match = path.match(localePattern)
    if (match) acc[match[1]] = module.default
    return acc
  },
  {} as Record<string, LocalizedMapData>,
)

const FALLBACK_LOCALE = "en"

function resolveLocaleData(locale?: string): LocalizedMapData | undefined {
  if (locale) {
    const normalized = locale.toLowerCase()
    if (mapDataByLocale[normalized]) return mapDataByLocale[normalized]
    const short = normalized.split("-")[0]
    if (short && mapDataByLocale[short]) return mapDataByLocale[short]
  }
  return mapDataByLocale[FALLBACK_LOCALE]
}

/* ── Public API ───────────────────────────────────── */

/**
 * Get all campus buildings with localized metadata merged in.
 * Structural data (rooms, floors, positions, geo coords) is always the same;
 * only names, descriptions, and amenities change per locale.
 */
export function getCampusBuildings(locale?: string): CampusBuilding[] {
  const localeData = resolveLocaleData(locale)

  return CAMPUS_STRUCTURE.map((struct) => {
    const meta = localeData?.buildings?.[struct.letter]
    const colors = BUILDING_COLORS[struct.letter]

    const floors: BuildingFloor[] = struct.floors.map((f) => ({
      floor: f.floor,
      svgFloorId: f.svgFloorId,
      rooms: f.rooms.map((r) => ({
        ...r,
        name: localeData?.rooms?.[r.id]?.name,
      })),
    }))

    return {
      letter: struct.letter,
      structureId: struct.structureId,
      name: meta?.name ?? struct.letter,
      description: meta?.description ?? "",
      address: meta?.address ?? "",
      hours: meta?.hours ?? "",
      amenities: meta?.amenities ?? [],
      tags: struct.tags,
      colorVar: colors.colorVar,
      colorHex: colors.colorHex,
      floorCount: floors.length,
      floors,
      svgBuildingId: struct.svgBuildingId,
      isoPosition: struct.isoPosition,
      geoCoords: struct.geoCoords,
    } satisfies CampusBuilding
  })
}

/**
 * Find a specific building by letter.
 */
export function getBuildingByLetter(
  letter: BuildingLetter,
  locale?: string,
): CampusBuilding | undefined {
  return getCampusBuildings(locale).find((b) => b.letter === letter)
}

/**
 * Find a room by its full ID (e.g. "А-305").
 * Returns the room, its floor, and parent building.
 */
export function findRoom(
  roomId: string,
  locale?: string,
): { room: CampusRoom; floor: BuildingFloor; building: CampusBuilding } | undefined {
  for (const building of getCampusBuildings(locale)) {
    for (const floor of building.floors) {
      const room = floor.rooms.find((r) => r.id === roomId)
      if (room) return { room, floor, building }
    }
  }
  return undefined
}

/**
 * Extract floor number from a room ID string.
 * "А-305" → 3, "Б-102" → 1
 */
export function extractFloorFromRoomId(roomId: string): number | null {
  const match = roomId.match(/^[А-ЯA-Z][\s-]?(\d)/)
  if (!match) return null
  return parseInt(match[1], 10)
}

/**
 * All building letters in display order.
 */
export const BUILDING_LETTERS: readonly BuildingLetter[] = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З"]

/**
 * All filterable categories (excluding "all").
 */
export const MAP_CATEGORIES: readonly MapCategory[] = [
  "study",
  "food",
  "sports",
  "services",
  "housing",
  "events",
]
