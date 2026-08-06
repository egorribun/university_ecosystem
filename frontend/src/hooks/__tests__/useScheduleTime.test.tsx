import { renderHook, act } from "@testing-library/react"
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest"
import { useScheduleTime } from "../useScheduleTime"
import type { Lesson } from "@/components/schedule/scheduleUtils"

// Mock useTranslation
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: unknown) => {
      const opts = options as
        { count?: number; duration?: string; defaultValue?: string } | undefined
      if (key === "schedule:time.hours") return `${opts?.count}h`
      if (key === "schedule:time.minutes") return `${opts?.count}m`
      if (key === "schedule:timeLeft.current") return `left ${opts?.duration}`
      if (key === "schedule:timeLeft.next") return `in ${opts?.duration}`
      return opts?.defaultValue ?? key
    },
  }),
}))

const mockLessons: Lesson[] = [
  {
    id: "1",
    subject: "Math",
    start_time: "09:00",
    end_time: "10:30",
    room: "101",
    teacher: "Teacher 1",
    lesson_type: "lecture",
    weekday: "mon",
    parity: "both",
  },
  {
    id: "2",
    subject: "Physics",
    start_time: "11:00",
    end_time: "12:30",
    room: "102",
    teacher: "Teacher 2",
    lesson_type: "practice",
    weekday: "mon",
    parity: "both",
  },
]

describe("useScheduleTime", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("identifies current lesson and progress at 09:30", () => {
    const date = new Date(2026, 3, 26, 9, 30)
    vi.setSystemTime(date)

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    expect(result.current.currentLesson?.subject).toBe("Math")
    expect(result.current.nextLesson?.subject).toBe("Physics")
    expect(result.current.currentProgress).toBe(33) // (30 / 90) * 100 = 33.33 -> 33
    expect(result.current.timeLeftShort).toContain("1h")
  })

  it("identifies next lesson when between lessons at 10:45", () => {
    const date = new Date(2026, 3, 26, 10, 45)
    vi.setSystemTime(date)

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    expect(result.current.currentLesson).toBeNull()
    expect(result.current.nextLesson?.subject).toBe("Physics")
    expect(result.current.currentProgress).toBe(0)
    expect(result.current.timeLeftText).toBe("in 15m")
  })

  it("returns no next lesson while the final lesson is in progress", () => {
    vi.setSystemTime(new Date(2026, 3, 26, 11, 30))

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    expect(result.current.currentLesson?.subject).toBe("Physics")
    expect(result.current.nextLesson).toBeNull()
    expect(result.current.timeLeftShort).toBe("1h")
  })

  it("updates on ticker interval", () => {
    const date = new Date(2026, 3, 26, 9, 29, 59)
    vi.setSystemTime(date)

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))
    expect(result.current.nowTick.getMinutes()).toBe(29)

    act(() => {
      vi.advanceTimersByTime(31000) // Advance past the 30s interval
    })

    expect(result.current.nowTick.getMinutes()).toBe(30)
  })

  it("keeps the same tick when an interval fires within the same minute", () => {
    const date = new Date(2026, 3, 26, 9, 29, 5)
    vi.setSystemTime(date)

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    act(() => {
      vi.advanceTimersByTime(30_000)
    })

    expect(result.current.nowTick.getTime()).toBe(date.getTime())
  })

  it("pauses ticker when page is hidden", () => {
    const date = new Date(2026, 3, 26, 9, 29, 59)
    vi.setSystemTime(date)

    // Mock document.visibilityState
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    })

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    act(() => {
      vi.advanceTimersByTime(60000)
    })

    // Should NOT update when hidden
    expect(result.current.nowTick.getMinutes()).toBe(29)

    // Switch to visible and trigger event
    act(() => {
      Object.defineProperty(document, "visibilityState", {
        value: "visible",
        configurable: true,
      })
      document.dispatchEvent(new Event("visibilitychange"))
    })

    // Should update immediately on visibility change to visible
    expect(result.current.nowTick.getMinutes()).toBe(30) // 9:29:59 + 60s = 9:30:59
  })

  it("returns empty values when hasToday is false", () => {
    const { result } = renderHook(() => useScheduleTime(mockLessons, false))
    expect(result.current.currentLesson).toBeNull()
    expect(result.current.nextLesson).toBeNull()
    expect(result.current.currentProgress).toBe(0)
  })

  it("formats a duration with both hours and minutes", () => {
    vi.setSystemTime(new Date(2026, 3, 26, 9, 0))
    const longLesson: Lesson = {
      ...mockLessons[0]!,
      id: "long",
      end_time: "10:45",
    }

    const { result } = renderHook(() => useScheduleTime([longLesson], true))

    expect(result.current.currentLesson?.id).toBe("long")
    expect(result.current.timeLeftShort).toBe("1h 45m")
    expect(result.current.currentProgress).toBe(0)
  })

  it("formats a current lesson with minutes only", () => {
    vi.setSystemTime(new Date(2026, 3, 26, 9, 5))
    const shortLesson: Lesson = {
      ...mockLessons[0]!,
      id: "short",
      end_time: "09:20",
    }

    const { result } = renderHook(() => useScheduleTime([shortLesson], true))

    expect(result.current.currentLesson?.id).toBe("short")
    expect(result.current.timeLeftShort).toBe("15m")
    expect(result.current.timeLeftText).toBe("left 15m")
  })

  it("uses safe defaults for malformed lesson times", () => {
    vi.setSystemTime(new Date(2026, 3, 26, 9, 30))
    const malformed: Lesson = {
      ...mockLessons[0]!,
      id: "malformed",
      start_time: null,
      end_time: "not-a-time",
    }

    const { result } = renderHook(() => useScheduleTime([malformed], true))

    expect(result.current.currentLesson).toBeNull()
    expect(result.current.nextLesson).toBeNull()
    expect(result.current.timeLeftText).toBe("")
    expect(result.current.timeLeftShort).toBe("")
    expect(result.current.currentProgress).toBe(0)
  })

  it("returns empty countdowns when today has lessons but none are current or next", () => {
    vi.setSystemTime(new Date(2026, 3, 26, 13, 0))

    const { result } = renderHook(() => useScheduleTime(mockLessons, true))

    expect(result.current.currentLesson).toBeNull()
    expect(result.current.nextLesson).toBeNull()
    expect(result.current.timeLeftText).toBe("")
    expect(result.current.timeLeftShort).toBe("")
    expect(result.current.currentProgress).toBe(0)
  })
})
