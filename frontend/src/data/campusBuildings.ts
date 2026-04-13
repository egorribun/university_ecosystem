/**
 * campusBuildings.ts — Real GUU campus building/floor/room data model.
 *
 * Structural data (rooms, floors, geo coords) is locale-independent.
 * Localized metadata (names, descriptions) is loaded from map.json.
 *
 * Wave 88 — foundation; Wave 99 — real GUU data; Wave 101 — verified coordinates from
 * 2GIS/Yandex Maps/totadres.ru, real floor counts, SVG fields removed.
 * Wave 106 — expanded to ~120 rooms with real GUU room numbers (ГУ/ЛК/У/А prefixes).
 */

/* ── Type Definitions ──────────────────────────── */

export type BuildingLetter = "А" | "Б" | "В" | "Г" | "Д" | "Е" | "Ж" | "З" | "И"

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

export interface BuildingHours {
  weekday: string
  saturday: string
  sunday: string
}

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
}

export interface BuildingFloor {
  /** 1-based floor number */
  floor: number
  /** Rooms on this floor */
  rooms: CampusRoom[]
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
  hours: BuildingHours
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
  /** WGS84 coordinates [lat, lng] — verified via 2GIS/Yandex Maps */
  geoCoords: [number, number]
  /** URL or asset path to building photo (undefined = gradient placeholder) */
  photo?: string
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
  И: { colorVar: "var(--color-orange-500)", colorHex: "#f97316" },
}

/* ── Structural Data (locale-independent) ─────────── */

interface BuildingStructure {
  letter: BuildingLetter
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

/**
 * All coordinates verified via 2GIS, Yandex Maps, totadres.ru (April 2026).
 * Floor counts from totadres.ru building registry data.
 * Rooms are representative samples — will be expanded in Wave 102.
 */
const CAMPUS_STRUCTURE: BuildingStructure[] = [
  /* ── А — Главный учебный корпус (ГУК, стр. 8, 8 этажей) ── */
  {
    letter: "А",
    structureId: "стр. 8",
    tags: ["study", "services", "events"],
    geoCoords: [55.71405, 37.81165],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "А-101", number: "101", type: "lecture", capacity: 200 },
          { id: "А-102", number: "102", type: "cafeteria", capacity: 300 },
          { id: "А-103", number: "103", type: "admin", capacity: 20 },
          { id: "А-104", number: "104", type: "other", capacity: 15 },
          { id: "А-105", number: "105", type: "admin", capacity: 12 },
          { id: "А-106", number: "106", type: "lecture", capacity: 100 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "А-201", number: "201", type: "lecture", capacity: 120 },
          { id: "А-202", number: "202", type: "seminar", capacity: 40 },
          { id: "А-203", number: "203", type: "office", capacity: 10 },
          { id: "А-204", number: "204", type: "seminar", capacity: 35 },
          { id: "А-205", number: "205", type: "seminar", capacity: 30 },
          { id: "А-229", number: "229", type: "admin", capacity: 15 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "А-301", number: "301", type: "lecture", capacity: 80 },
          { id: "А-302", number: "302", type: "seminar", capacity: 30 },
          { id: "А-303", number: "303", type: "office", capacity: 8 },
          { id: "А-304", number: "304", type: "seminar", capacity: 30 },
          { id: "А-305", number: "305", type: "seminar", capacity: 35 },
          { id: "А-310", number: "310", type: "lab", capacity: 25 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "А-401", number: "401", type: "lecture", capacity: 80 },
          { id: "А-402", number: "402", type: "seminar", capacity: 35 },
          { id: "А-403", number: "403", type: "seminar", capacity: 30 },
          { id: "А-410", number: "410", type: "office", capacity: 10 },
          { id: "А-464", number: "464", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "А-501", number: "501", type: "seminar", capacity: 30 },
          { id: "А-502", number: "502", type: "office", capacity: 10 },
          { id: "А-506", number: "506", type: "admin", capacity: 15 },
          { id: "А-507", number: "507", type: "office", capacity: 12 },
          { id: "А-509", number: "509", type: "admin", capacity: 10 },
          { id: "А-515", number: "515", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "А-601", number: "601", type: "seminar", capacity: 30 },
          { id: "А-602", number: "602", type: "office", capacity: 10 },
          { id: "А-610", number: "610", type: "office", capacity: 8 },
        ],
      },
      {
        floor: 7,
        rooms: [
          { id: "А-701", number: "701", type: "office", capacity: 8 },
          { id: "А-702", number: "702", type: "office", capacity: 8 },
          { id: "А-705", number: "705", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 8,
        rooms: [
          { id: "А-801", number: "801", type: "office", capacity: 6 },
          { id: "А-802", number: "802", type: "admin", capacity: 10 },
        ],
      },
    ],
  },
  /* ── Б — Корпус поточных аудиторий + Библиотека (стр. 5, 5 этажей) ── */
  {
    letter: "Б",
    structureId: "стр. 5",
    tags: ["study", "services"],
    geoCoords: [55.71350, 37.81669],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Б-101", number: "101", type: "lecture", capacity: 250 },
          { id: "Б-102", number: "102", type: "lecture", capacity: 200 },
          { id: "Б-103", number: "103", type: "lecture", capacity: 150 },
          { id: "Б-104", number: "104", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Б-201", number: "201", type: "lecture", capacity: 150 },
          { id: "Б-202", number: "202", type: "library", capacity: 100 },
          { id: "Б-203", number: "203", type: "study", capacity: 50 },
          { id: "Б-204", number: "204", type: "study", capacity: 40 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "Б-301", number: "301", type: "lecture", capacity: 120 },
          { id: "Б-302", number: "302", type: "seminar", capacity: 40 },
          { id: "Б-303", number: "303", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "Б-401", number: "401", type: "seminar", capacity: 40 },
          { id: "Б-402", number: "402", type: "seminar", capacity: 35 },
          { id: "Б-403", number: "403", type: "lecture", capacity: 80 },
          { id: "Б-410", number: "410", type: "seminar", capacity: 30 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "Б-501", number: "501", type: "office", capacity: 15 },
          { id: "Б-502", number: "502", type: "office", capacity: 10 },
          { id: "Б-503", number: "503", type: "seminar", capacity: 25 },
        ],
      },
    ],
  },
  /* ── В — Лабораторный корпус + Приёмная комиссия (стр. 4, 6 этажей) ── */
  {
    letter: "В",
    structureId: "стр. 4",
    tags: ["study", "services"],
    geoCoords: [55.71342, 37.81537],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "В-101", number: "101", type: "admin", capacity: 20 },
          { id: "В-102", number: "102", type: "lab", capacity: 30 },
          { id: "В-103", number: "103", type: "lab", capacity: 25 },
          { id: "В-104", number: "104", type: "seminar", capacity: 40 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "В-201", number: "201", type: "lab", capacity: 20 },
          { id: "В-202", number: "202", type: "lab", capacity: 25 },
          { id: "В-204", number: "204", type: "lab", capacity: 25 },
          { id: "В-206", number: "206", type: "lab", capacity: 20 },
          { id: "В-207", number: "207", type: "seminar", capacity: 30 },
          { id: "В-212", number: "212", type: "lab", capacity: 20 },
          { id: "В-216", number: "216", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "В-301", number: "301", type: "lab", capacity: 20 },
          { id: "В-302", number: "302", type: "lab", capacity: 20 },
          { id: "В-304", number: "304", type: "office", capacity: 12 },
          { id: "В-308", number: "308", type: "office", capacity: 10 },
          { id: "В-310", number: "310", type: "office", capacity: 10 },
          { id: "В-312", number: "312", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "В-401", number: "401", type: "lab", capacity: 25 },
          { id: "В-402", number: "402", type: "office", capacity: 12 },
          { id: "В-410", number: "410", type: "seminar", capacity: 30 },
          { id: "В-431", number: "431", type: "office", capacity: 10 },
          { id: "В-440", number: "440", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "В-501", number: "501", type: "office", capacity: 10 },
          { id: "В-502", number: "502", type: "office", capacity: 8 },
          { id: "В-510", number: "510", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "В-601", number: "601", type: "office", capacity: 8 },
          { id: "В-602", number: "602", type: "office", capacity: 6 },
          { id: "В-645", number: "645", type: "office", capacity: 15 },
        ],
      },
    ],
  },
  /* ── Г — Административный корпус (стр. 1, 5 этажей) ── */
  {
    letter: "Г",
    structureId: "стр. 1",
    tags: ["services"],
    geoCoords: [55.71401, 37.81778],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Г-101", number: "101", type: "admin", capacity: 15 },
          { id: "Г-102", number: "102", type: "admin", capacity: 10 },
          { id: "Г-105", number: "105", type: "other", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Г-201", number: "201", type: "admin", capacity: 12 },
          { id: "Г-202", number: "202", type: "office", capacity: 8 },
          { id: "Г-203", number: "203", type: "office", capacity: 6 },
          { id: "Г-210", number: "210", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "Г-301", number: "301", type: "admin", capacity: 15 },
          { id: "Г-302", number: "302", type: "office", capacity: 8 },
          { id: "Г-319", number: "319", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "Г-401", number: "401", type: "office", capacity: 10 },
          { id: "Г-402", number: "402", type: "office", capacity: 8 },
          { id: "Г-405", number: "405", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "Г-501", number: "501", type: "office", capacity: 8 },
          { id: "Г-502", number: "502", type: "office", capacity: 6 },
        ],
      },
    ],
  },
  /* ── Д — Бассейн ГУУ (к. 3, 2 этажа, построен 2013) ── */
  {
    letter: "Д",
    structureId: "к. 3",
    tags: ["sports"],
    geoCoords: [55.71572, 37.81193],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Д-101", number: "101", type: "sports", capacity: 60 },
          { id: "Д-102", number: "102", type: "other", capacity: 20 },
          { id: "Д-103", number: "103", type: "office", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Д-201", number: "201", type: "sports", capacity: 30 },
          { id: "Д-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },
  /* ── Е — Спортивный комплекс (стр. 7, 2 этажа) ── */
  {
    letter: "Е",
    structureId: "стр. 7",
    tags: ["sports", "events"],
    geoCoords: [55.71490, 37.81272],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Е-101", number: "101", type: "sports", capacity: 200 },
          { id: "Е-102", number: "102", type: "sports", capacity: 80 },
          { id: "Е-103", number: "103", type: "other", capacity: 15 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Е-201", number: "201", type: "sports", capacity: 40 },
          { id: "Е-202", number: "202", type: "sports", capacity: 30 },
          { id: "Е-203", number: "203", type: "sports", capacity: 25 },
        ],
      },
    ],
  },
  /* ── Ж — Общежитие №2 + ЦУВП (стр. 2, 16 этажей) ── */
  {
    letter: "Ж",
    structureId: "стр. 2",
    tags: ["housing", "events"],
    geoCoords: [55.71384, 37.81577],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Ж-101", number: "101", type: "study", capacity: 20 },
          { id: "Ж-102", number: "102", type: "cafeteria", capacity: 40 },
          { id: "Ж-103", number: "103", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Ж-201", number: "201", type: "study", capacity: 15 },
          { id: "Ж-202", number: "202", type: "other", capacity: 10 },
          { id: "Ж-203", number: "203", type: "other", capacity: 100 },
        ],
      },
    ],
  },
  /* ── З — Общежитие №6 (к. 6, 18 этажей) ── */
  {
    letter: "З",
    structureId: "к. 6",
    tags: ["housing"],
    geoCoords: [55.71495, 37.81547],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "З-101", number: "101", type: "study", capacity: 25 },
          { id: "З-102", number: "102", type: "cafeteria", capacity: 50 },
          { id: "З-103", number: "103", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "З-201", number: "201", type: "study", capacity: 20 },
          { id: "З-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },
  /* ── И — Бизнес-центр (стр. 16, 2+ этажа) ── */
  {
    letter: "И",
    structureId: "стр. 16",
    tags: ["study", "services"],
    geoCoords: [55.71569, 37.81355],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "И-101", number: "101", type: "seminar", capacity: 30 },
          { id: "И-102", number: "102", type: "office", capacity: 10 },
          { id: "И-103", number: "103", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "И-201", number: "201", type: "seminar", capacity: 25 },
          { id: "И-202", number: "202", type: "office", capacity: 8 },
          { id: "И-205", number: "205", type: "office", capacity: 10 },
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
  hours: BuildingHours
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
 * Structural data (rooms, floors, geo coords) is always the same;
 * only names, descriptions, and amenities change per locale.
 */
export function getCampusBuildings(locale?: string): CampusBuilding[] {
  const localeData = resolveLocaleData(locale)

  return CAMPUS_STRUCTURE.map((struct) => {
    const meta = localeData?.buildings?.[struct.letter]
    const colors = BUILDING_COLORS[struct.letter]

    const floors: BuildingFloor[] = struct.floors.map((f) => ({
      floor: f.floor,
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
      hours: meta?.hours ?? { weekday: "", saturday: "", sunday: "" },
      amenities: meta?.amenities ?? [],
      tags: struct.tags,
      colorVar: colors.colorVar,
      colorHex: colors.colorHex,
      floorCount: floors.length,
      floors,
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
export const BUILDING_LETTERS: readonly BuildingLetter[] = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И"]

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
