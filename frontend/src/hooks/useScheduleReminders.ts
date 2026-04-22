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

export function useScheduleReminders(todayLessons: Lesson[]) {
  const { t } = useTranslation(["schedule"])
  const [prefs, setPrefsState] = useState<ReminderPrefs>(DEFAULT_PREFS)
  const [permission, setPermission] = useState<NotificationPermission>("default")
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const remindedRef = useRef<Set<string>>(new Set())

  // Load prefs from IndexedDB
  useEffect(() => {
    get<ReminderPrefs>(REMINDER_PREFS_KEY)
      .then((stored) => {
        if (stored) setPrefsState(stored)
      })
      .catch((err) => logError("[schedule:reminders]", err))

    // Load already-reminded set for today
    const todayKey = new Date().toISOString().slice(0, 10)
    get<string[]>(`${REMINDED_TODAY_KEY}:${todayKey}`)
      .then((ids) => {
        if (ids) remindedRef.current = new Set(ids)
      })
      .catch((err) => logError("[schedule:reminders]", err))

    // Check notification permission
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
    // Clear previous timers — ensures no stale reminders fire
    for (const timer of timersRef.current) clearTimeout(timer)
    timersRef.current = []

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
    const todayKey = now.toISOString().slice(0, 10)

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

      const timer = setTimeout(async () => {
        // Mark as reminded
        remindedRef.current.add(lesson.id)
        set(`${REMINDED_TODAY_KEY}:${todayKey}`, [...remindedRef.current]).catch((err) =>
          logError("[schedule:reminders]", err)
        )

        // Show notification
        const title = t("schedule:reminder.title", { defaultValue: "Lesson starting soon" })
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
  }, [todayLessons, prefs, permission, t])

  return {
    prefs,
    setPrefs,
    permission,
    requestPermission,
    isEnabled: prefs.minutesBefore > 0 && permission === "granted",
  }
}
