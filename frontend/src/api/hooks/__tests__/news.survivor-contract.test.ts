import { describe, expect, it } from "vitest"

import { normalizeNewsListLimit } from "@/api/hooks/news"

describe("news list runtime-boundary contracts", () => {
  it("rejects an object even when it can be coerced to a finite number", () => {
    const coercibleLimit = {
      valueOf: () => 7.9,
    } as unknown as number

    expect(normalizeNewsListLimit(coercibleLimit)).toBe(12)
  })
})
