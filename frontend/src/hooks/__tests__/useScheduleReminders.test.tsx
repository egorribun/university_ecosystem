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
})
