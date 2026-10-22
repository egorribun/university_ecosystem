import { useEffect, useState } from "react"

const TICKER_INTERVAL_MS = 30_000

/** Share an actual minute-granular instant without creating a second active ticker. */
export function useScheduleClock(enabled = true): Date {
  const [nowTick, setNowTick] = useState(() => new Date())

  useEffect(() => {
    if (!enabled) return
    const tick = () => {
      if (document.visibilityState === "hidden") return
      const now = new Date()
      const minute = Math.floor(now.getTime() / 60_000)
      setNowTick((previous) => {
        const previousMinute = Math.floor(previous.getTime() / 60_000)
        return previousMinute === minute ? previous : now
      })
    }
    const id = setInterval(tick, TICKER_INTERVAL_MS)
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") tick()
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    tick()
    return () => {
      clearInterval(id)
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [enabled])

  return nowTick
}
