import { describe, expect, it } from "vitest"

import {
  ALL_EVENT_CATEGORIES,
  getCategoryMeta,
  inferEventCategory,
  type EventCategory,
} from "@/features/events/categories"

describe("event category inference fallbacks", () => {
  it.each([
    ["public lecture", "lecture"],
    ["research seminar", "seminar"],
    ["technology conference", "conference"],
    ["design workshop", "workshop"],
    ["student meetup", "social"],
    ["football tournament", "sport"],
  ] as const)("classifies %s as %s", (eventType, expected) => {
    expect(inferEventCategory(eventType)).toBe(expected)
  })

  it("classifies an absent event type as other", () => {
    expect(inferEventCategory(null)).toBe("other")
  })

  it("classifies a non-empty unmatched event type as other", () => {
    expect(inferEventCategory("board meeting without a known category keyword")).toBe("other")
  })

  it("returns metadata for known and defensive fallback categories", () => {
    expect(getCategoryMeta("lecture")).toEqual({
      labelKey: "events:categories.lecture",
      color: "blue",
    })
    expect(getCategoryMeta("unknown" as EventCategory)).toEqual({
      labelKey: "events:categories.other",
      color: "slate",
    })
    expect(ALL_EVENT_CATEGORIES.map(({ id }) => id)).toEqual([
      "lecture",
      "seminar",
      "conference",
      "workshop",
      "social",
      "sport",
      "other",
    ])
  })
})
