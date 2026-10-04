import { act, cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createInstance } from "i18next"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import { buildTable, type Lesson } from "@/components/schedule/scheduleUtils"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleKeyboardNav } from "@/hooks/useScheduleKeyboardNav"
import enCommon from "@/i18n/locales/en/common.json"
import enSchedule from "@/i18n/locales/en/schedule.json"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"
import type { User } from "@/types/User"

const weekdays = ["monday", "tuesday"]
const lessons: Lesson[] = weekdays.map((weekday, index) => ({
  id: `lesson-${index}`,
  subject: index === 0 ? "Algebra" : "Biology",
  weekday,
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  room: "101",
  lesson_type: "lecture",
  group_id: "group-1",
}))
const teacher: User = {
  id: "teacher-1",
  email: "teacher@example.test",
  is_active: true,
  role: "teacher",
}
type Actions = { settings: string[]; opened: string[]; deleted: string[]; shortcuts: string[] }
function ScheduleWithNavigation({
  actions,
  enabled,
  children,
}: {
  actions: Actions
  enabled: boolean
  children?: ReactNode
}) {
  const { activeDialog, selectedLesson, addDay, openDialog } = useSchedulePage()
  const rows = buildTable(lessons, weekdays)
  const { activeCell } = useScheduleKeyboardNav({
    rowCount: rows.length,
    colCount: weekdays.length,
    todayColIdx: 1,
    enabled: enabled && activeDialog === null,
    onOpen: (row, col) => {
      const lesson = rows[row]?.[col]
      if (lesson) {
        actions.opened.push(lesson.id)
        openDialog("details", lesson)
      }
    },
    onEdit: () => actions.shortcuts.push("edit"),
    onDelete: () => actions.shortcuts.push("delete"),
    onToggleShortcuts: () => actions.shortcuts.push("shortcuts"),
  })
  return (
    <>
      <ScheduleHeader
        user={null}
        groups={[]}
        selectedGroup={null}
        setSelectedGroup={() => {}}
        currentLesson={null}
        nextLesson={null}
        timeLeftText=""
        timeLeftShort=""
        currentProgress={0}
        todayLessons={[]}
        nowTick={new Date("2026-10-04T10:00:00Z")}
        onOpenSettings={() => actions.settings.push("opened")}
      />
      <ScheduleDesktopTable
        schedule={lessons}
        rawSchedule={lessons}
        weekdayBackend={weekdays}
        weekdayLabels={["Monday", "Tuesday"]}
        hasToday={true}
        todayIdx={1}
        conflictedIds={new Set()}
        user={teacher}
        refresh={() => {}}
        currentLesson={null}
        currentProgress={0}
        isOnline={true}
        onDeleteLesson={(id) => actions.deleted.push(id)}
        getLessonTypeColor={() => "var(--lt-lecture-badge)"}
        getLessonTypeLabel={() => "Lecture"}
        notesMap={new Map()}
      />
      {children}
      <output aria-label="Active dialog">{activeDialog ?? "closed"}</output>
      <output aria-label="Selected lesson">{selectedLesson?.subject ?? "none"}</output>
      <output aria-label="Add day">{addDay ?? "none"}</output>
      <output aria-label="Grid selection">
        {activeCell ? `${activeCell.row},${activeCell.col}` : "none"}
      </output>
    </>
  )
}
async function renderSchedule({
  enabled = true,
  children,
}: { enabled?: boolean; children?: ReactNode } = {}) {
  const actions: Actions = { settings: [], opened: [], deleted: [], shortcuts: [] },
    i18n = createInstance()
  await i18n.init({
    lng: "en",
    resources: { en: { schedule: enSchedule, common: enCommon } },
    interpolation: { escapeValue: false },
  })
  render(
    <I18nextProvider i18n={i18n}>
      <SchedulePageProvider>
        <ScheduleWithNavigation actions={actions} enabled={enabled}>
          {children}
        </ScheduleWithNavigation>
      </SchedulePageProvider>
    </I18nextProvider>
  )
  return { actions, user: userEvent.setup() }
}
async function tabTo(user: ReturnType<typeof userEvent.setup>, target: HTMLElement) {
  for (let step = 0; step < 10 && document.activeElement !== target; step++) await user.tab()
  expect(target).toHaveFocus()
}
async function pressEnter(user: ReturnType<typeof userEvent.setup>) {
  const events: KeyboardEvent[] = []
  const observe = (event: KeyboardEvent) => {
    if (event.key === "Enter") events.push(event)
  }
  document.addEventListener("keydown", observe)
  try {
    await user.keyboard("{Enter}")
  } finally {
    document.removeEventListener("keydown", observe)
  }
  expect(events).toHaveLength(1)
  return events[0]!
}
let previousPreferences: Pick<
  ReturnType<typeof useScheduleUIStore.getState>,
  "hiddenWeekdays" | "compactMode"
>
beforeEach(() => {
  const { hiddenWeekdays, compactMode } = useScheduleUIStore.getState()
  previousPreferences = { hiddenWeekdays, compactMode }
  useScheduleUIStore.setState({ hiddenWeekdays: [], compactMode: false })
})
afterEach(() => {
  try {
    cleanup()
  } finally {
    useScheduleUIStore.setState(previousPreferences)
  }
})
describe("schedule Enter ownership", () => {
  it.each([true, false])("activates real Settings with grid enabled=%s", async (enabled) => {
    const { user, actions } = await renderSchedule({ enabled })
    await user.tab()
    expect(screen.getByRole("button", { name: "Settings" })).toHaveFocus()
    expect((await pressEnter(user)).defaultPrevented).toBe(false)
    expect(actions.settings).toEqual(["opened"])
    expect(actions.opened).toEqual([])
    expect(screen.getByLabelText("Active dialog")).toHaveTextContent("closed")
    expect(screen.getByLabelText("Grid selection")).toHaveTextContent("none")
  })
  it("keeps selected lesson closed when Settings receives Enter", async () => {
    const { user, actions } = await renderSchedule()
    await user.keyboard("{ArrowRight}")
    expect(screen.getAllByRole("gridcell")[1]).toHaveFocus()
    await tabTo(user, screen.getByRole("button", { name: "Settings" }))
    expect((await pressEnter(user)).defaultPrevented).toBe(false)
    expect(actions.settings).toEqual(["opened"])
    expect(actions.opened).toEqual([])
    expect(screen.getByLabelText("Grid selection")).toHaveTextContent("0,1")
  })
  it("opens Add lesson for focused column", async () => {
    const { user, actions } = await renderSchedule()
    await tabTo(user, screen.getByRole("button", { name: "Add lesson for Tuesday" }))
    expect((await pressEnter(user)).defaultPrevented).toBe(false)
    expect(screen.getByLabelText("Active dialog")).toHaveTextContent("add")
    expect(screen.getByLabelText("Add day")).toHaveTextContent("tuesday")
    expect(screen.getByLabelText("Selected lesson")).toHaveTextContent("none")
    expect(actions.opened).toEqual([])
  })
  it("activates nested real Delete button", async () => {
    const { user, actions } = await renderSchedule()
    await tabTo(
      user,
      within(screen.getAllByRole("gridcell")[1]!).getByRole("button", { name: "Delete lesson" })
    )
    expect((await pressEnter(user)).defaultPrevented).toBe(false)
    expect(actions.deleted).toEqual(["lesson-1"])
    expect(actions.opened).toEqual([])
    expect(screen.getByLabelText("Active dialog")).toHaveTextContent("closed")
  })
  it("still opens selected real grid cell", async () => {
    const { user, actions } = await renderSchedule()
    await user.keyboard("{ArrowRight}")
    expect(screen.getAllByRole("gridcell")[1]).toHaveFocus()
    expect((await pressEnter(user)).defaultPrevented).toBe(true)
    expect(actions.opened).toEqual(["lesson-1"])
    expect(screen.getByLabelText("Active dialog")).toHaveTextContent("details")
    expect(screen.getByLabelText("Selected lesson")).toHaveTextContent("Biology")
  })
  it("leaves native anchor activation to link", async () => {
    const activated: string[] = []
    const { user, actions } = await renderSchedule({
      children: (
        <a
          href="#schedule-help"
          onClick={(event) => {
            event.preventDefault()
            activated.push("help")
          }}
        >
          <span>Schedule help</span>
        </a>
      ),
    })
    await tabTo(user, screen.getByRole("link", { name: "Schedule help" }))
    expect((await pressEnter(user)).defaultPrevented).toBe(false)
    expect(activated).toEqual(["help"])
    expect(actions.opened).toEqual([])
  })
  it.each(["button icon", "link label"])("leaves nested %s Enter unclaimed", async (child) => {
    const { actions } = await renderSchedule({
      children: (
        <a href="#schedule-help">
          <span>Schedule help</span>
        </a>
      ),
    })
    const target =
      child === "button icon"
        ? screen.getByRole("button", { name: "Settings" }).querySelector("svg")!
        : screen.getByText("Schedule help")
    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    act(() => {
      target.dispatchEvent(event)
    })
    expect(event.defaultPrevented).toBe(false)
    expect(actions.opened).toEqual([])
    expect(screen.getByLabelText("Active dialog")).toHaveTextContent("closed")
  })
  it("retains non-Enter shortcuts from focused button", async () => {
    const { user, actions } = await renderSchedule()
    await user.tab()
    expect(screen.getByRole("button", { name: "Settings" })).toHaveFocus()
    await user.keyboard("e{Delete}?")
    expect(actions.shortcuts).toEqual(["edit", "delete", "shortcuts"])
    expect(actions.settings).toEqual([])
    await user.keyboard("t")
    expect(screen.getAllByRole("gridcell")[1]).toHaveFocus()
    expect(screen.getByLabelText("Grid selection")).toHaveTextContent("0,1")
    await user.keyboard("{Escape}")
    expect(screen.getByLabelText("Grid selection")).toHaveTextContent("none")
  })
})
