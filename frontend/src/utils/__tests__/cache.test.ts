import { describe, it, expect } from "vitest"

import { parseCacheVersion } from "../cache"

describe("parseCacheVersion", () => {
  it("returns finite numbers unchanged", () => {
    expect(parseCacheVersion(123)).toBe(123)
    expect(parseCacheVersion(0)).toBe(0)
  })

  it("parses numeric strings", () => {
    expect(parseCacheVersion("456")).toBe(456)
  })

  it("parses date strings via Date.parse", () => {
    expect(parseCacheVersion("2026-01-01T00:00:00.000Z")).toBe(
      Date.parse("2026-01-01T00:00:00.000Z")
    )
  })

  it("returns undefined for non-numeric, non-date strings", () => {
    expect(parseCacheVersion("not-a-date")).toBeUndefined()
  })

  it("returns undefined for non-finite numbers and other types", () => {
    expect(parseCacheVersion(Number.NaN)).toBeUndefined()
    expect(parseCacheVersion(Number.POSITIVE_INFINITY)).toBeUndefined()
    expect(parseCacheVersion(null)).toBeUndefined()
    expect(parseCacheVersion({})).toBeUndefined()
  })
})
