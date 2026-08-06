import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import Schedule from "@/pages/Schedule"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const {
  apiMocks,
  authState,
  scheduleState,
  uiState,
  pageState,
  mediaState,
  keyboardState,
  scrollToElement,
  baseLesson,
} = vi.hoisted(() => {
  const lesson = {
    id: "lesson-42",
    weekday: "Monday",
    parity: "odd",
    start_time: "08:00",
    end_time: "09:30",
    subject: "Linear Algebra",
    teacher: "Ada Lovelace",
    room: "101",
    lesson_type: "lecture",
    group_id: "group-1",
  }

  return {
    apiMocks: {
      delete: vi.fn(),
    },
    authState: {
      user: { role: "student" },
    },
    scheduleState: {
      isLoading: false,
      error: null as Error | null,
      schedule: [lesson],
      rawSchedule: [lesson],
      weekdayBackend: ["Monday"],
      weekdayLabels: ["Monday"],
      weekdayShort: ["Mon"],
      hasToday: false,
      todayIdx: 0,
      conflictedIds: new Set<string>(),
      user: { role: "student" },
      refresh: vi.fn(),
      getDayLabel: (value: string) => value,
      getLessonTypeColor: () => "#3366ff",
      applyScheduleUpdate: vi.fn(),
      currentLesson: null as any,
      nextLesson: null as any,
      nowTick: new Date("2024-03-25T08:00:00.000Z"),
      lessonDays: ["Monday"],
      lessonTypeLabels: new Map([["lecture", "Lecture"]]),
      todayLessons: [],
      currentProgress: 0,
      currentParity: "odd",
      setCurrentParity: vi.fn(),
    },
    uiState: {
      weekOffset: 0,
      showPastLessons: true,
      resetPreferences: vi.fn(),
    },
    pageState: {
      activeDialog: null,
      selectedLesson: null as any,
      snackbarMessage: null,
      snackbarSeverity: "success",
      showSnackbar: vi.fn(),
      hideSnackbar: vi.fn(),
      openDialog: vi.fn(),
    },
    mediaState: {
      mobile: false,
      reduced: false,
      online: true,
    },
    keyboardState: {
      options: null as any,
    },
    scrollToElement: vi.fn(),
    baseLesson: lesson,
  }
})

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

vi.mock("@/api/client", () => ({
  __esModule: true,
  default: {
    delete: apiMocks.delete,
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    interceptors: { response: { use: vi.fn() }, request: { use: vi.fn() } },
  },
}))

vi.mock("@/hooks/useScheduleData", () => ({
  useScheduleData: () => scheduleState,
}))

vi.mock("@/hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => mediaState.online,
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    if (query.includes("prefers-reduced-motion")) return mediaState.reduced
    return mediaState.mobile
  },
}))

vi.mock("@/hooks/useScheduleURLSync", () => ({
  useScheduleURLSync: vi.fn(),
}))

vi.mock("@/hooks/useLessonNotes", () => ({
  useLessonNotesMap: () => new Map<string, boolean>(),
}))

vi.mock("@/hooks/useScheduleKeyboardNav", () => ({
  useScheduleKeyboardNav: (options: unknown) => {
    keyboardState.options = options
    return {
      activeCell: null,
      setActiveCell: vi.fn(),
      gridRef: { current: null },
      clearSelection: vi.fn(),
    }
  },
}))

vi.mock("@/stores/scheduleUIStore", () => ({
  useWeekOffset: () => uiState.weekOffset,
  useScheduleDisplayPreferences: () => ({ showPastLessons: uiState.showPastLessons }),
  useScheduleUIActions: () => ({ resetPreferences: uiState.resetPreferences }),
}))

vi.mock("@/contexts/SchedulePageContext", () => ({
  SchedulePageProvider: ({ children }: { children: ReactNode }) => children,
  useSchedulePage: () => pageState,
}))

vi.mock("@/hooks/useScrollToElement", () => ({
  useScrollToElement: scrollToElement,
}))

vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => (
    <div data-testid="page-layout">{children}</div>
  ),
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/motion/FadeSection", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/ui/SEO", () => ({
  SEO: () => null,
}))

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
  ScheduleSkeleton: () => <div data-testid="schedule-skeleton" />,
}))

vi.mock("@/components/schedule/ScheduleHeader", () => ({
  ScheduleHeader: ({ onOpenSettings }: { onOpenSettings: () => void }) => (
    <button type="button" onClick={onOpenSettings}>
      Open settings
    </button>
  ),
}))

vi.mock("@/components/schedule/ScheduleDesktopTable", () => ({
  ScheduleDesktopTable: ({
    schedule,
    onDeleteLesson,
    getLessonTypeLabel,
  }: {
    schedule: Array<{ id: string }>
    onDeleteLesson: (id: string) => void
    getLessonTypeLabel: (value?: string | null) => string
  }) => (
    <div data-testid="desktop-view">
      <span data-testid="desktop-labels">
        {getLessonTypeLabel("lecture")}|{getLessonTypeLabel("missing")}|{getLessonTypeLabel(null)}
      </span>
      <button type="button" onClick={() => schedule[0] && onDeleteLesson(schedule[0].id)}>
        Delete lesson
      </button>
    </div>
  ),
}))

vi.mock("@/components/schedule/ScheduleMobileView", () => ({
  ScheduleMobileView: ({
    schedule,
    onDeleteLesson,
  }: {
    schedule: Array<{ id: string }>
    onDeleteLesson: (id: string) => void
  }) => (
    <div data-testid="mobile-view">
      <button type="button" onClick={() => schedule[0] && onDeleteLesson(schedule[0].id)}>
        Delete lesson
      </button>
    </div>
  ),
}))

vi.mock("@/components/schedule/ScheduleDialogs", () => ({
  ScheduleDialogs: () => <div data-testid="schedule-dialogs" />,
}))

vi.mock("@/components/schedule/ScheduleShortcutsOverlay", () => ({
  ScheduleShortcutsOverlay: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="shortcuts-overlay">
        <button type="button" onClick={onClose}>
          Close shortcuts
        </button>
      </div>
    ) : null,
}))

vi.mock("@/components/schedule/ScheduleMiniCalendar", () => ({
  ScheduleMiniCalendar: () => <aside data-testid="mini-calendar" />,
}))

vi.mock("@/components/schedule/ScheduleSettingsPanel", () => ({
  ScheduleSettingsPanel: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="settings-panel">
        <button type="button" onClick={onClose}>
          Close settings
        </button>
      </div>
    ) : null,
}))

vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    onCancel,
  }: {
    open: boolean
    onConfirm: () => void
    onCancel: () => void
  }) =>
    open ? (
      <div role="dialog" data-testid="confirm-delete">
        <button type="button" onClick={onConfirm}>
          Confirm delete
        </button>
        <button type="button" onClick={onCancel}>
          Cancel delete
        </button>
      </div>
    ) : null,
}))

vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: ReactNode }) => <div role="alert">{children}</div>,
  Snackbar: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div data-testid="snackbar">{children}</div> : null,
}))

vi.mock("@/components/error/FeatureErrorBoundary", () => ({
  FeatureErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("framer-motion", () => ({
  LazyMotion: ({ children }: { children: ReactNode }) => <>{children}</>,
  domAnimation: {},
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  },
}))

async function renderSchedule() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const result = await renderWithRouter({
    ui: Schedule,
    path: "/schedule",
    initialPath: "/schedule",
    queryClient,
    authProvider: false,
  })
  return result
}

describe("Schedule page behavior", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    vi.clearAllMocks()

    authState.user = { role: "student" }
    scheduleState.isLoading = false
    scheduleState.error = null
    scheduleState.schedule = [baseLesson]
    scheduleState.rawSchedule = [baseLesson]
    scheduleState.weekdayBackend = ["Monday"]
    scheduleState.weekdayLabels = ["Monday"]
    scheduleState.weekdayShort = ["Mon"]
    scheduleState.hasToday = false
    scheduleState.todayIdx = 0
    scheduleState.user = { role: "student" }
    scheduleState.currentLesson = null
    scheduleState.nextLesson = null
    scheduleState.nowTick = new Date("2024-03-25T08:00:00.000Z")
    scheduleState.currentParity = "odd"
    uiState.weekOffset = 0
    uiState.showPastLessons = true
    mediaState.mobile = false
    mediaState.reduced = false
    mediaState.online = true
    pageState.activeDialog = null
    pageState.selectedLesson = null
    pageState.snackbarMessage = null
    pageState.snackbarSeverity = "success"
    keyboardState.options = null
    scrollToElement.mockClear()
    apiMocks.delete.mockResolvedValue({})
  })

  afterEach(() => {
    cleanup()
  })

  it("renders desktop controls and toggles settings and shortcuts", async () => {
    await renderSchedule()

    expect(screen.getByTestId("desktop-view")).toBeInTheDocument()
    expect(screen.getByTestId("mini-calendar")).toBeInTheDocument()
    expect(screen.getByTestId("desktop-labels")).toHaveTextContent("Lecture|missing|")

    fireEvent.click(screen.getByRole("button", { name: "Open settings" }))
    expect(screen.getByTestId("settings-panel")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }))
    expect(screen.queryByTestId("settings-panel")).not.toBeInTheDocument()

    expect(keyboardState.options).not.toBeNull()
    keyboardState.options.onEdit()
    keyboardState.options.onDelete()
    expect(screen.queryByTestId("confirm-delete")).not.toBeInTheDocument()
    keyboardState.options.onToggleShortcuts()
    await waitFor(() => expect(screen.getByTestId("shortcuts-overlay")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Close shortcuts" }))
    expect(screen.queryByTestId("shortcuts-overlay")).not.toBeInTheDocument()
  })

  it("renders mobile view and resets a filter that hides every lesson", async () => {
    mediaState.mobile = true
    uiState.showPastLessons = false
    scheduleState.hasToday = true
    scheduleState.nowTick = new Date("2024-03-25T10:00:00.000Z")
    scheduleState.schedule = [{ ...baseLesson, end_time: "09:30" }]
    scheduleState.rawSchedule = [...scheduleState.schedule]

    await renderSchedule()

    expect(screen.getByTestId("mobile-view")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /reset filters/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /reset filters/i }))
    expect(uiState.resetPreferences).toHaveBeenCalledOnce()
  })

  it("shows a load error and retries the schedule request", async () => {
    scheduleState.error = new Error("network")
    await renderSchedule()

    expect(screen.getByText("Failed to load schedule")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /retry/i }))
    expect(scheduleState.refresh).toHaveBeenCalledOnce()
  })

  it("renders the skeleton while schedule data is loading", async () => {
    scheduleState.isLoading = true
    await renderSchedule()

    expect(screen.getByTestId("schedule-skeleton")).toBeInTheDocument()
    expect(screen.queryByTestId("desktop-view")).not.toBeInTheDocument()
  })

  it("keeps the schedule when today is unavailable or lesson times are malformed", async () => {
    uiState.showPastLessons = false
    scheduleState.hasToday = false
    await renderSchedule()
    expect(screen.getByTestId("desktop-view")).toBeInTheDocument()

    cleanup()
    scheduleState.hasToday = true
    scheduleState.schedule = [
      { ...baseLesson, id: "no-end", end_time: "" },
      { ...baseLesson, id: "invalid-end", end_time: "not-a-time" },
      { ...baseLesson, id: "other-day", weekday: "Tuesday", end_time: "09:00" },
    ]
    scheduleState.rawSchedule = [...scheduleState.schedule]
    await renderSchedule()
    expect(screen.getByTestId("desktop-view")).toBeInTheDocument()
  })

  it("uses reduced-motion transitions and scrolls to the current lesson", async () => {
    mediaState.reduced = true
    scheduleState.currentLesson = scheduleState.schedule[0]

    await renderSchedule()

    expect(scrollToElement).toHaveBeenCalledWith("lesson-card-lesson-42", {
      behavior: "smooth",
      block: "center",
    })
  })

  it("optimistically deletes a lesson online and refreshes after success", async () => {
    await renderSchedule()

    fireEvent.click(screen.getByRole("button", { name: "Delete lesson" }))
    expect(screen.getByTestId("confirm-delete")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await waitFor(() => expect(apiMocks.delete).toHaveBeenCalledWith("/schedule/lesson-42"))
    expect(scheduleState.applyScheduleUpdate).toHaveBeenCalledOnce()
    expect(scheduleState.refresh).toHaveBeenCalledOnce()
    expect(pageState.showSnackbar).toHaveBeenCalledWith(expect.any(String))
  })

  it("rolls back an optimistic delete while offline", async () => {
    mediaState.online = false
    await renderSchedule()

    fireEvent.click(screen.getByRole("button", { name: "Delete lesson" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await waitFor(() =>
      expect(pageState.showSnackbar).toHaveBeenCalledWith(expect.any(String), "error")
    )
    expect(apiMocks.delete).not.toHaveBeenCalled()
    expect(scheduleState.applyScheduleUpdate).toHaveBeenCalledTimes(2)
  })

  it("routes keyboard edit and delete callbacks for privileged users", async () => {
    authState.user = { role: "admin" }
    scheduleState.user = { role: "admin" }
    pageState.selectedLesson = scheduleState.schedule[0]
    await renderSchedule()

    keyboardState.options.onEdit()
    expect(pageState.openDialog).toHaveBeenCalledWith("edit", scheduleState.schedule[0])

    keyboardState.options.onDelete()
    await waitFor(() => expect(screen.getByTestId("confirm-delete")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Cancel delete" }))
    expect(screen.queryByTestId("confirm-delete")).not.toBeInTheDocument()
  })

  it("allows teachers to use keyboard edit and delete callbacks", async () => {
    authState.user = { role: "teacher" }
    scheduleState.user = { role: "teacher" }
    pageState.selectedLesson = scheduleState.schedule[0]
    await renderSchedule()

    keyboardState.options.onEdit()
    expect(pageState.openDialog).toHaveBeenCalledWith("edit", scheduleState.schedule[0])
    keyboardState.options.onDelete()
    await waitFor(() => expect(screen.getByTestId("confirm-delete")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Cancel delete" }))
  })

  it("announces positive and negative week offsets", async () => {
    uiState.weekOffset = 2
    const { rerender } = await renderSchedule()
    expect(screen.getByRole("status")).toHaveTextContent("+2")

    uiState.weekOffset = -2
    rerender(<Schedule />)
    expect(screen.getByRole("status")).toHaveTextContent("-2")
  })
})
