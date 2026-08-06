import { describe, it, expect } from "vitest"

import { CAMPUS_POIS, POI_CATEGORY_COLORS, type POICategory } from "@/data/campusPOI"

const CATEGORIES: POICategory[] = ["transport", "food", "shop", "service", "campus"]
const ICONS = new Set([
  "TrainFront",
  "Bus",
  "UtensilsCrossed",
  "Coffee",
  "ShoppingCart",
  "ShoppingBag",
  "Pill",
  "Landmark",
  "ParkingCircle",
  "MapPin",
  "BookOpen",
])

describe("campusPOI data", () => {
  it("exposes the verified set of campus POIs", () => {
    expect(Array.isArray(CAMPUS_POIS)).toBe(true)
    expect(CAMPUS_POIS).toHaveLength(11)
  })

  it("gives every POI a unique id", () => {
    const ids = CAMPUS_POIS.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it("keeps every POI well-formed (type, coords, icon, i18nKey)", () => {
    for (const poi of CAMPUS_POIS) {
      expect(typeof poi.id).toBe("string")
      expect(CATEGORIES).toContain(poi.type)
      expect(poi.coords).toHaveLength(2)
      expect(typeof poi.coords[0]).toBe("number")
      expect(typeof poi.coords[1]).toBe("number")
      expect(ICONS.has(poi.icon)).toBe(true)
      expect(typeof poi.i18nKey).toBe("string")
      expect(poi.i18nKey!.length).toBeGreaterThan(0)
    }
  })

  it("maps every category to a map-poi CSS variable colour", () => {
    expect(Object.keys(POI_CATEGORY_COLORS)).toHaveLength(5)
    for (const category of CATEGORIES) {
      expect(POI_CATEGORY_COLORS[category]).toBe(`var(--map-poi-${category})`)
    }
  })

  it("only uses categories that have a colour mapping", () => {
    for (const poi of CAMPUS_POIS) {
      expect(POI_CATEGORY_COLORS[poi.type]).toBeDefined()
    }
  })
})
