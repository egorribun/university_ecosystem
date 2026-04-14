import { useState, useEffect } from "react"

export type TimePeriod = "dawn" | "morning" | "afternoon" | "dusk" | "night"

function getTimePeriod(): TimePeriod {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 7) return "dawn"
  if (hour >= 7 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour < 20) return "dusk"
  return "night"
}

/**
 * Reactive time-of-day period — updates every minute.
 * Returns dawn/morning/afternoon/dusk/night for CSS atmosphere tokens.
 * Wave 108
 */
export function useTimeOfDay(): TimePeriod {
  const [period, setPeriod] = useState(getTimePeriod)

  useEffect(() => {
    const id = setInterval(() => setPeriod(getTimePeriod()), 60_000)
    return () => clearInterval(id)
  }, [])

  return period
}
