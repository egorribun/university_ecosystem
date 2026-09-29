import { afterEach, describe, expect, it, vi } from "vitest"

import { hasInvalidEventDates } from "@/components/events/EventCreateDialog"

afterEach(() => {
  vi.restoreAllMocks()
})

describe("EventCreateDialog date-validation guard", () => {
  it("does not compare an infinite start timestamp", () => {
    vi.spyOn(Date, "parse")
      .mockReturnValueOnce(Number.POSITIVE_INFINITY)
      .mockReturnValueOnce(Date.UTC(2026, 0, 15, 12))

    expect(hasInvalidEventDates("infinite-start", "valid-end")).toBe(false)
  })

  it("does not compare a negative-infinite end timestamp", () => {
    vi.spyOn(Date, "parse")
      .mockReturnValueOnce(Date.UTC(2026, 0, 15, 10))
      .mockReturnValueOnce(Number.NEGATIVE_INFINITY)

    expect(hasInvalidEventDates("valid-start", "infinite-end")).toBe(false)
  })
})
