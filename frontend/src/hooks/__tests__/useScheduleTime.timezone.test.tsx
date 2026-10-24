import { cleanup, renderHook } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import type { PropsWithChildren } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { CampusTimezoneProvider } from "@/contexts/CampusTimezoneContext"
import { useScheduleTime } from "@/hooks/useScheduleTime"
import type { Lesson } from "@/components/schedule/scheduleUtils"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

const lesson: Lesson = {
  id: "monday-lesson",
  subject: "Math",
  start_time: "09:00",
  end_time: "10:30",
  room: "101",
  teacher: "Teacher",
  lesson_type: "lecture",
  weekday: "monday",
  parity: "both",
}

function istanbulTimezone({ children }: PropsWithChildren) {
  return <CampusTimezoneProvider timeZone="Europe/Istanbul">{children}</CampusTimezoneProvider>
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("useScheduleTime campus timezone boundary", () => {
  it("does not derive a live lesson state from the host zone when campus timezone is unavailable", () => {
    const epoch = new Date("2026-04-26T06:30:00.000Z")
    const hostHours = vi.spyOn(Date.prototype, "getHours").mockReturnValue(9)
    const hostMinutes = vi.spyOn(Date.prototype, "getMinutes").mockReturnValue(30)

    const { result } = renderHook(() => useScheduleTime([lesson], true, epoch))

    expect(result.current.nowTick).toBe(epoch)
    expect(result.current.nowTick.getTime()).toBe(epoch.getTime())
    expect(result.current.currentLesson).toBeNull()
    expect(result.current.nextLesson).toBeNull()
    expect(result.current.timeLeftText).toBe("")
    expect(result.current.timeLeftShort).toBe("")
    expect(result.current.currentProgress).toBe(0)
    expect(hostHours).not.toHaveBeenCalled()
    expect(hostMinutes).not.toHaveBeenCalled()
  })

  it("uses the same epoch in the configured campus zone without reading host clock fields", () => {
    const epoch = new Date("2026-04-26T06:30:00.000Z")
    const hostHours = vi.spyOn(Date.prototype, "getHours").mockReturnValue(23)
    const hostMinutes = vi.spyOn(Date.prototype, "getMinutes").mockReturnValue(59)

    const { result } = renderHook(() => useScheduleTime([lesson], true, epoch), {
      wrapper: istanbulTimezone,
    })

    expect(result.current.nowTick).toBe(epoch)
    expect(result.current.currentLesson?.id).toBe("monday-lesson")
    expect(result.current.currentProgress).toBe(33)
    expect(hostHours).not.toHaveBeenCalled()
    expect(hostMinutes).not.toHaveBeenCalled()
  })
})

describe("useScheduleTime SSR/client parity", () => {
  it("renders the same no-zone clock state on server and client despite different host clocks", () => {
    const epoch = new Date("2026-04-26T06:30:00.000Z")
    const snapshotOf = (value: ReturnType<typeof useScheduleTime>) => ({
      epoch: value.nowTick.getTime(),
      current: value.currentLesson?.id ?? null,
      next: value.nextLesson?.id ?? null,
      timeLeftText: value.timeLeftText,
      timeLeftShort: value.timeLeftShort,
      progress: value.currentProgress,
    })
    const hostHours = vi.spyOn(Date.prototype, "getHours").mockReturnValue(9)
    const hostMinutes = vi.spyOn(Date.prototype, "getMinutes").mockReturnValue(30)

    function ServerSnapshot() {
      const value = useScheduleTime([lesson], true, epoch)
      return <output data-state={JSON.stringify(snapshotOf(value))} />
    }

    const serverMarkup = renderToString(<ServerSnapshot />)
    const serverValue = new DOMParser()
      .parseFromString(serverMarkup, "text/html")
      .querySelector("output")
      ?.getAttribute("data-state")
    const serverSnapshot = JSON.parse(serverValue ?? "null") as ReturnType<typeof snapshotOf>
    hostHours.mockReturnValue(11)
    hostMinutes.mockReturnValue(30)

    const { result } = renderHook(() => useScheduleTime([lesson], true, epoch))
    const clientSnapshot = {
      epoch: result.current.nowTick.getTime(),
      current: result.current.currentLesson?.id ?? null,
      next: result.current.nextLesson?.id ?? null,
      timeLeftText: result.current.timeLeftText,
      timeLeftShort: result.current.timeLeftShort,
      progress: result.current.currentProgress,
    }

    expect(clientSnapshot).toEqual(serverSnapshot)
    expect(serverSnapshot).toEqual({
      epoch: epoch.getTime(),
      current: null,
      next: null,
      timeLeftText: "",
      timeLeftShort: "",
      progress: 0,
    })
  })
})
