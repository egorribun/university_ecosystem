/**
 * buildingIcons.ts — Parse room strings into building + room components.
 * Maps university buildings to theme-consistent colors.
 * Wave 66 (Idea #4); Wave 107 — BuildingId multi-char abbreviations.
 */

/** Parsed building/room result */
export interface BuildingRoom {
  building: string
  room: string
  /** CSS color token name (e.g., "--color-blue-500") */
  colorVar: string
  /** Hex fallback for inline SVG/canvas */
  colorHex: string
}

/**
 * Building → color mapping.
 * Keys are real GUU abbreviations (ГУК, ПА, ЛК, А, Б, СК, О2, О6, ЦИТ).
 * Matches lesson-type accent palette for visual consistency.
 */
const BUILDING_COLORS: Record<string, { colorVar: string; colorHex: string }> = {
  ГУК: { colorVar: "var(--color-blue-500)", colorHex: "#3b82f6" },
  ПА:  { colorVar: "var(--color-amber-500)", colorHex: "#f59e0b" },
  ЛК:  { colorVar: "var(--color-emerald-500)", colorHex: "#10b981" },
  А:   { colorVar: "var(--color-slate-500)", colorHex: "#64748b" },
  Б:   { colorVar: "var(--color-rose-500)", colorHex: "#f43f5e" },
  СК:  { colorVar: "var(--color-indigo-500)", colorHex: "#6366f1" },
  О2:  { colorVar: "var(--color-sky-500)", colorHex: "#0ea5e9" },
  О6:  { colorVar: "var(--color-violet-500)", colorHex: "#8b5cf6" },
  ЦИТ: { colorVar: "var(--color-orange-500)", colorHex: "#f97316" },
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
  const colors = BUILDING_COLORS[building] ?? DEFAULT_COLOR
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
