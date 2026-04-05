/**
 * useScheduleTime — time ticker + time-dependent calculations.
 * Extracted from useScheduleData (Wave 65).
 *
 * FIX-65-03: Pauses ticker when tab is hidden (Page Visibility API)
 * and ticks immediately on tab re-focus to show fresh data.
 */
import { useState, useEffect, useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import {
  type Lesson,
  parseMinutes,
} from "@/components/schedule/scheduleUtils"

const TICKER_INTERVAL_MS = 30_000

export function useScheduleTime(
  todayLessons: Lesson[],
  hasToday: boolean,
) {
  const { t } = useTranslation(["schedule"])
  const [nowTick, setNowTick] = useState(new Date())

  // Timer with Page Visibility API optimization
  useEffect(() => {
    const tick = () => {
      // Skip tick when tab is hidden — saves battery & avoids wasted re-renders
      if (document.visibilityState === "hidden") return
      setNowTick((prev) => {
        const now = new Date()
        if (now.getMinutes() === prev.getMinutes() && now.getHours() === prev.getHours()) {
          return prev // same minute — no state update, no re-render
        }
        return now
      })
    }
    const id = setInterval(tick, TICKER_INTERVAL_MS)
    // Tick immediately when tab becomes visible again
    const onVisible = () => {
      if (document.visibilityState === "visible") tick()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [])

  const minutesNow = useMemo(() => nowTick.getHours() * 60 + nowTick.getMinutes(), [nowTick])

  const currentLesson = useMemo(() => {
    if (!hasToday) return null
    return (
      todayLessons.find((l) => {
        const s = parseMinutes(l.start_time) ?? -1
        const e = parseMinutes(l.end_time) ?? -1
        return minutesNow >= s && minutesNow < e
      }) || null
    )
  }, [todayLessons, minutesNow, hasToday])

  const nextLesson = useMemo(() => {
    if (!hasToday) return null
    if (currentLesson) {
      const endM = parseMinutes(currentLesson.end_time) ?? 0
      return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow, hasToday])

  const formatDuration = useCallback(
    (hours: number, minutes: number) => {
      const parts: string[] = []
      if (hours > 0) {
        parts.push(t("schedule:time.hours", { count: hours }))
      }
      if (minutes > 0 || hours === 0) {
        parts.push(t("schedule:time.minutes", { count: minutes }))
      }
      return parts.join(" ")
    },
    [t]
  )

  const timeLeftText = useMemo(() => {
    let text = ""
    if (currentLesson) {
      const end = parseMinutes(currentLesson.end_time) ?? 0
      const left = Math.max(0, end - minutesNow)
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.current", { duration: formatDuration(h, m) })
    } else if (nextLesson) {
      const start = parseMinutes(nextLesson.start_time) ?? 0
      const left = Math.max(0, start - minutesNow)
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.next", { duration: formatDuration(h, m) })
    }
    return text
  }, [currentLesson, nextLesson, minutesNow, t, formatDuration])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time)
    const e = parseMinutes(currentLesson.end_time)
    if (s == null || e == null || e <= s) return 0
    const span = e - s
    const passed = Math.min(Math.max(minutesNow - s, 0), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  return {
    nowTick,
    currentLesson,
    nextLesson,
    timeLeftText,
    currentProgress,
  }
}
