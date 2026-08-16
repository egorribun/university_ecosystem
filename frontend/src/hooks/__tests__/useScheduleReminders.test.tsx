import { renderHook, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const { idbGet, idbSet, logError } = vi.hoisted(() => ({
  idbGet: vi.fn(),
  idbSet: vi.fn(),
  logError: vi.fn(),
}))
vi.mock("idb-keyval", () => ({ get: idbGet, set: idbSet }))
vi.mock("@/app/logger", () => ({ logError }))
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
  logError.mockReset()
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

  it("reports enabled reminders when notification permission is not granted", async () => {
    renderHook(() => useScheduleReminders([lesson()]))
    await flush()

    expect(logError).toHaveBeenCalledWith(
      "[schedule:reminders] Reminders enabled but notification permission denied"
    )
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

  it("uses the schedule clock local calendar date for reminded storage", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T21:30:00.000Z"))
    const dateSpies = [
      vi.spyOn(Date.prototype, "getFullYear").mockReturnValue(2026),
      vi.spyOn(Date.prototype, "getMonth").mockReturnValue(5),
      vi.spyOn(Date.prototype, "getDate").mockReturnValue(16),
      vi.spyOn(Date.prototype, "getHours").mockReturnValue(0),
      vi.spyOn(Date.prototype, "getMinutes").mockReturnValue(30),
    ]

    try {
      const { unmount } = renderHook(() => useScheduleReminders([]))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(idbGet).toHaveBeenCalledWith("schedule:reminded-today:2026-06-16")
      expect(idbGet).not.toHaveBeenCalledWith("schedule:reminded-today:2026-06-15")
      unmount()
    } finally {
      for (const spy of dateSpies) spy.mockRestore()
    }
  })

  it("rehydrates reminded IDs and reschedules lessons after local midnight", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 15, 23, 58))
    MockNotification.permission = "granted"
    idbGet.mockImplementation((key: string) => {
      if (key === "schedule:reminder-prefs") return Promise.resolve(undefined)
      if (key === "schedule:reminded-today:2026-06-15") return Promise.resolve(["carry-over"])
      if (key === "schedule:reminded-today:2026-06-16") {
        return Promise.resolve(["already-new-day"])
      }
      return Promise.resolve(undefined)
    })

    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const showNotification = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    const { unmount } = renderHook(() =>
      useScheduleReminders([
        lesson({ id: "carry-over", start_time: "00:20" }),
        lesson({ id: "already-new-day", start_time: "00:20" }),
      ])
    )

    try {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(idbGet).toHaveBeenCalledWith("schedule:reminded-today:2026-06-15")

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2 * 60_000)
      })
      expect(idbGet).toHaveBeenCalledWith("schedule:reminded-today:2026-06-16")

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5 * 60_000 + 100)
      })

      expect(showNotification).toHaveBeenCalledOnce()
      expect(showNotification).toHaveBeenCalledWith(
        "schedule:reminder.title",
        expect.objectContaining({ tag: "lesson-carry-over" })
      )
      expect(idbSet).toHaveBeenCalledOnce()
      expect(idbSet).toHaveBeenCalledWith(
        "schedule:reminded-today:2026-06-16",
        expect.arrayContaining(["already-new-day", "carry-over"])
      )
    } finally {
      unmount()
      if (descriptor) {
        Object.defineProperty(navigator, "serviceWorker", descriptor)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
    }
  })

  it("schedules and persists duplicate lesson IDs only once", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const showNotification = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    try {
      renderHook(() =>
        useScheduleReminders([
          lesson({ id: "duplicate", start_time: "10:20" }),
          lesson({ id: "duplicate", start_time: "10:20" }),
        ])
      )
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5 * 60_000 + 100)
      })

      expect(idbSet).toHaveBeenCalledOnce()
      expect(idbSet).toHaveBeenCalledWith("schedule:reminded-today:2026-06-15", ["duplicate"])
      expect(showNotification).toHaveBeenCalledOnce()
    } finally {
      if (descriptor) {
        Object.defineProperty(navigator, "serviceWorker", descriptor)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
    }
  })

  it("waits for reminded IDs hydration before scheduling notifications", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"

    let resolveReminded!: (ids: string[]) => void
    const reminded = new Promise<string[]>((resolve) => {
      resolveReminded = resolve
    })
    idbGet.mockImplementation((key: string) => {
      if (key === "schedule:reminder-prefs") return Promise.resolve(undefined)
      if (key === "schedule:reminded-today:2026-06-15") return reminded
      return Promise.resolve(undefined)
    })

    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const showNotification = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    try {
      renderHook(() => useScheduleReminders([lesson({ id: "already-reminded" })]))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
      })

      expect(showNotification).not.toHaveBeenCalled()
      expect(notifications).toHaveLength(0)

      await act(async () => {
        resolveReminded(["already-reminded"])
        await Promise.resolve()
      })
      await act(async () => {
        await vi.runOnlyPendingTimersAsync()
      })

      expect(showNotification).not.toHaveBeenCalled()
      expect(notifications).toHaveLength(0)
    } finally {
      if (descriptor) {
        Object.defineProperty(navigator, "serviceWorker", descriptor)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
    }
  })

  it("waits for stored preferences before scheduling notifications", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"

    let resolvePrefs!: (prefs: ReminderPrefs) => void
    const storedPrefs = new Promise<ReminderPrefs>((resolve) => {
      resolvePrefs = resolve
    })
    idbGet.mockImplementation((key: string) =>
      key === "schedule:reminder-prefs" ? storedPrefs : Promise.resolve(undefined)
    )

    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const showNotification = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    try {
      renderHook(() =>
        useScheduleReminders([lesson({ id: "disabled-by-stored-prefs", start_time: "10:20" })])
      )
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5 * 60_000 + 100)
      })

      expect(showNotification).not.toHaveBeenCalled()
      expect(notifications).toHaveLength(0)

      await act(async () => {
        resolvePrefs({ minutesBefore: 0, overrides: {} })
        await Promise.resolve()
      })
      await act(async () => {
        await vi.runOnlyPendingTimersAsync()
      })

      expect(showNotification).not.toHaveBeenCalled()
      expect(notifications).toHaveLength(0)
    } finally {
      if (descriptor) {
        Object.defineProperty(navigator, "serviceWorker", descriptor)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
    }
  })

  it("continues scheduling after both storage hydration reads fail", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const prefsError = new Error("preferences unavailable")
    const remindedError = new Error("reminded IDs unavailable")
    idbGet.mockImplementation((key: string) =>
      Promise.reject(key === "schedule:reminder-prefs" ? prefsError : remindedError)
    )

    renderHook(() => useScheduleReminders([lesson({ id: "after-read-error" })]))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
    })

    expect(logError).toHaveBeenCalledWith("[schedule:reminders]", prefsError)
    expect(logError).toHaveBeenCalledWith("[schedule:reminders]", remindedError)
    expect(notifications).toEqual([
      expect.objectContaining({
        title: "schedule:reminder.title",
        options: expect.objectContaining({ tag: "lesson-after-read-error" }),
      }),
    ])
  })

  it("ignores pending IndexedDB hydration after unmount", async () => {
    MockNotification.permission = "granted"
    let resolvePrefs!: (prefs: ReminderPrefs | undefined) => void
    let resolveReminded!: (ids: string[] | undefined) => void
    const storedPrefs = new Promise<ReminderPrefs | undefined>((resolve) => {
      resolvePrefs = resolve
    })
    const reminded = new Promise<string[] | undefined>((resolve) => {
      resolveReminded = resolve
    })
    idbGet.mockImplementation((key: string) =>
      key === "schedule:reminder-prefs" ? storedPrefs : reminded
    )

    const { unmount } = renderHook(() => useScheduleReminders([lesson()]))
    unmount()
    await act(async () => {
      resolvePrefs({ minutesBefore: 30, overrides: {} })
      resolveReminded(["l1"])
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(notifications).toHaveLength(0)
  })

  it("falls back to the Notification constructor without a service worker", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    })

    try {
      renderHook(() => useScheduleReminders([lesson({ id: "no-sw" })]))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
      })

      expect(notifications).toEqual([
        expect.objectContaining({
          title: "schedule:reminder.title",
          options: expect.objectContaining({ tag: "lesson-no-sw" }),
        }),
      ])
    } finally {
      if (descriptor) Object.defineProperty(navigator, "serviceWorker", descriptor)
    }
  })

  it("shows a reminder through an available service worker", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-15T10:00:00"))
    MockNotification.permission = "granted"
    const descriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const showNotification = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ showNotification }) },
    })

    try {
      renderHook(() => useScheduleReminders([lesson({ id: "sw-success" })]))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(105 * 60_000 + 100)
      })

      expect(showNotification).toHaveBeenCalledWith(
        "schedule:reminder.title",
        expect.objectContaining({ tag: "lesson-sw-success" })
      )
      expect(notifications).toHaveLength(0)
    } finally {
      if (descriptor) {
        Object.defineProperty(navigator, "serviceWorker", descriptor)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
    }
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
