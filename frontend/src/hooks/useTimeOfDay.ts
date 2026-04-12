import { useMemo } from "react"

/**
 * useTimeOfDay — returns current time period for atmosphere theming.
 *
 * Computed on mount only (map visits are short).
 * Used via `data-time-period` CSS attribute selector in map.css.
 *
 * Wave 98
 */

export type TimePeriod = "dawn" | "morning" | "afternoon" | "dusk" | "night"

export function useTimeOfDay(): TimePeriod {
  return useMemo(() => {
    const hour = new Date().getHours()
    if (hour >= 5 && hour < 8) return "dawn"
    if (hour >= 8 && hour < 12) return "morning"
    if (hour >= 12 && hour < 17) return "afternoon"
    if (hour >= 17 && hour < 20) return "dusk"
    return "night"
  }, [])
}
