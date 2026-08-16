/**
 * useScheduleReminders — Notification reminders for schedule lessons.
 * Wave 66 (Idea #11). Uses Notification API + Service Worker.
 * Reminder preferences stored in IndexedDB via idb-keyval.
 */
import { useState, useEffect, useCallback, useRef } from "react"
import { useTranslation } from "react-i18next"
import { get, set } from "idb-keyval"
import { type Lesson, parseMinutes } from "@/components/schedule/scheduleUtils"
import { logError } from "@/app/logger"

const REMINDER_PREFS_KEY = "schedule:reminder-prefs"
const REMINDED_TODAY_KEY = "schedule:reminded-today"

export type ReminderTiming = 0 | 5 | 10 | 15 | 30

export interface ReminderPrefs {
  /** Minutes before lesson start. 0 = disabled */
  minutesBefore: ReminderTiming
  /** Per-lesson overrides (lessonId → minutesBefore). 0 = disabled for that lesson */
  overrides: Record<string, ReminderTiming>
}

const DEFAULT_PREFS: ReminderPrefs = {
  minutesBefore: 15,
  overrides: {},
}

const localDateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`

export function useScheduleReminders(todayLessons: Lesson[]) {
  const { t } = useTranslation(["schedule"])
  const [prefs, setPrefsState] = useState<ReminderPrefs>(DEFAULT_PREFS)
  const [permission, setPermission] = useState<NotificationPermission>("default")
  const [dayKey, setDayKey] = useState(() => localDateKey(new Date()))
  const [hydratedDay, setHydratedDay] = useState<string | null>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const remindedRef = useRef<Set<string>>(new Set())

  // Roll the day scope at the next local midnight. A fresh one-shot timeout is
  // scheduled after each rollover so DST-length days do not accumulate drift.
  useEffect(() => {
    const now = new Date()
    const nextMidnight = new Date(now)
    nextMidnight.setHours(24, 0, 0, 0)
    const timer = setTimeout(() => {
      setDayKey(localDateKey(nextMidnight))
    }, nextMidnight.getTime() - now.getTime())

    return () => clearTimeout(timer)
  }, [dayKey])

  // Load prefs and the current local day's reminded IDs from IndexedDB.
  useEffect(() => {
    let cancelled = false
    setHydratedDay(null)
    remindedRef.current = new Set()

    const storedPrefs = get<ReminderPrefs>(REMINDER_PREFS_KEY).catch((err) => {
      logError("[schedule:reminders]", err)
      return undefined
    })
    const remindedIds = get<string[]>(`${REMINDED_TODAY_KEY}:${dayKey}`).catch((err) => {
      logError("[schedule:reminders]", err)
      return undefined
    })

    void Promise.all([storedPrefs, remindedIds]).then(([stored, ids]) => {
      if (cancelled) return
      if (stored) setPrefsState(stored)
      remindedRef.current = new Set(ids ?? [])
      setHydratedDay(dayKey)
    })

    return () => {
      cancelled = true
    }
  }, [dayKey])

  // Check notification permission
  useEffect(() => {
    if ("Notification" in window) {
      setPermission(Notification.permission)
    }
  }, [])

  // Update prefs
  const setPrefs = useCallback(async (update: Partial<ReminderPrefs>) => {
    setPrefsState((prev) => {
      const next = { ...prev, ...update }
      set(REMINDER_PREFS_KEY, next).catch((err) => logError("[schedule:reminders]", err))
      return next
    })
  }, [])

  // Request notification permission
  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!("Notification" in window)) return false
    if (Notification.permission === "granted") {
      setPermission("granted")
      return true
    }
    const result = await Notification.requestPermission()
    setPermission(result)
    return result === "granted"
  }, [])

  // Schedule reminders for today's lessons.
  // Timer lifecycle: when deps change (prefs, lessons, permission), the cleanup
  // function clears ALL pending timers before the effect re-runs and schedules
  // new ones. This prevents the race condition where old timers fire after a
  // preference change (FIX-68-04).
  useEffect(() => {
    if (hydratedDay !== dayKey) return
    if (prefs.minutesBefore === 0) return
    if (permission !== "granted") {
      if (prefs.minutesBefore > 0 && todayLessons.length > 0) {
        if (import.meta.env.DEV)
          logError("[schedule:reminders] Reminders enabled but notification permission denied")
      }
      return
    }
    if (todayLessons.length === 0) return

    const now = new Date()
    const nowMinutes = now.getHours() * 60 + now.getMinutes()
    const scheduledIds = new Set<string>()

    for (const lesson of todayLessons) {
      const lessonMinutesBefore = prefs.overrides[lesson.id] ?? prefs.minutesBefore
      if (lessonMinutesBefore === 0) continue

      const startMin = parseMinutes(lesson.start_time)
      if (startMin == null) continue

      const remindAt = startMin - lessonMinutesBefore
      const delayMs = (remindAt - nowMinutes) * 60_000

      // Skip if already past or already reminded
      if (delayMs <= 0) continue
      if (remindedRef.current.has(lesson.id)) continue
      if (scheduledIds.has(lesson.id)) continue
      scheduledIds.add(lesson.id)

      const timer = setTimeout(async () => {
        // Mark as reminded
        remindedRef.current.add(lesson.id)
        set(`${REMINDED_TODAY_KEY}:${dayKey}`, [...remindedRef.current]).catch((err) =>
          logError("[schedule:reminders]", err)
        )

        // Show notification
        const title = t("schedule:reminder.title")
        const body = t("schedule:reminder.body", {
          subject: lesson.subject ?? "",
          minutes: lessonMinutesBefore,
        })
        const options: NotificationOptions = {
          body,
          icon: "/assets/guu_logo.png",
          badge: "/assets/guu_logo.png",
          tag: `lesson-${lesson.id}`,
        }

        try {
          const reg = await navigator.serviceWorker?.ready
          if (reg) {
            await reg.showNotification(title, options)
          } else {
            new Notification(title, options)
          }
        } catch (err) {
          logError("[schedule:reminders] Notification failed", err)
        }
      }, delayMs)

      timersRef.current.push(timer)
    }

    return () => {
      for (const timer of timersRef.current) clearTimeout(timer)
      timersRef.current = []
    }
  }, [todayLessons, prefs, permission, hydratedDay, dayKey, t])

  return {
    prefs,
    setPrefs,
    permission,
    requestPermission,
    isEnabled: prefs.minutesBefore > 0 && permission === "granted",
  }
}
