import { renderHook, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const { idbGet, idbSet } = vi.hoisted(() => ({ idbGet: vi.fn(), idbSet: vi.fn() }))
vi.mock("idb-keyval", () => ({ get: idbGet, set: idbSet }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))

import { useScheduleReminders, type ReminderPrefs } from "@/hooks/useScheduleReminders"
import type { Lesson } from "@/components/schedule/scheduleUtils"

const notifications: Array<{ title: string; options?: NotificationOptions }> = []
let requestPermissionMock: ReturnType<typeof vi.fn>

class MockNotification {
  static permission: NotificationPermission = "default"
  static requestPermission = (...args: unknown[]) => requestPermissionMock(...args)
  title: string
  options?: NotificationOptions
  constructor(title: string, options?: NotificationOptions) {
    this.title = title
    this.options = options
    notifications.push({ title, options })
  }
}

const lesson = (over: Partial<Lesson> = {}): Lesson => ({
  id: "l1",
  weekday: "monday",
  parity: "both",
  start_time: "12:00",
  end_time: "13:30",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "ГУК-305",
  lesson_type: "lecture",
  ...over,
})

const flush = () =>
  act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })

beforeEach(() => {
  idbGet.mockReset().mockResolvedValue(undefined)
  idbSet.mockReset().mockResolvedValue(undefined)
  notifications.length = 0
  requestPermissionMock = vi.fn(async () => "granted" as NotificationPermission)
  MockNotification.permission = "default"
  vi.stubGlobal("Notification", MockNotification)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("useScheduleReminders", () => {
  it("defaults to 15-minutes-before and disabled when permission is default", async () => {
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    expect(result.current.prefs.minutesBefore).toBe(15)
    expect(result.current.permission).toBe("default")
    expect(result.current.isEnabled).toBe(false)
  })

  it("loads stored prefs from IndexedDB on mount", async () => {
    const stored: ReminderPrefs = { minutesBefore: 30, overrides: {} }
    idbGet.mockImplementation((key: string) =>
      Promise.resolve(key === "schedule:reminder-prefs" ? stored : undefined)
    )
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    expect(result.current.prefs.minutesBefore).toBe(30)
  })

  it("reflects granted permission from the Notification API", async () => {
    MockNotification.permission = "granted"
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    expect(result.current.permission).toBe("granted")
    expect(result.current.isEnabled).toBe(true)
  })

  it("requestPermission returns true immediately when already granted", async () => {
    MockNotification.permission = "granted"
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    let granted: boolean | undefined
    await act(async () => {
      granted = await result.current.requestPermission()
    })
    expect(granted).toBe(true)
    expect(requestPermissionMock).not.toHaveBeenCalled()
  })

  it("requestPermission asks the Notification API when permission is default", async () => {
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    let granted: boolean | undefined
    await act(async () => {
      granted = await result.current.requestPermission()
    })
    expect(requestPermissionMock).toHaveBeenCalledOnce()
    expect(granted).toBe(true)
    expect(result.current.permission).toBe("granted")
  })

  it("reports a denied permission result without enabling reminders", async () => {
    requestPermissionMock.mockResolvedValueOnce("denied" as NotificationPermission)
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()

    let granted: boolean | undefined
    await act(async () => {
      granted = await result.current.requestPermission()
    })

    expect(granted).toBe(false)
    expect(result.current.permission).toBe("denied")
    expect(result.current.isEnabled).toBe(false)
  })

  it("setPrefs updates state and persists to IndexedDB", async () => {
    const { result } = renderHook(() => useScheduleReminders([]))
    await flush()
    await act(async () => {
      await result.current.setPrefs({ minutesBefore: 5 })
    })
    expect(result.current.prefs.minutesBefore).toBe(5)
    expect(idbSet).toHaveBeenCalledWith(
      "schedule:reminder-prefs",
      expect.objectContaining({ minutesBefore: 5 })
    )
  })

  it("schedules and fires a reminder notification for an upcoming lesson", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    renderHook(() => useScheduleReminders([lesson({ start_time: "12:00" })]))
    // Flush the mount effect (permission read + IDB loads) under fake timers
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    // remindAt = 720 (12:00) - 15 = 705 min; now = 600 (10:00) → delay 105 min
    await act(async () => {
      await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
    })
    expect(notifications.length).toBeGreaterThanOrEqual(1)
    expect(notifications[0]!.title).toBe("schedule:reminder.title")
  })

  it("uses the service worker and tolerates persistence and display failures", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    idbSet.mockRejectedValue(new Error("persistence failed"))
    const showNotification = vi.fn().mockRejectedValue(new Error("display failed"))
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    renderHook(() => useScheduleReminders([lesson({ id: "sw-lesson", subject: null })]))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
    })

    expect(showNotification).toHaveBeenCalledWith(
      "schedule:reminder.title",
      expect.objectContaining({ tag: "lesson-sw-lesson", body: "schedule:reminder.body" })
    )
    expect(notifications).toHaveLength(0)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    })
  })

  it("skips disabled, invalid, past, overridden, and already-reminded lessons", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const stored: ReminderPrefs = {
      minutesBefore: 15,
      overrides: { disabled: 0, remembered: 15, overridden: 0 },
    }
    idbGet.mockImplementation((key: string) =>
      Promise.resolve(key === "schedule:reminder-prefs" ? stored : ["remembered"])
    )

    renderHook(() =>
      useScheduleReminders([
        lesson({ id: "disabled", start_time: "12:00" }),
        lesson({ id: "invalid", start_time: "not-a-time" }),
        lesson({ id: "past", start_time: "10:10" }),
        lesson({ id: "remembered", start_time: "12:00" }),
        lesson({ id: "overridden", start_time: "12:00" }),
      ])
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
    })

    expect(notifications).toHaveLength(0)
  })

  it("stops scheduling when reminders are disabled", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const { result } = renderHook(() => useScheduleReminders([lesson({ start_time: "12:00" })]))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    await act(async () => {
      await result.current.setPrefs({ minutesBefore: 0 })
    })

    expect(result.current.isEnabled).toBe(false)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
    })
    expect(notifications).toHaveLength(0)
  })

  it("returns false when the browser has no Notification API", async () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "Notification")
    Reflect.deleteProperty(window, "Notification")
    Reflect.deleteProperty(globalThis, "Notification")

    try {
      const { result } = renderHook(() => useScheduleReminders([]))
      await flush()

      await expect(result.current.requestPermission()).resolves.toBe(false)
      expect(result.current.permission).toBe("default")
    } finally {
      if (descriptor) Object.defineProperty(window, "Notification", descriptor)
    }
  })
})
