import { describe, expect, it } from "vitest"
import { Route as ActivityRoute } from "../_auth/activity"

type SearchResult = Record<string, unknown>
type SearchValidator = (search: Record<string, unknown>) => SearchResult

const validateActivitySearch = ActivityRoute.options.validateSearch as SearchValidator | undefined

function parseActivitySearch(search: Record<string, unknown>): SearchResult {
  if (!validateActivitySearch) {
    throw new Error("Activity route search validation is not configured")
  }

  return validateActivitySearch(search)
}

describe("Activity route search validation", () => {
  it("falls back from unsupported period values instead of rejecting the route", () => {
    expect(() => parseActivitySearch({ p: "next-semester" })).not.toThrow()
    expect(parseActivitySearch({ p: "next-semester" }).p).toBeUndefined()
  })

  it("preserves supported periods and accepts an omitted period", () => {
    expect(parseActivitySearch({ p: "30d" }).p).toBe("30d")
    expect(parseActivitySearch({}).p).toBeUndefined()
  })
})
