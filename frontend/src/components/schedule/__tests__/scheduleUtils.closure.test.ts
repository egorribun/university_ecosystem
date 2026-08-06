import { describe, expect, it } from "vitest"

import { minutesDiff, parseMinutes } from "@/components/schedule/scheduleUtils"

describe("schedule time parser closure", () => {
  it("uses the full-date fallback for valid timestamps and rejects invalid dates", () => {
    expect(parseMinutes("2026-04-26T09:30:00Z")).not.toBeNull()
    expect(parseMinutes("not-a-real-date")).toBeNull()
  })

  it("uses zero defaults when either minutes-diff input is missing or invalid", () => {
    expect(minutesDiff(null, "not-a-real-date")).toBe(0)
  })
})
