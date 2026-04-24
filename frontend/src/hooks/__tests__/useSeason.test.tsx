import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useSeason } from "../useSeason"

describe("useSeason", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  const MONTH_SEASON_PAIRS = [
    // spring: March–May (months 2–4)
    { month: 2, expected: "spring" },
    { month: 3, expected: "spring" },
    { month: 4, expected: "spring" },
    // summer: June–August (months 5–7)
    { month: 5, expected: "summer" },
    { month: 6, expected: "summer" },
    { month: 7, expected: "summer" },
    // autumn: September–November (months 8–10)
    { month: 8, expected: "autumn" },
    { month: 9, expected: "autumn" },
    { month: 10, expected: "autumn" },
    // winter: December–February (months 11, 0, 1)
    { month: 11, expected: "winter" },
    { month: 0, expected: "winter" },
    { month: 1, expected: "winter" },
  ] as const

  it.each(MONTH_SEASON_PAIRS)(
    "returns '$expected' when the month is $month",
    ({ month, expected }) => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2025, month, 15, 12, 0, 0))
      const { result } = renderHook(() => useSeason())
      expect(result.current).toBe(expected)
    }
  )
})
