/**
 * buildingIcons.ts — Parse room strings into building + room components.
 * Colors imported from campusBuildings.ts (single source of truth).
 * Wave 66 (Idea #4); Wave 107 — BuildingId multi-char abbreviations.
 * Wave 109 — consolidated BUILDING_COLORS (DRY).
 */

import { BUILDING_COLORS } from "@/data/campusBuildings"

/** Parsed building/room result */
export interface BuildingRoom {
  building: string
  room: string
  /** CSS color token name (e.g., "--color-blue-500") */
  colorVar: string
  /** Hex fallback for inline SVG/canvas */
  colorHex: string
}

const DEFAULT_COLOR = { colorVar: "var(--color-slate-400)", colorHex: "#94a3b8" }

/**
 * Parse a room string into building ID + room number + color.
 * Handles multi-char building IDs: "ГУК-305", "ПА-201", "О2-103", "А-101".
 * Returns null for unparseable strings (e.g., "Спорт. зал").
 */
export function parseBuildingRoom(room: string | null | undefined): BuildingRoom | null {
  if (!room) return null
  const trimmed = room.trim()
  const dashIdx = trimmed.indexOf("-")
  if (dashIdx < 1) return null
  const building = trimmed.slice(0, dashIdx)
  const roomNum = trimmed.slice(dashIdx + 1)
  if (!roomNum || !/^\d/.test(roomNum)) return null
  const colors =
    (BUILDING_COLORS as Record<string, { colorVar: string; colorHex: string }>)[building] ??
    DEFAULT_COLOR
  return { building, room: roomNum, ...colors }
}

/**
 * Extract unique building IDs from a list of lessons.
 * Used for day stats: "корпуса ГУК, ПА, ЛК"
 */
export function uniqueBuildings(lessons: { room?: string | null }[]): string[] {
  const buildings = new Set<string>()
  for (const l of lessons) {
    const parsed = parseBuildingRoom(l.room)
    if (parsed) buildings.add(parsed.building)
  }
  return [...buildings].sort()
}
