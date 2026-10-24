/**
 * useScheduleTime — time ticker + time-dependent calculations.
 * Extracted from useScheduleData (Wave 65).
 *
 * FIX-65-03: Pauses ticker when tab is hidden (Page Visibility API)
 * and ticks immediately on tab re-focus to show fresh data.
 */
import { useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { type Lesson, parseMinutes } from "@/components/schedule/scheduleUtils"
import { useCampusTimezone } from "@/contexts/CampusTimezoneContext"
import { getCampusClockParts } from "@/utils/campusTimezone"
import { useScheduleClock } from "./useScheduleClock"

const getLessonBounds = (lesson: Lesson): { start: number; end: number } | null => {
  const start = parseMinutes(lesson.start_time)
  const end = parseMinutes(lesson.end_time)
  return start !== null && end !== null && end > start ? { start, end } : null
}

export function useScheduleTime(todayLessons: Lesson[], hasToday: boolean, externalNow?: Date) {
  const { t } = useTranslation(["schedule"])
  const fallbackNow = useScheduleClock(externalNow === undefined)
  const nowTick = externalNow ?? fallbackNow
  const timeZone = useCampusTimezone()
  const minutesNow = useMemo(() => {
    const clock = getCampusClockParts(nowTick, timeZone)
    return clock ? clock.hour * 60 + clock.minute : null
  }, [nowTick, timeZone])

  const currentLesson = useMemo(() => {
    if (!hasToday || minutesNow === null) return null
    return (
      todayLessons.find((l) => {
        const bounds = getLessonBounds(l)
        return bounds !== null && minutesNow >= bounds.start && minutesNow < bounds.end
      }) || null
    )
  }, [todayLessons, minutesNow, hasToday])

  const nextLesson = useMemo(() => {
    if (!hasToday || minutesNow === null) return null
    if (currentLesson && minutesNow !== null) {
      const endM = getLessonBounds(currentLesson)!.end
      return (
        todayLessons.find((l) => {
          const bounds = getLessonBounds(l)
          return bounds !== null && bounds.start >= endM
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
    if (currentLesson && minutesNow !== null) {
      const end = getLessonBounds(currentLesson)!.end
      const left = Math.max(0, end - minutesNow)
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.current", { duration: formatDuration(h, m) })
    } else if (nextLesson && minutesNow !== null) {
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
    if (currentLesson && minutesNow !== null) {
      const end = getLessonBounds(currentLesson)!.end
      mins = Math.max(0, end - minutesNow)
    } else if (nextLesson && minutesNow !== null) {
      const start = getLessonBounds(nextLesson)!.start
      mins = Math.max(0, start - minutesNow)
    }
    if (mins <= 0 && !currentLesson && !nextLesson) return ""
    const h = Math.floor(mins / 60)
    const m = mins % 60
    if (h > 0 && m > 0)
      return `${h}${t("schedule:time.hoursShort")} ${m}${t("schedule:time.minutesShort")}`
    if (h > 0) return `${h}${t("schedule:time.hoursShort")}`
    return `${m}${t("schedule:time.minutesShort")}`
  }, [currentLesson, nextLesson, minutesNow, t])

  const currentProgress = useMemo(() => {
    if (!currentLesson || minutesNow === null) return 0
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
