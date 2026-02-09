import { describe, expect, it } from "vitest"

import {
  availableCampusPointLocales,
  getCampusPointsForLocale,
  type CampusPointEntry,
} from "@/data/campusPoints"
import systemEn from "@/i18n/locales/en/system.json"

const collectById = (points: CampusPointEntry[]) =>
  points.reduce<Record<string, CampusPointEntry>>((acc, point) => {
    acc[point.id] = point
    return acc
  }, {})

describe("campus points data", () => {
  const enPoints = getCampusPointsForLocale("en")
  const ruPoints = getCampusPointsForLocale("ru")

  it("lists available locales", () => {
    expect(availableCampusPointLocales).toEqual(expect.arrayContaining(["en", "ru"]))
  })

  it("keeps point identifiers and tags in sync across locales", () => {
    const enById = collectById(enPoints)
    const ruById = collectById(ruPoints)

    expect(Object.keys(ruById)).toEqual(Object.keys(enById))

    for (const [id, enPoint] of Object.entries(enById)) {
      const ruPoint = ruById[id]
      expect(ruPoint).toBeDefined()
      expect(ruPoint?.tags).toEqual(enPoint.tags)
    }
  })

  it("falls back to english data for unsupported locales", () => {
    expect(getCampusPointsForLocale("en-US")).toEqual(enPoints)
    expect(getCampusPointsForLocale("de")).toEqual(enPoints)
  })

  it("provides translations for every tag", () => {
    const tagTranslations = systemEn.map.fallback.tags

    const tags = new Set<string>()
    for (const point of enPoints) {
      for (const tag of point.tags) {
        tags.add(tag)
      }
    }

    for (const tag of tags) {
      expect(tagTranslations[tag as keyof typeof tagTranslations]).toBeTruthy()
    }
  })
})




