import { describe, expect, it, vi } from "vitest"

import { eventsListQueryKey } from "@/api/hooks/events"

describe("events list runtime-boundary contracts", () => {
  it("keeps the runtime type guard ahead of numeric normalization", () => {
    // Number.isFinite normally rejects objects before coercion.  Returning true
    // here makes the ordering observable: a mutation that removes the
    // typeof guard would coerce this object through <= and Math.floor instead
    // of using the safe page-size fallback.
    const finiteSpy = vi.spyOn(Number, "isFinite").mockReturnValue(true)
    const coercibleLimit = {
      valueOf: () => 3.9,
    } as unknown as number

    try {
      expect(eventsListQueryKey({ language: "en", limit: coercibleLimit })[2].limit).toBe(12)
    } finally {
      finiteSpy.mockRestore()
    }
  })
})
