import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { act, renderHook } from "@testing-library/react"

import { useClassReminders, type RemindItem } from "./useClassReminders"

/**
 * useClassReminders — schedules client-side Notification timers for a
 * list of upcoming events. Each timer fires ``minutesBefore`` ahead of
 * ``when``; the hook respects ``Notification.permission`` and skips
 * past events silently.
 *
 * We pin Date.now via vi.useFakeTimers so the schedule windows are
 * deterministic, and stub Notification + navigator.serviceWorker so
 * fired timers don't try to open real browser notifications.
 */

const NOW = new Date("2026-05-15T12:00:00Z")

let notificationCtor: Mock<(...args: unknown[]) => void>
let permission: NotificationPermission

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)

  permission = "granted"
  notificationCtor = vi.fn<(...args: unknown[]) => void>()

  // Build a Notification stub that tests can control via `permission`.
  const NotificationStub = function (this: Notification, ...args: unknown[]) {
    notificationCtor(...args)
  } as unknown as typeof Notification
  Object.defineProperty(NotificationStub, "permission", {
    get: () => permission,
    configurable: true,
  })
  Object.defineProperty(NotificationStub, "requestPermission", {
    value: vi.fn().mockResolvedValue("granted"),
    configurable: true,
  })

  vi.stubGlobal("Notification", NotificationStub)
  // Service worker registration: use the inline fallback path (`new
  // Notification(...)`) by returning null from getRegistration.
  vi.stubGlobal("navigator", {
    ...navigator,
    serviceWorker: { getRegistration: vi.fn().mockResolvedValue(null) },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const tPlus = (mins: number) => new Date(NOW.getTime() + mins * 60_000).toISOString()

describe("useClassReminders — scheduling", () => {
  it("does nothing when items is undefined", () => {
    renderHook(() => useClassReminders(undefined))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("does nothing when items is an empty list", () => {
    renderHook(() => useClassReminders([]))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("schedules a timer at (when - minutesBefore)", async () => {
    // Lecture in 30 minutes, remind 10 minutes before — timer fires in 20.
    const items: RemindItem[] = [{ id: 1, title: "Algebra", when: tPlus(30), minutesBefore: 10 }]
    renderHook(() => useClassReminders(items))
    expect(vi.getTimerCount()).toBe(1)

    // Advance to T+19 — timer should NOT have fired yet.
    await vi.advanceTimersByTimeAsync(19 * 60_000)
    expect(notificationCtor).not.toHaveBeenCalled()

    // Advance past T+20 → fires; the callback awaits service-worker
    // resolution, so we use the async timer flush.
    await vi.advanceTimersByTimeAsync(2 * 60_000)
    expect(notificationCtor).toHaveBeenCalledOnce()
    expect(notificationCtor).toHaveBeenCalledWith(
      "Algebra",
      expect.objectContaining({
        body: expect.any(String),
      })
    )
  })

  it("falls back to defaultMinutesBefore when minutesBefore is omitted", () => {
    const items: RemindItem[] = [{ id: 1, title: "X", when: tPlus(15) }]
    renderHook(() => useClassReminders(items, { defaultMinutesBefore: 5 }))
    // Timer fires 5 min before the lesson — at T+10.
    expect(vi.getTimerCount()).toBe(1)
  })

  it("skips past events (timer would fire in the past)", () => {
    const items: RemindItem[] = [
      { id: 1, title: "Already happened", when: tPlus(-30), minutesBefore: 10 },
    ]
    renderHook(() => useClassReminders(items))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("skips events with non-finite parsed timestamps", () => {
    const items: RemindItem[] = [{ id: 1, title: "Bad date", when: "not-a-date" }]
    renderHook(() => useClassReminders(items))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("clears existing timers and re-schedules when items change", () => {
    const initial: RemindItem[] = [{ id: 1, title: "A", when: tPlus(60), minutesBefore: 10 }]
    const { rerender } = renderHook(
      ({ items }: { items: RemindItem[] }) => useClassReminders(items),
      { initialProps: { items: initial } }
    )
    expect(vi.getTimerCount()).toBe(1)

    const next: RemindItem[] = [
      { id: 2, title: "B", when: tPlus(120), minutesBefore: 10 },
      { id: 3, title: "C", when: tPlus(180), minutesBefore: 10 },
    ]
    rerender({ items: next })
    // Old timer cleared, two new timers scheduled.
    expect(vi.getTimerCount()).toBe(2)
  })

  it("clears all timers on unmount", () => {
    const items: RemindItem[] = [
      { id: 1, title: "X", when: tPlus(60), minutesBefore: 10 },
      { id: 2, title: "Y", when: tPlus(120), minutesBefore: 10 },
    ]
    const { unmount } = renderHook(() => useClassReminders(items))
    expect(vi.getTimerCount()).toBe(2)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe("useClassReminders — permission gating", () => {
  it("does not show a notification when permission is not 'granted'", async () => {
    permission = "denied"
    const items: RemindItem[] = [{ id: 1, title: "X", when: tPlus(15), minutesBefore: 5 }]
    renderHook(() => useClassReminders(items))
    // Drain timer.
    await vi.runAllTimersAsync()
    expect(notificationCtor).not.toHaveBeenCalled()
  })

  it("uses the service-worker notification API when a registration is available", async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined)
    const getRegistration = (
      navigator.serviceWorker as unknown as { getRegistration: ReturnType<typeof vi.fn> }
    ).getRegistration
    getRegistration.mockResolvedValue({ showNotification })

    const items: RemindItem[] = [{ id: 7, title: "Physics", when: tPlus(15), minutesBefore: 5 }]
    renderHook(() => useClassReminders(items))

    await vi.runAllTimersAsync()

    expect(showNotification).toHaveBeenCalledWith(
      "Physics",
      expect.objectContaining({
        tag: "reminder:7",
        data: { url: "/", id: 7, type: "reminder" },
      })
    )
    expect(notificationCtor).not.toHaveBeenCalled()
  })

  it("opens the reminder URL when the fallback notification is clicked", async () => {
    const notification = { onclick: undefined as (() => void) | undefined }
    const NotificationWithClick = function (this: Notification) {
      return notification as unknown as Notification
    } as unknown as typeof Notification
    Object.defineProperty(NotificationWithClick, "permission", {
      get: () => "granted" as NotificationPermission,
      configurable: true,
    })
    Object.defineProperty(NotificationWithClick, "requestPermission", {
      value: vi.fn().mockResolvedValue("granted"),
      configurable: true,
    })
    vi.stubGlobal("Notification", NotificationWithClick)
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)

    const items: RemindItem[] = [
      { id: 8, title: "Chemistry", when: tPlus(15), minutesBefore: 5, url: "/events/8" },
    ]
    renderHook(() => useClassReminders(items))
    await vi.runAllTimersAsync()
    notification.onclick?.()

    expect(openSpy).toHaveBeenCalledWith(`${location.origin}/events/8`, "_blank")
    openSpy.mockRestore()
  })

  it("silently ignores malformed reminder URLs", async () => {
    const notification = { onclick: undefined as (() => void) | undefined }
    const NotificationWithClick = function (this: Notification) {
      return notification as unknown as Notification
    } as unknown as typeof Notification
    Object.defineProperty(NotificationWithClick, "permission", {
      get: () => "granted" as NotificationPermission,
      configurable: true,
    })
    Object.defineProperty(NotificationWithClick, "requestPermission", {
      value: vi.fn().mockResolvedValue("granted"),
      configurable: true,
    })
    vi.stubGlobal("Notification", NotificationWithClick)
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)

    renderHook(() =>
      useClassReminders([
        { id: 10, title: "Biology", when: tPlus(15), minutesBefore: 5, url: "http://[invalid" },
      ])
    )
    await vi.runAllTimersAsync()
    notification.onclick?.()

    expect(openSpy).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it("ignores a service-worker registration failure", async () => {
    const getRegistration = (
      navigator.serviceWorker as unknown as { getRegistration: ReturnType<typeof vi.fn> }
    ).getRegistration
    getRegistration.mockRejectedValueOnce(new Error("worker unavailable"))

    renderHook(() =>
      useClassReminders([{ id: 9, title: "History", when: tPlus(15), minutesBefore: 5 }])
    )
    await vi.runAllTimersAsync()
  })
})

describe("useClassReminders — requestPermission", () => {
  it("returns 'unsupported' when Notification API is missing", async () => {
    // The hook checks `"Notification" in window` — set to undefined alone
    // keeps the key present in window, so we delete the property entirely.
    const original = (globalThis as { Notification?: typeof Notification }).Notification
    delete (globalThis as { Notification?: typeof Notification }).Notification
    try {
      const { result } = renderHook(() => useClassReminders([]))
      await expect(result.current.requestPermission()).resolves.toBe("unsupported")
    } finally {
      ;(globalThis as { Notification?: typeof Notification }).Notification = original
    }
  })

  it("short-circuits to 'granted' when already granted", async () => {
    permission = "granted"
    const { result } = renderHook(() => useClassReminders([]))
    await expect(result.current.requestPermission()).resolves.toBe("granted")
  })

  it("short-circuits to 'denied' when already denied", async () => {
    permission = "denied"
    const { result } = renderHook(() => useClassReminders([]))
    await expect(result.current.requestPermission()).resolves.toBe("denied")
  })

  it("requests permission when the browser has not decided yet", async () => {
    permission = "default"
    const requestPermission = Notification.requestPermission
    const { result } = renderHook(() => useClassReminders([]))

    await expect(result.current.requestPermission()).resolves.toBe("granted")
    expect(requestPermission).toHaveBeenCalledOnce()
  })
})

describe("useClassReminders — clear()", () => {
  it("immediately clears all pending timers", () => {
    const items: RemindItem[] = [{ id: 1, title: "X", when: tPlus(60), minutesBefore: 10 }]
    const { result } = renderHook(() => useClassReminders(items))
    expect(vi.getTimerCount()).toBe(1)
    act(() => result.current.clear())
    expect(vi.getTimerCount()).toBe(0)
  })
})
