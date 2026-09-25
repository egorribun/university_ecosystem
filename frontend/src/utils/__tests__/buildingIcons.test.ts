import { describe, it, expect } from "vitest"

import { BUILDING_COLORS } from "@/data/campusBuildings"
import { parseBuildingRoom, uniqueBuildings } from "../buildingIcons"

describe("parseBuildingRoom", () => {
  it("parses a multi-char building id and room number", () => {
    const parsed = parseBuildingRoom("ГУК-305")
    expect(parsed).not.toBeNull()
    expect(parsed!.building).toBe("ГУК")
    expect(parsed!.room).toBe("305")
    expect(typeof parsed!.colorVar).toBe("string")
    expect(parsed!.colorHex.startsWith("#")).toBe(true)
  })

  it("returns null for null/empty input", () => {
    expect(parseBuildingRoom(null)).toBeNull()
    expect(parseBuildingRoom(undefined)).toBeNull()
    expect(parseBuildingRoom("")).toBeNull()
  })

  it("returns null when there is no separating dash", () => {
    expect(parseBuildingRoom("Спорт. зал")).toBeNull()
  })

  it("returns null when the dash is at the start (empty building)", () => {
    expect(parseBuildingRoom("-101")).toBeNull()
  })

  it("returns null when the room does not start with a digit", () => {
    expect(parseBuildingRoom("А-абв")).toBeNull()
  })

  it("parses a single-letter building id", () => {
    expect(parseBuildingRoom("А-101")).toEqual({ building: "А", room: "101", ...BUILDING_COLORS.А })
  })

  it("ignores surrounding whitespace", () => {
    expect(parseBuildingRoom("  ПА-201 ")).toEqual({
      building: "ПА",
      room: "201",
      ...BUILDING_COLORS.ПА,
    })
  })

  it("returns null when the room only contains a digit after a letter", () => {
    expect(parseBuildingRoom("ГУК-А305")).toBeNull()
  })

  it("uses the default color for an unknown building id", () => {
    const parsed = parseBuildingRoom("ZZ-1")
    expect(parsed).not.toBeNull()
    expect(parsed!.building).toBe("ZZ")
    expect(parsed!.colorHex).toBe("#94a3b8") // DEFAULT_COLOR
    expect(parsed!.colorVar).toBe("var(--color-slate-400)")
  })
})

describe("uniqueBuildings", () => {
  it("returns sorted, de-duplicated building ids and skips unparseable rooms", () => {
    const result = uniqueBuildings([
      { room: "ПА-2" },
      { room: "ГУК-1" },
      { room: "ГУК-3" }, // duplicate building
      { room: "Спорт. зал" }, // unparseable → skipped
      { room: null }, // skipped
    ])
    expect(result).toEqual(["ГУК", "ПА"]) // sorted, unique
  })

  it("returns an empty array when nothing parses", () => {
    expect(uniqueBuildings([{ room: null }, { room: "lobby" }])).toEqual([])
  })
})
