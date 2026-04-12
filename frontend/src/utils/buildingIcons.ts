/**
 * buildingIcons.ts — Parse room strings into building + room components.
 * Maps university buildings to theme-consistent colors.
 * Wave 66 (Idea #4)
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
 * Matches lesson-type accent palette for visual consistency.
 */
const BUILDING_COLORS: Record<string, { colorVar: string; colorHex: string }> = {
  А: { colorVar: "var(--color-blue-500)", colorHex: "#3b82f6" },
  Б: { colorVar: "var(--color-amber-500)", colorHex: "#f59e0b" },
  В: { colorVar: "var(--color-emerald-500)", colorHex: "#10b981" },
  Г: { colorVar: "var(--color-slate-500)", colorHex: "#64748b" },
  Д: { colorVar: "var(--color-rose-500)", colorHex: "#f43f5e" },
  Е: { colorVar: "var(--color-indigo-500)", colorHex: "#6366f1" },
  Ж: { colorVar: "var(--color-sky-500)", colorHex: "#0ea5e9" },
  З: { colorVar: "var(--color-violet-500)", colorHex: "#8b5cf6" },
}

const DEFAULT_COLOR = { colorVar: "var(--color-slate-400)", colorHex: "#94a3b8" }

// Match patterns like "А-101", "Б-310", "В-215", "Спорт. зал", "А 501"
const BUILDING_RE = /^([А-ЯA-Z])[\s-]?(\d+.*)$/i

/**
 * Parse a room string into building letter + room number + color.
 * Returns null for unparseable strings (e.g., "Спорт. зал").
 */
export function parseBuildingRoom(room: string | null | undefined): BuildingRoom | null {
  if (!room) return null
  const match = room.trim().match(BUILDING_RE)
  if (!match) return null
  const building = match[1].toUpperCase()
  const roomNum = match[2]
  const colors = BUILDING_COLORS[building] ?? DEFAULT_COLOR
  return { building, room: roomNum, ...colors }
}

/**
 * Extract unique building letters from a list of lessons.
 * Used for day stats: "корпуса А, Б, В"
 */
export function uniqueBuildings(lessons: { room?: string | null }[]): string[] {
  const buildings = new Set<string>()
  for (const l of lessons) {
    const parsed = parseBuildingRoom(l.room)
    if (parsed) buildings.add(parsed.building)
  }
  return [...buildings].sort()
}
