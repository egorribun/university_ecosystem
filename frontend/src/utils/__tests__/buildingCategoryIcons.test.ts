import { describe, it, expect } from "vitest"
import { BookOpen, Building2, Dumbbell } from "lucide-react"
import type { MapCategory } from "@/data/campusBuildings"

import { getPrimaryIcon } from "../buildingCategoryIcons"

describe("getPrimaryIcon", () => {
  it("returns the icon for the first matching tag", () => {
    expect(getPrimaryIcon(["study"])).toBe(BookOpen)
  })

  it("respects ordering — the first recognised tag wins", () => {
    // sports comes first → Dumbbell, even though food is also recognised
    expect(getPrimaryIcon(["sports", "food"])).toBe(Dumbbell)
  })

  it("falls back to Building2 for unrecognised tags", () => {
    expect(getPrimaryIcon(["totally-unknown" as MapCategory])).toBe(Building2)
  })

  it("falls back to Building2 for an empty tag list", () => {
    expect(getPrimaryIcon([])).toBe(Building2)
  })
})
