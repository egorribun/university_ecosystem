import { useState, useEffect } from "react"
import { pad } from "@/utils/scheduleUtils"

const getCurrentMinute = (now = new Date()) => {
  const d = new Date(now)
  d.setSeconds(0, 0)
  return d
}

export function useClock(locale: string) {
  // Keep SSR and the browser's first render independent of their timezones.
  // The live local clock is only available after hydration.
  const [time, setTime] = useState(() => new Date(0))
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const tick = () => setTime(getCurrentMinute())
    const now = new Date()
    setTime(getCurrentMinute(now))
    setIsReady(true)

    let intervalId: number | null = null
    const msUntilNextMinute = (60 - now.getSeconds()) * 1000 - now.getMilliseconds()
    const timeoutId = window.setTimeout(() => {
      tick()
      intervalId = window.setInterval(tick, 60_000)
    }, msUntilNextMinute)
    return () => {
      window.clearTimeout(timeoutId)
      if (intervalId) {
        window.clearInterval(intervalId)
      }
    }
  }, [])

  const hh = isReady ? pad(time.getHours()) : "--"
  const mm = isReady ? pad(time.getMinutes()) : "--"
  const dateStr = isReady
    ? time.toLocaleDateString(locale, {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : ""

  return { hh, mm, dateStr, time, isReady }
}
