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
import { CAMPUS_STRUCTURE_ACADEMIC } from "./campusBuildingsStructureAcademic"
import { CAMPUS_STRUCTURE_ADMINISTRATIVE } from "./campusBuildingsStructureAdministrative"
import { CAMPUS_STRUCTURE_RESIDENTIAL } from "./campusBuildingsStructureResidential"
import type { BuildingStructure } from "./campusBuildingsStructureTypes"

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

/**
 * All coordinates verified via 2GIS, Yandex Maps, totadres.ru (April 2026).
 * Floor counts from totadres.ru building registry data.
 * Rooms are representative samples — will be expanded in Wave 102.
 */
const CAMPUS_STRUCTURE: BuildingStructure[] = [
  ...CAMPUS_STRUCTURE_ACADEMIC,
  ...CAMPUS_STRUCTURE_ADMINISTRATIVE,
  ...CAMPUS_STRUCTURE_RESIDENTIAL,
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
