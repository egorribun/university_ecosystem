import { useEffect, useState } from "react"

const MINUTE_MS = 60_000

/**
 * Current time in epoch ms, refreshed once a minute. Memos that decide "live",
 * "ended" or "upcoming" take this value as a dependency so they re-evaluate as
 * the clock passes an event boundary instead of freezing at mount time.
 */
export function useMinuteClock(): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), MINUTE_MS)
    return () => window.clearInterval(timer)
  }, [])

  return now
}
