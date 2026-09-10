import { describe, expect, it } from "vitest"

import { NEWS_PAGE_SIZE, normalizeNewsListLimit } from "@/api/hooks/news"

describe("news list limit mutation contract", () => {
  it("accepts only finite positive numbers and falls back for every invalid boundary", () => {
    expect(normalizeNewsListLimit(1)).toBe(1)
    expect(normalizeNewsListLimit(20.9)).toBe(20)
    for (const value of [undefined, 0, 0.5, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(normalizeNewsListLimit(value)).toBe(NEWS_PAGE_SIZE)
    }
  })
})
