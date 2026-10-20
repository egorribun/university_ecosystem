import { act, cleanup, fireEvent, screen, within } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { useSyncExternalStore, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Lesson } from "@/components/schedule/scheduleUtils"
import { CampusTimezoneProvider } from "@/contexts/CampusTimezoneContext"
import Schedule from "@/pages/Schedule"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const fixture = vi.hoisted(() => {
  const lessons: Lesson[] = []
  const groupState: { selectedGroup: string | null } = {
    selectedGroup: "group-1",
  }
  const listeners = new Set<() => void>()

  return {
    lessons,
    weekdayConfigs: [
      { id: "mon", backend: ["monday"], long: "Monday", short: "Mon" },
      { id: "tue", backend: ["tuesday"], long: "Tuesday", short: "Tue" },
    ],
    weekdayBackend: ["monday", "tuesday"],
    nowTick: new Date("2026-10-18T21:30:00Z"),
    lessonTypeLabels: new Map([["lecture", "Lecture"]]),
    subscribe: (listener: () => void) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    getSnapshot: () => groupState.selectedGroup,
    setSelectedGroup: (selectedGroup: string | null) => {
      if (groupState.selectedGroup === selectedGroup) return
      groupState.selectedGroup = selectedGroup
      listeners.forEach((listener) => listener())
    },
  }
})

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: null }),
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

vi.mock("@/hooks/useScheduleData", () => ({
  useScheduleData: () => ({
    user: { role: "student" },
    groups: [{ id: "group-1", name: "Export group" }],
    selectedGroup: useSyncExternalStore(
      fixture.subscribe,
      fixture.getSnapshot,
      fixture.getSnapshot
    ),
    setSelectedGroup: fixture.setSelectedGroup,
    currentParity: "odd",
    setCurrentParity: vi.fn(),
    schedule: fixture.lessons,
    rawSchedule: fixture.lessons,
    isLoading: false,
    error: null,
    refresh: vi.fn(),
    applyScheduleUpdate: vi.fn(),
    weekdayConfigs: fixture.weekdayConfigs,
    weekdayBackend: fixture.weekdayBackend,
    weekdayLabels: ["Monday", "Tuesday"],
    weekdayShort: ["Mon", "Tue"],
    getDayLabel: (day: string) => day,
    lessonTypeConfigs: [
      {
        id: "lecture",
        backend: ["lecture"],
        label: "Lecture",
        color: "var(--badge-lec)",
      },
    ],
    lessonTypeOptions: [{ value: "lecture", label: "Lecture" }],
    lessonTypeLabels: fixture.lessonTypeLabels,
    defaultLessonType: "lecture",
    getLessonTypeColor: () => "var(--badge-lec)",
    toBackendLessonType: (value: string) => value,
    todayIdx: 0,
    hasToday: true,
    nowTick: fixture.nowTick,
    todayLessons: [],
    currentLesson: null,
    nextLesson: null,
    conflictedIds: new Set<string>(),
    lessonDaysForMonth: () => new Set<number>(),
    timeLeftText: "",
    timeLeftShort: "",
    currentProgress: 0,
  }),
}))

vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => query.includes("prefers-reduced-motion"),
}))
vi.mock("@/hooks/useScheduleURLSync", () => ({ useScheduleURLSync: vi.fn() }))
vi.mock("@/hooks/useLessonNotes", () => ({
  useLessonNotesMap: () => new Map<string, boolean>(),
}))
vi.mock("@/hooks/useScheduleKeyboardNav", () => ({ useScheduleKeyboardNav: vi.fn() }))
vi.mock("@/hooks/useScrollToElement", () => ({ useScrollToElement: vi.fn() }))

vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/components/motion/FadeSection", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/ui/SkeletonMorph", () => ({
  SkeletonMorph: ({
    loaded,
    skeleton,
    children,
  }: {
    loaded: boolean
    skeleton: ReactNode
    children: ReactNode
  }) => (loaded ? <>{children}</> : <>{skeleton}</>),
}))
vi.mock("@/components/schedule/ScheduleSkeleton", () => ({
  ScheduleSkeleton: () => null,
}))
vi.mock("@/components/schedule/ScheduleHeader", () => ({
  ScheduleHeader: ({ onOpenSettings }: { onOpenSettings: () => void }) => (
    <button type="button" onClick={onOpenSettings}>
      Open settings
    </button>
  ),
}))
vi.mock("@/components/schedule/ScheduleDesktopTable", () => ({
  ScheduleDesktopTable: () => null,
}))
vi.mock("@/components/schedule/ScheduleMobileView", () => ({
  ScheduleMobileView: () => null,
}))
vi.mock("@/components/schedule/ScheduleDialogs", () => ({ ScheduleDialogs: () => null }))
vi.mock("@/components/schedule/ScheduleShortcutsOverlay", () => ({
  ScheduleShortcutsOverlay: () => null,
}))
vi.mock("@/components/schedule/ScheduleMiniCalendar", () => ({
  ScheduleMiniCalendar: () => null,
}))
vi.mock("@/components/ui/ConfirmDialog", () => ({ ConfirmDialog: () => null }))
vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: ReactNode }) => <div role="alert">{children}</div>,
  Snackbar: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div>{children}</div> : null,
}))
vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

async function renderSchedule() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return renderWithRouter({
    ui: () => (
      <CampusTimezoneProvider timeZone="Europe/Istanbul">
        <Schedule />
      </CampusTimezoneProvider>
    ),
    path: "/schedule",
    initialPath: "/schedule",
    queryClient,
    authProvider: false,
  })
}

function openExportMenu() {
  fireEvent.click(screen.getByRole("button", { name: "Open settings" }))
  const dialog = screen.getByRole("dialog")
  fireEvent.click(within(dialog).getByRole("button", { name: /^Export$/ }))
  return within(dialog).getByRole("menuitem", { name: /Google Calendar/i })
}

describe("Schedule Google Calendar export — AUD-066", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    fixture.lessons = []
    fixture.setSelectedGroup("group-1")
    useScheduleUIStore.setState({
      weekOffset: 0,
      viewMode: "week",
      hiddenWeekdays: [],
      showPastLessons: true,
      compactMode: false,
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    useScheduleUIStore.setState({
      weekOffset: 0,
      viewMode: "week",
      hiddenWeekdays: [],
      showPastLessons: true,
      compactMode: false,
    })
  })

  it("prepares the first eligible lesson of the filtered selected campus week", async () => {
    const first: Lesson = {
      id: "tuesday-first",
      group_id: "group-1",
      weekday: "tuesday",
      parity: "both",
      subject: "Linear Algebra",
      teacher: "Ada Lovelace",
      room: "B-202",
      lesson_type: "lecture",
      start_time: "09:15",
      end_time: "10:45",
    }
    fixture.lessons = [
      {
        ...first,
        id: "tuesday-later",
        subject: "Later lesson",
        start_time: "12:00",
        end_time: "13:30",
      },
      { ...first, id: "hidden-monday", weekday: "monday", subject: "Hidden lesson" },
      first,
    ]
    const open = vi.spyOn(window, "open").mockReturnValue(null)

    await renderSchedule()
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }))
    const dialog = screen.getByRole("dialog")

    fireEvent.click(within(dialog).getByRole("button", { name: "Next week" }))
    fireEvent.click(within(dialog).getByRole("button", { name: "Monday" }))
    expect(useScheduleUIStore.getState().weekOffset).toBe(1)
    expect(useScheduleUIStore.getState().hiddenWeekdays).toEqual([0])

    fireEvent.click(within(dialog).getByRole("button", { name: /^Export$/ }))
    fireEvent.click(within(dialog).getByRole("menuitem", { name: /Google Calendar/i }))

    expect(open).toHaveBeenCalledTimes(1)
    const call = open.mock.calls.at(0)
    if (!call) throw new Error("Expected a Google Calendar event preparation")
    const [destination, target, features] = call
    if (typeof destination !== "string") throw new Error("Expected a calendar URL string")

    const url = new URL(destination)
    expect(url.origin).toBe("https://calendar.google.com")
    expect(url.pathname).toBe("/calendar/r/eventedit")
    expect(url.searchParams.get("action")).toBe("TEMPLATE")
    expect(url.searchParams.get("text")).toBe("Linear Algebra (Ada Lovelace)")
    expect(url.searchParams.get("dates")).toBe("20261027T091500/20261027T104500")
    expect(url.searchParams.get("location")).toBe("B-202")
    expect(url.searchParams.get("details")).toBe("Type: Lecture")
    expect(url.searchParams.get("ctz")).toBe("Europe/Istanbul")
    expect(target).toBe("_blank")
    expect(features).toBe("noopener")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("does not open Google Calendar when the selected group has no lessons", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null)

    await renderSchedule()
    const calendarItem = openExportMenu()
    fireEvent.click(calendarItem)

    expect(open).not.toHaveBeenCalled()
    expect(calendarItem).toBeDisabled()
  })

  it("rechecks group ownership on the same mounted export menu without replacing schedule inputs", async () => {
    const lessons: Lesson[] = [
      {
        id: "group-1-tuesday",
        group_id: "group-1",
        weekday: "tuesday",
        parity: "both",
        subject: "Linear Algebra",
        teacher: "Ada Lovelace",
        room: "B-202",
        lesson_type: "lecture",
        start_time: "09:15",
        end_time: "10:45",
      },
    ]
    fixture.lessons = lessons
    const weekdayConfigs = fixture.weekdayConfigs
    const weekdayBackend = fixture.weekdayBackend
    const nowTick = fixture.nowTick
    const lessonTypeLabels = fixture.lessonTypeLabels
    const hiddenWeekdays = useScheduleUIStore.getState().hiddenWeekdays
    const open = vi.spyOn(window, "open").mockReturnValue(null)

    await renderSchedule()
    const calendarItem = openExportMenu()
    expect(calendarItem).toBeEnabled()

    // Deliberately contradictory fixture metadata exercises the export guard.
    // This does not model normal group-keyed query cache behavior.
    act(() => {
      fixture.setSelectedGroup("group-2")
    })

    expect(screen.getByRole("menuitem", { name: /Google Calendar/i })).toBe(calendarItem)
    expect(calendarItem).toBeDisabled()
    fireEvent.click(calendarItem)
    expect(open).not.toHaveBeenCalled()
    expect(screen.getByRole("menu")).toBeInTheDocument()

    expect(fixture.lessons).toBe(lessons)
    expect(fixture.weekdayConfigs).toBe(weekdayConfigs)
    expect(fixture.weekdayBackend).toBe(weekdayBackend)
    expect(fixture.nowTick).toBe(nowTick)
    expect(fixture.lessonTypeLabels).toBe(lessonTypeLabels)
    expect(useScheduleUIStore.getState().weekOffset).toBe(0)
    expect(useScheduleUIStore.getState().hiddenWeekdays).toBe(hiddenWeekdays)

    act(() => {
      fixture.setSelectedGroup("group-1")
    })

    expect(screen.getByRole("menuitem", { name: /Google Calendar/i })).toBe(calendarItem)
    expect(calendarItem).toBeEnabled()
    fireEvent.click(calendarItem)

    expect(open).toHaveBeenCalledTimes(1)
    expect(open).toHaveBeenCalledWith(
      expect.stringContaining("https://calendar.google.com/calendar/r/eventedit?"),
      "_blank",
      "noopener"
    )
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })
})
