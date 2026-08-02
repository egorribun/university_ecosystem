/**
 * Session 11 coverage: src/components/schedule/ScheduleDesktopTable.tsx
 *
 * The W120 SW3 ARIA-grid component. All schedule data arrives as PROPS (the
 * `useScheduleData` import is type-only — never mock it). The only hooks the
 * component CALLS are useTranslation (real i18n), useSchedulePage (real
 * <SchedulePageProvider>), and the zustand scheduleUIStore (reset per-test).
 *
 * Gotchas baked in (verified from source):
 *  - LessonCard is rendered WITHOUT `onOpen` → it has NO role → query cards via
 *    getByLabelText, never getByRole("button"). Delete buttons ARE real <button>.
 *  - aria-labels use an en-dash `–` (U+2013) in the time range, NOT a hyphen.
 *  - compactMode MUST be false (reset in beforeEach) for the note indicator +
 *    details row to render.
 *  - authProvider:false — the component reads `user` from props, not AuthContext.
 */
import { fireEvent, screen, within } from "@testing-library/react"
import type { ComponentProps } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"] as const
const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const

const LESSON_MON_1: Lesson = {
  id: "l1",
  weekday: "monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Linear Algebra",
  teacher: "Ada Lovelace",
  room: "101",
  lesson_type: "lecture",
  group_id: "g1",
}

const LESSON_MON_2: Lesson = {
  id: "l2",
  weekday: "monday",
  parity: "both",
  start_time: "10:40",
  end_time: "12:10",
  subject: "Programming",
  teacher: "Alan Turing",
  room: "202",
  lesson_type: "practice",
  group_id: "g1",
}

const LESSON_WED_1: Lesson = {
  id: "l3",
  weekday: "wednesday",
  parity: "both",
  start_time: "13:00",
  end_time: "14:30",
  subject: "Databases",
  teacher: "Edgar Codd",
  room: "303",
  lesson_type: "lab",
  group_id: "g1",
}

const ALL_LESSONS: Lesson[] = [LESSON_MON_1, LESSON_MON_2, LESSON_WED_1]

type Props = ComponentProps<typeof ScheduleDesktopTable>

let resizeObserverCallback: ResizeObserverCallback | undefined
const resizeObserverDisconnect = vi.fn()

function ContextProbe() {
  const { addDay, activeDialog } = useSchedulePage()
  return <div data-testid="schedule-context-probe">{`${addDay ?? ""}:${activeDialog ?? ""}`}</div>
}

function baseProps(overrides: Partial<Props> = {}): Props {
  return {
    schedule: ALL_LESSONS,
    rawSchedule: ALL_LESSONS,
    weekdayBackend: [...WEEKDAYS],
    weekdayLabels: [...WEEKDAY_LABELS],
    hasToday: true,
    todayIdx: 0,
    conflictedIds: new Set<string>(),
    user: null,
    refresh: vi.fn(),
    currentLesson: null,
    currentProgress: 0,
    isOnline: true,
    onDeleteLesson: vi.fn(),
    getLessonTypeColor: () => "var(--lt-lecture-badge)",
    getLessonTypeLabel: (val) => val ?? "Lecture",
    notesMap: new Map<string, boolean>(),
    ...overrides,
  }
}

function renderTable(props: Props) {
  return renderWithRouter({
    ui: () => (
      <SchedulePageProvider>
        <ScheduleDesktopTable {...props} />
        <ContextProbe />
      </SchedulePageProvider>
    ),
    authProvider: false,
  })
}

beforeEach(() => {
  resizeObserverCallback = undefined
  resizeObserverDisconnect.mockReset()
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn()
      disconnect() {
        resizeObserverDisconnect()
      }

      constructor(callback: ResizeObserverCallback) {
        resizeObserverCallback = callback
      }
    }
  )
  // scheduleUIStore persists hiddenWeekdays + compactMode to localStorage; reset
  // to defaults so all 6 days are visible and cards render non-compact (required
  // for the note indicator + details row).
  useScheduleUIStore.setState({ hiddenWeekdays: [], compactMode: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ScheduleDesktopTable", () => {
  it("renders an ARIA grid with rows, columnheaders, rowheaders, and gridcells", async () => {
    await renderTable(baseProps())

    const grid = screen.getByRole("grid", { name: "Schedule" })
    expect(grid).toBeInTheDocument()
    // colCount = visibleDays(6) + 1 = 7; rowCount = tableRows(2) + 1 = 3.
    expect(grid).toHaveAttribute("aria-colcount", "7")
    expect(grid).toHaveAttribute("aria-rowcount", "3")

    // 1 header row + 2 data rows (Monday has 2 lessons → buildTable yields 2 rows).
    expect(within(grid).getAllByRole("row")).toHaveLength(3)

    const columnHeaders = within(grid).getAllByRole("columnheader")
    expect(columnHeaders).toHaveLength(7)
    expect(within(grid).getByRole("columnheader", { name: /№/ })).toBeInTheDocument()
    expect(within(grid).getByRole("columnheader", { name: /Mon/ })).toBeInTheDocument()
    expect(within(grid).getByRole("columnheader", { name: /Wed/ })).toBeInTheDocument()

    const rowHeaders = within(grid).getAllByRole("rowheader")
    expect(rowHeaders).toHaveLength(2)
    expect(rowHeaders[0]).toHaveTextContent("1")
    expect(rowHeaders[1]).toHaveTextContent("2")

    // 2 rows × 6 day columns = 12 gridcells (lesson + empty mix).
    expect(within(grid).getAllByRole("gridcell")).toHaveLength(12)

    // canEdit=false (user:null) → no delete affordances anywhere.
    expect(within(grid).queryByRole("button", { name: "Delete lesson" })).toBeNull()
  })

  it("places lessons in their correct day columns", async () => {
    await renderTable(baseProps())

    // LessonCard has no role (onOpen not passed) → query by accessible label.
    // aria-label = [subject, "HH:MM–HH:MM", room].join(", ") with an en-dash.
    expect(screen.getByLabelText("Linear Algebra, 09:00–10:30, 101")).toBeInTheDocument()
    expect(screen.getByLabelText("Programming, 10:40–12:10, 202")).toBeInTheDocument()
    expect(screen.getByLabelText("Databases, 13:00–14:30, 303")).toBeInTheDocument()

    expect(screen.getByText("Linear Algebra")).toBeInTheDocument()
    expect(screen.getByText("Programming")).toBeInTheDocument()
    expect(screen.getByText("Databases")).toBeInTheDocument()
    expect(screen.getAllByText(/Linear Algebra|Programming|Databases/)).toHaveLength(3)
  })

  it("marks a conflicted lesson with the conflict label, title, and indicator", async () => {
    await renderTable(baseProps({ conflictedIds: new Set(["l1"]) }))

    const conflictCard = screen.getByLabelText(
      "Linear Algebra, 09:00–10:30, 101, Schedule conflict"
    )
    expect(conflictCard).toBeInTheDocument()
    expect(conflictCard).toHaveAttribute("title", "Schedule conflict")
    expect(conflictCard.className).toContain("sched-conflict")
    expect(within(conflictCard).getByText("Schedule conflict")).toBeInTheDocument()

    // Non-conflicted lesson keeps the plain label (no ", Schedule conflict" suffix).
    expect(screen.getByLabelText("Programming, 10:40–12:10, 202")).toBeInTheDocument()
  })

  it("fires onDeleteLesson with the lesson id when an admin clicks delete", async () => {
    const onDeleteLesson = vi.fn()
    await renderTable(baseProps({ user: { role: "admin" } as Props["user"], onDeleteLesson }))

    const targetCard = screen.getByLabelText("Linear Algebra, 09:00–10:30, 101")
    const deleteBtn = within(targetCard).getByRole("button", { name: "Delete lesson" })
    expect(deleteBtn).toHaveAttribute("id", "delete-lesson-l1")

    fireEvent.click(deleteBtn)

    expect(onDeleteLesson).toHaveBeenCalledTimes(1)
    expect(onDeleteLesson).toHaveBeenCalledWith("l1")
  })

  it("opens the add dialog for the selected weekday", async () => {
    await renderTable(baseProps({ user: { role: "admin" } as Props["user"] }))

    const addButtons = screen.getAllByRole("button", { name: "actions.addLesson" })
    expect(addButtons).toHaveLength(WEEKDAYS.length)
    fireEvent.click(addButtons[0]!)

    expect(screen.getByTestId("schedule-context-probe")).toHaveTextContent("monday:add")
  })

  it("renders the EmptyState when there are no lessons (online)", async () => {
    await renderTable(baseProps({ schedule: [], rawSchedule: [], isOnline: true }))

    expect(screen.getByText("No lessons scheduled")).toBeInTheDocument()
    expect(screen.getByText("Select a group to view schedule")).toBeInTheDocument()
    // EmptyState title renders as a heading (titleAs default "h2").
    expect(screen.getByRole("heading", { name: "No lessons scheduled" })).toBeInTheDocument()
    expect(screen.queryByLabelText(/Linear Algebra/)).toBeNull()

    const grid = screen.getByRole("grid", { name: "Schedule" })
    expect(within(grid).getAllByRole("columnheader")).toHaveLength(7)
    // No data rows → aria-rowcount = 0 + 1 = 1.
    expect(grid).toHaveAttribute("aria-rowcount", "1")
  })

  it("renders OfflineFallback (not EmptyState) when offline with no cached schedule", async () => {
    const refresh = vi.fn()
    await renderTable(baseProps({ schedule: [], rawSchedule: [], isOnline: false, refresh }))

    // Offline branch → OfflineFallback, NOT EmptyState. Distinguish by the absence
    // of the EmptyState string + the retry button wiring (namespace-agnostic).
    expect(screen.queryByText("No lessons scheduled")).toBeNull()

    const buttons = screen.getAllByRole("button")
    expect(buttons.length).toBeGreaterThanOrEqual(2)

    // First button is OfflineFallback's solid "Retry" → onClick calls onRetry (refresh).
    fireEvent.click(buttons[0]!)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it("renders a note indicator only on lessons present in notesMap", async () => {
    await renderTable(baseProps({ notesMap: new Map<string, boolean>([["l1", true]]) }))

    // compactMode false (beforeEach) → note indicator <span title="Has a note"> renders.
    expect(screen.getAllByTitle("Has a note")).toHaveLength(1)

    const l1Card = screen.getByLabelText("Linear Algebra, 09:00–10:30, 101")
    expect(within(l1Card).getByTitle("Has a note")).toBeInTheDocument()

    // l2/l3 not in notesMap → notesMap.get(...) ?? false → no indicator.
    const l2Card = screen.getByLabelText("Programming, 10:40–12:10, 202")
    expect(within(l2Card).queryByTitle("Has a note")).toBeNull()
  })

  it("hides weekday columns present in hiddenWeekdays (store-driven)", async () => {
    // Hide Tuesday (1) + Saturday (5) → 4 visible days.
    useScheduleUIStore.setState({ hiddenWeekdays: [1, 5], compactMode: false })
    await renderTable(baseProps())

    const grid = screen.getByRole("grid", { name: "Schedule" })
    expect(grid).toHaveAttribute("aria-colcount", "5") // 4 days + 1
    expect(within(grid).getAllByRole("columnheader")).toHaveLength(5)
    expect(within(grid).queryByRole("columnheader", { name: /Tue/ })).toBeNull()
    expect(within(grid).queryByRole("columnheader", { name: /Sat/ })).toBeNull()
    expect(within(grid).getByRole("columnheader", { name: /Mon/ })).toBeInTheDocument()
  })

  it("labels empty grid cells with the fallback 'Empty' aria-label", async () => {
    // One Monday lesson → row 0 Monday filled, the other 5 day-columns empty.
    await renderTable(baseProps({ schedule: [LESSON_MON_1], rawSchedule: [LESSON_MON_1] }))

    const grid = screen.getByRole("grid", { name: "Schedule" })
    // 1 row × 6 day columns = 6 gridcells; 1 lesson + 5 empty (aria-label "Empty").
    expect(within(grid).getAllByRole("gridcell", { name: "Empty" })).toHaveLength(5)
    // The filled Monday cell carries the stable keyboard-nav id (W120 SW3).
    expect(grid.querySelector("#sched-cell-0-0")).not.toBeNull()
  })

  it("updates the overflow marker and renders current-lesson cell state", async () => {
    await renderTable(baseProps({ currentLesson: LESSON_MON_1, currentProgress: 42, todayIdx: 1 }))

    const container = document.querySelector(".schedule-grid-container") as HTMLElement
    const scrollWrapper = document.querySelector(".sched-scroll-wrapper") as HTMLElement
    Object.defineProperties(scrollWrapper, {
      scrollWidth: { configurable: true, value: 1200 },
      clientWidth: { configurable: true, value: 800 },
    })
    resizeObserverCallback?.([], {} as ResizeObserver)
    expect(container).toHaveAttribute("data-overflows", "")

    Object.defineProperty(scrollWrapper, "scrollWidth", { configurable: true, value: 700 })
    resizeObserverCallback?.([], {} as ResizeObserver)
    expect(container).not.toHaveAttribute("data-overflows")

    const currentCell = document.getElementById("sched-cell-0-0")
    expect(currentCell).toBeInTheDocument()
    expect(document.getElementById("sched-cell-0-1")).toHaveClass("sched-today-col")
    expect(screen.getByLabelText("Linear Algebra, 09:00–10:30, 101")).toBeInTheDocument()
    expect(resizeObserverDisconnect).not.toHaveBeenCalled()
  })
})
