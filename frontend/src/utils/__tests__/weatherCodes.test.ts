import { describe, it, expect } from "vitest"

import { wmoToCondition } from "../weatherCodes"

describe("wmoToCondition", () => {
  it("maps known WMO codes to their condition", () => {
    expect(wmoToCondition(0)).toBe("clear")
    expect(wmoToCondition(2)).toBe("cloudy")
    expect(wmoToCondition(45)).toBe("fog")
    expect(wmoToCondition(61)).toBe("rain")
    expect(wmoToCondition(75)).toBe("snow")
    expect(wmoToCondition(95)).toBe("storm")
  })

  it("falls back to 'clear' for unknown codes", () => {
    expect(wmoToCondition(999)).toBe("clear")
    expect(wmoToCondition(-1)).toBe("clear")
  })
})
