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

import enMapData from "../i18n/locales/en/map.json"
import ruMapData from "../i18n/locales/ru/map.json"

/* ── Type Definitions ──────────────────────────── */

export type BuildingId = "ГУК" | "ПА" | "ЛК" | "А" | "Б" | "СК" | "О2" | "О6" | "ЦИТ"

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

export type MapCategory = "all" | "study" | "food" | "sports" | "services" | "housing" | "events"

export interface BuildingHours {
  weekday: string
  saturday: string
  sunday: string
}

export interface CampusRoom {
  /** Full room ID, e.g. "ГУК-305" */
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
  /** Building abbreviation, e.g. "ГУК" */
  letter: BuildingId
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

/** Canonical building→color mapping. Single source of truth — imported by buildingIcons.ts. */
export const BUILDING_COLORS: Record<BuildingId, { colorVar: string; colorHex: string }> = {
  ГУК: { colorVar: "var(--color-blue-500)", colorHex: "#3b82f6" },
  ПА: { colorVar: "var(--color-amber-500)", colorHex: "#f59e0b" },
  ЛК: { colorVar: "var(--color-emerald-500)", colorHex: "#10b981" },
  А: { colorVar: "var(--color-slate-500)", colorHex: "#64748b" },
  Б: { colorVar: "var(--color-rose-500)", colorHex: "#f43f5e" },
  СК: { colorVar: "var(--color-indigo-500)", colorHex: "#6366f1" },
  О2: { colorVar: "var(--color-sky-500)", colorHex: "#0ea5e9" },
  О6: { colorVar: "var(--color-violet-500)", colorHex: "#8b5cf6" },
  ЦИТ: { colorVar: "var(--color-orange-500)", colorHex: "#f97316" },
}

/* ── Structural Data (locale-independent) ─────────── */

interface BuildingStructure {
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

/**
 * All coordinates verified via 2GIS, Yandex Maps, totadres.ru (April 2026).
 * Floor counts from totadres.ru building registry data.
 * Rooms are representative samples — will be expanded in Wave 102.
 */
const CAMPUS_STRUCTURE: BuildingStructure[] = [
  /* ── А — Главный учебный корпус (ГУК, стр. 8, 8 этажей) ── */
  {
    letter: "ГУК",
    structureId: "стр. 8",
    tags: ["study", "services", "events"],
    geoCoords: [55.71405, 37.81165],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ГУК-101", number: "101", type: "lecture", capacity: 200 },
          { id: "ГУК-102", number: "102", type: "cafeteria", capacity: 300 },
          { id: "ГУК-103", number: "103", type: "admin", capacity: 20 },
          { id: "ГУК-104", number: "104", type: "other", capacity: 15 },
          { id: "ГУК-105", number: "105", type: "admin", capacity: 12 },
          { id: "ГУК-106", number: "106", type: "lecture", capacity: 100 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ГУК-201", number: "201", type: "lecture", capacity: 120 },
          { id: "ГУК-202", number: "202", type: "seminar", capacity: 40 },
          { id: "ГУК-203", number: "203", type: "office", capacity: 10 },
          { id: "ГУК-204", number: "204", type: "seminar", capacity: 35 },
          { id: "ГУК-205", number: "205", type: "seminar", capacity: 30 },
          { id: "ГУК-229", number: "229", type: "admin", capacity: 15 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ГУК-301", number: "301", type: "lecture", capacity: 80 },
          { id: "ГУК-302", number: "302", type: "seminar", capacity: 30 },
          { id: "ГУК-303", number: "303", type: "office", capacity: 8 },
          { id: "ГУК-304", number: "304", type: "seminar", capacity: 30 },
          { id: "ГУК-305", number: "305", type: "seminar", capacity: 35 },
          { id: "ГУК-310", number: "310", type: "lab", capacity: 25 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ГУК-401", number: "401", type: "lecture", capacity: 80 },
          { id: "ГУК-402", number: "402", type: "seminar", capacity: 35 },
          { id: "ГУК-403", number: "403", type: "seminar", capacity: 30 },
          { id: "ГУК-410", number: "410", type: "office", capacity: 10 },
          { id: "ГУК-464", number: "464", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ГУК-501", number: "501", type: "seminar", capacity: 30 },
          { id: "ГУК-502", number: "502", type: "office", capacity: 10 },
          { id: "ГУК-506", number: "506", type: "admin", capacity: 15 },
          { id: "ГУК-507", number: "507", type: "office", capacity: 12 },
          { id: "ГУК-509", number: "509", type: "admin", capacity: 10 },
          { id: "ГУК-515", number: "515", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "ГУК-601", number: "601", type: "seminar", capacity: 30 },
          { id: "ГУК-602", number: "602", type: "office", capacity: 10 },
          { id: "ГУК-610", number: "610", type: "office", capacity: 8 },
        ],
      },
      {
        floor: 7,
        rooms: [
          { id: "ГУК-701", number: "701", type: "office", capacity: 8 },
          { id: "ГУК-702", number: "702", type: "office", capacity: 8 },
          { id: "ГУК-705", number: "705", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 8,
        rooms: [
          { id: "ГУК-801", number: "801", type: "office", capacity: 6 },
          { id: "ГУК-802", number: "802", type: "admin", capacity: 10 },
        ],
      },
    ],
  },
  /* ── Б — Корпус поточных аудиторий + Библиотека (стр. 5, 5 этажей) ── */
  {
    letter: "ПА",
    structureId: "стр. 5",
    tags: ["study", "services"],
    geoCoords: [55.7135, 37.81669],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ПА-101", number: "101", type: "lecture", capacity: 250 },
          { id: "ПА-102", number: "102", type: "lecture", capacity: 200 },
          { id: "ПА-103", number: "103", type: "lecture", capacity: 150 },
          { id: "ПА-104", number: "104", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ПА-201", number: "201", type: "lecture", capacity: 150 },
          { id: "ПА-202", number: "202", type: "library", capacity: 100 },
          { id: "ПА-203", number: "203", type: "study", capacity: 50 },
          { id: "ПА-204", number: "204", type: "study", capacity: 40 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ПА-301", number: "301", type: "lecture", capacity: 120 },
          { id: "ПА-302", number: "302", type: "seminar", capacity: 40 },
          { id: "ПА-303", number: "303", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ПА-401", number: "401", type: "seminar", capacity: 40 },
          { id: "ПА-402", number: "402", type: "seminar", capacity: 35 },
          { id: "ПА-403", number: "403", type: "lecture", capacity: 80 },
          { id: "ПА-410", number: "410", type: "seminar", capacity: 30 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ПА-501", number: "501", type: "office", capacity: 15 },
          { id: "ПА-502", number: "502", type: "office", capacity: 10 },
          { id: "ПА-503", number: "503", type: "seminar", capacity: 25 },
        ],
      },
    ],
  },
  /* ── В — Лабораторный корпус + Приёмная комиссия (стр. 4, 6 этажей) ── */
  {
    letter: "ЛК",
    structureId: "стр. 4",
    tags: ["study", "services"],
    geoCoords: [55.71342, 37.81537],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ЛК-101", number: "101", type: "admin", capacity: 20 },
          { id: "ЛК-102", number: "102", type: "lab", capacity: 30 },
          { id: "ЛК-103", number: "103", type: "lab", capacity: 25 },
          { id: "ЛК-104", number: "104", type: "seminar", capacity: 40 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ЛК-201", number: "201", type: "lab", capacity: 20 },
          { id: "ЛК-202", number: "202", type: "lab", capacity: 25 },
          { id: "ЛК-204", number: "204", type: "lab", capacity: 25 },
          { id: "ЛК-206", number: "206", type: "lab", capacity: 20 },
          { id: "ЛК-207", number: "207", type: "seminar", capacity: 30 },
          { id: "ЛК-212", number: "212", type: "lab", capacity: 20 },
          { id: "ЛК-216", number: "216", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ЛК-301", number: "301", type: "lab", capacity: 20 },
          { id: "ЛК-302", number: "302", type: "lab", capacity: 20 },
          { id: "ЛК-304", number: "304", type: "office", capacity: 12 },
          { id: "ЛК-308", number: "308", type: "office", capacity: 10 },
          { id: "ЛК-310", number: "310", type: "office", capacity: 10 },
          { id: "ЛК-312", number: "312", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ЛК-401", number: "401", type: "lab", capacity: 25 },
          { id: "ЛК-402", number: "402", type: "office", capacity: 12 },
          { id: "ЛК-410", number: "410", type: "seminar", capacity: 30 },
          { id: "ЛК-431", number: "431", type: "office", capacity: 10 },
          { id: "ЛК-440", number: "440", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ЛК-501", number: "501", type: "office", capacity: 10 },
          { id: "ЛК-502", number: "502", type: "office", capacity: 8 },
          { id: "ЛК-510", number: "510", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "ЛК-601", number: "601", type: "office", capacity: 8 },
          { id: "ЛК-602", number: "602", type: "office", capacity: 6 },
          { id: "ЛК-645", number: "645", type: "office", capacity: 15 },
        ],
      },
    ],
  },
  /* ── Г — Административный корпус (стр. 1, 5 этажей) ── */
  {
    letter: "А",
    structureId: "стр. 1",
    tags: ["services"],
    geoCoords: [55.71401, 37.81778],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "А-101", number: "101", type: "admin", capacity: 15 },
          { id: "А-102", number: "102", type: "admin", capacity: 10 },
          { id: "А-105", number: "105", type: "other", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "А-201", number: "201", type: "admin", capacity: 12 },
          { id: "А-202", number: "202", type: "office", capacity: 8 },
          { id: "А-203", number: "203", type: "office", capacity: 6 },
          { id: "А-210", number: "210", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "А-301", number: "301", type: "admin", capacity: 15 },
          { id: "А-302", number: "302", type: "office", capacity: 8 },
          { id: "А-319", number: "319", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "А-401", number: "401", type: "office", capacity: 10 },
          { id: "А-402", number: "402", type: "office", capacity: 8 },
          { id: "А-405", number: "405", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "А-501", number: "501", type: "office", capacity: 8 },
          { id: "А-502", number: "502", type: "office", capacity: 6 },
        ],
      },
    ],
  },
  /* ── Д — Бассейн ГУУ (к. 3, 2 этажа, построен 2013) ── */
  {
    letter: "Б",
    structureId: "к. 3",
    tags: ["sports"],
    geoCoords: [55.71572, 37.81193],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Б-101", number: "101", type: "sports", capacity: 60 },
          { id: "Б-102", number: "102", type: "other", capacity: 20 },
          { id: "Б-103", number: "103", type: "office", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Б-201", number: "201", type: "sports", capacity: 30 },
          { id: "Б-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },
  /* ── Е — Спортивный комплекс (стр. 7, 2 этажа) ── */
  {
    letter: "СК",
    structureId: "стр. 7",
    tags: ["sports", "events"],
    geoCoords: [55.7149, 37.81272],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "СК-101", number: "101", type: "sports", capacity: 200 },
          { id: "СК-102", number: "102", type: "sports", capacity: 80 },
          { id: "СК-103", number: "103", type: "other", capacity: 15 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "СК-201", number: "201", type: "sports", capacity: 40 },
          { id: "СК-202", number: "202", type: "sports", capacity: 30 },
          { id: "СК-203", number: "203", type: "sports", capacity: 25 },
        ],
      },
    ],
  },
  /* ── Ж — Общежитие №2 + ЦУВП (стр. 2, 16 этажей) ── */
  {
    letter: "О2",
    structureId: "стр. 2",
    tags: ["housing", "events"],
    geoCoords: [55.71384, 37.81577],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "О2-101", number: "101", type: "study", capacity: 20 },
          { id: "О2-102", number: "102", type: "cafeteria", capacity: 40 },
          { id: "О2-103", number: "103", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "О2-201", number: "201", type: "study", capacity: 15 },
          { id: "О2-202", number: "202", type: "other", capacity: 10 },
          { id: "О2-203", number: "203", type: "other", capacity: 100 },
        ],
      },
    ],
  },
  /* ── З — Общежитие №6 (к. 6, 18 этажей) ── */
  {
    letter: "О6",
    structureId: "к. 6",
    tags: ["housing"],
    geoCoords: [55.71495, 37.81547],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "О6-101", number: "101", type: "study", capacity: 25 },
          { id: "О6-102", number: "102", type: "cafeteria", capacity: 50 },
          { id: "О6-103", number: "103", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "О6-201", number: "201", type: "study", capacity: 20 },
          { id: "О6-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },
  /* ── И — Бизнес-центр (стр. 16, 2+ этажа) ── */
  {
    letter: "ЦИТ",
    structureId: "стр. 16",
    tags: ["study", "services"],
    geoCoords: [55.71569, 37.81355],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ЦИТ-101", number: "101", type: "seminar", capacity: 30 },
          { id: "ЦИТ-102", number: "102", type: "office", capacity: 10 },
          { id: "ЦИТ-103", number: "103", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ЦИТ-201", number: "201", type: "seminar", capacity: 25 },
          { id: "ЦИТ-202", number: "202", type: "office", capacity: 8 },
          { id: "ЦИТ-205", number: "205", type: "office", capacity: 10 },
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
  buildings: Record<BuildingId, LocalizedBuildingMeta>
  rooms: Record<string, { name: string }>
}

// The MVP ships exactly the two supported locales. Explicit imports keep the
// resource graph deterministic for SSR and mutation testing while preserving
// the same eager, synchronous behaviour as the former glob.
const mapDataByLocale: Record<string, LocalizedMapData> = {
  en: enMapData,
  ru: ruMapData,
}

const FALLBACK_LOCALE = "en"

function resolveLocaleData(locale?: string): LocalizedMapData {
  if (locale) {
    const normalized = locale.toLowerCase()
    if (mapDataByLocale[normalized]) return mapDataByLocale[normalized]
    const short = normalized.split("-")[0]
    if (short && mapDataByLocale[short]) return mapDataByLocale[short]
  }
  return mapDataByLocale[FALLBACK_LOCALE]!
}

/* ── Public API ───────────────────────────────────── */

/**
 * Get all campus buildings with localized metadata merged in.
 * Structural data (rooms, floors, geo coords) is always the same;
 * only names, descriptions, and amenities change per locale.
 */
/** Module-level cache — getCampusBuildings is pure for a given locale (PERF-109-02). */
const _buildingsCache = new Map<string, CampusBuilding[]>()

export function getCampusBuildings(locale?: string): CampusBuilding[] {
  const key = locale ?? "default"
  const cached = _buildingsCache.get(key)
  if (cached) return cached

  const localeData = resolveLocaleData(locale)

  const result = CAMPUS_STRUCTURE.map((struct) => {
    const meta = localeData.buildings[struct.letter]
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
      name: meta.name,
      description: meta.description,
      address: meta.address,
      hours: meta.hours,
      amenities: meta.amenities,
      tags: struct.tags,
      colorVar: colors.colorVar,
      colorHex: colors.colorHex,
      floorCount: floors.length,
      floors,
      geoCoords: struct.geoCoords,
    } satisfies CampusBuilding
  })

  _buildingsCache.set(key, result)
  return result
}

/**
 * Find a specific building by its ID.
 */
export function getBuildingById(letter: BuildingId, locale?: string): CampusBuilding | undefined {
  return getCampusBuildings(locale).find((b) => b.letter === letter)
}

/**
 * Find a room by its full ID (e.g. "ГУК-305").
 * Returns the room, its floor, and parent building.
 */
export function findRoom(
  roomId: string,
  locale?: string
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
 * "ГУК-305" → 3, "ПА-102" → 1
 */
export function extractFloorFromRoomId(roomId: string): number | null {
  const dashIdx = roomId.indexOf("-")
  if (dashIdx < 0) return null
  const digit = roomId[dashIdx + 1]
  if (!digit || !/\d/.test(digit)) return null
  return parseInt(digit, 10)
}

/**
 * All building IDs in display order.
 */
export const BUILDING_IDS: readonly BuildingId[] = [
  "ГУК",
  "ПА",
  "ЛК",
  "А",
  "Б",
  "СК",
  "О2",
  "О6",
  "ЦИТ",
]

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
