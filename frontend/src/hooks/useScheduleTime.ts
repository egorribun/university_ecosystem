/**
 * useScheduleTime — time ticker + time-dependent calculations.
 * Extracted from useScheduleData (Wave 65).
 *
 * FIX-65-03: Pauses ticker when tab is hidden (Page Visibility API)
 * and ticks immediately on tab re-focus to show fresh data.
 */
import { useState, useEffect, useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { type Lesson, parseMinutes } from "@/components/schedule/scheduleUtils"

/**
 * Tick every 30s — sub-minute precision isn't needed for schedule display,
 * and longer intervals reduce battery drain on mobile. The tick function
 * skips state updates if the minute hasn't changed, so re-renders are
 * effectively minute-granular regardless.
 */
const TICKER_INTERVAL_MS = 30_000

const getLessonBounds = (lesson: Lesson): { start: number; end: number } | null => {
  const start = parseMinutes(lesson.start_time)
  const end = parseMinutes(lesson.end_time)
  return start !== null && end !== null && end > start ? { start, end } : null
}

export function useScheduleTime(todayLessons: Lesson[], hasToday: boolean) {
  const { t } = useTranslation(["schedule"])
  const [nowTick, setNowTick] = useState(new Date())

  // Timer with Page Visibility API optimization.
  // NOTE: setNowTick's functional updater form is safe even if the component
  // unmounts mid-interval — React silently discards updates on unmounted
  // components when using the `prev => ...` pattern (FIX-68-03).
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
        const bounds = getLessonBounds(l)
        return bounds !== null && minutesNow >= bounds.start && minutesNow < bounds.end
      }) || null
    )
  }, [todayLessons, minutesNow, hasToday])

  const nextLesson = useMemo(() => {
    if (!hasToday) return null
    if (currentLesson) {
      const endM = getLessonBounds(currentLesson)!.end
      return (
        todayLessons.find((l) => {
          const bounds = getLessonBounds(l)
          return bounds !== null && bounds.start > endM
        }) || null
      )
    }
    return (
      todayLessons.find((l) => {
        const bounds = getLessonBounds(l)
        return bounds !== null && bounds.start > minutesNow
      }) || null
    )
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
      const end = getLessonBounds(currentLesson)!.end
      const left = Math.max(0, end - minutesNow)
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.current", { duration: formatDuration(h, m) })
    } else if (nextLesson) {
      const start = getLessonBounds(nextLesson)!.start
      const left = Math.max(0, start - minutesNow)
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.next", { duration: formatDuration(h, m) })
    }
    return text
  }, [currentLesson, nextLesson, minutesNow, t, formatDuration])

  // Wave 71b: compact duration — "7ч 22м" / "22м" for badge display
  const timeLeftShort = useMemo(() => {
    let mins = 0
    if (currentLesson) {
      const end = getLessonBounds(currentLesson)!.end
      mins = Math.max(0, end - minutesNow)
    } else if (nextLesson) {
      const start = getLessonBounds(nextLesson)!.start
      mins = Math.max(0, start - minutesNow)
    }
    if (mins <= 0 && !currentLesson && !nextLesson) return ""
    const h = Math.floor(mins / 60)
    const m = mins % 60
    if (h > 0 && m > 0)
      return `${h}${t("schedule:time.hoursShort", { defaultValue: "h" })} ${m}${t("schedule:time.minutesShort", { defaultValue: "m" })}`
    if (h > 0) return `${h}${t("schedule:time.hoursShort", { defaultValue: "h" })}`
    return `${m}${t("schedule:time.minutesShort", { defaultValue: "m" })}`
  }, [currentLesson, nextLesson, minutesNow, t])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const { start, end } = getLessonBounds(currentLesson)!
    const span = end - start
    const passed = Math.min(Math.max(minutesNow - start, 0), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  return {
    nowTick,
    currentLesson,
    nextLesson,
    timeLeftText,
    timeLeftShort,
    currentProgress,
  }
}
