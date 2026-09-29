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

  it("maps every documented WMO code to its condition", () => {
    const expected: Array<[number, string]> = [
      [0, "clear"],
      [1, "clear"],
      [2, "cloudy"],
      [3, "cloudy"],
      [45, "fog"],
      [48, "fog"],
      [51, "rain"],
      [53, "rain"],
      [55, "rain"],
      [56, "rain"],
      [57, "rain"],
      [61, "rain"],
      [63, "rain"],
      [65, "rain"],
      [66, "rain"],
      [67, "rain"],
      [71, "snow"],
      [73, "snow"],
      [75, "snow"],
      [77, "snow"],
      [80, "rain"],
      [81, "rain"],
      [82, "rain"],
      [85, "snow"],
      [86, "snow"],
      [95, "storm"],
      [96, "storm"],
      [99, "storm"],
    ]
    expect(expected.map(([code]) => [code, wmoToCondition(code)])).toEqual(expected)
  })
})
