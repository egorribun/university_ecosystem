import type { ComponentProps, ReactNode } from "react"
import {
  act,
  cleanup,
  createEvent,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterContextProvider,
} from "@tanstack/react-router"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
import { type Lesson } from "@/components/schedule/scheduleUtils"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleConfig } from "@/hooks/useScheduleConfig"
import enSchedule from "@/i18n/locales/en/schedule.json"
import enSystem from "@/i18n/locales/en/system.json"
import ruSchedule from "@/i18n/locales/ru/schedule.json"
import ruSystem from "@/i18n/locales/ru/system.json"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

type Props = ComponentProps<typeof ScheduleMobileView>
type DataProps = Omit<
  Props,
  | "weekdayBackend"
  | "weekdayLabels"
  | "weekdayShort"
  | "getDayLabel"
  | "getLessonTypeColor"
  | "getLessonTypeLabel"
>

const earlyLesson: Lesson = {
  id: "algebra",
  weekday: "monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "A-101",
  lesson_type: "lecture",
}
const lateLesson: Lesson = {
  ...earlyLesson,
  id: "geometry",
  start_time: "12:00",
  end_time: "13:30",
  subject: "Geometry",
  teacher: "Dr. Smirnov",
}
const tuesdayLesson: Lesson = {
  ...earlyLesson,
  id: "physics",
  weekday: "tuesday",
  subject: "Physics",
}
const lessons = [lateLesson, tuesdayLesson, earlyLesson]

function ConfiguredMobileView(props: DataProps) {
  const config = useScheduleConfig()
  return (
    <ScheduleMobileView
      {...config}
      {...props}
      getLessonTypeLabel={(value) => config.lessonTypeLabels.get(value ?? "") ?? value ?? ""}
    />
  )
}

function AddDialogProbe() {
  const { activeDialog, addDay } = useSchedulePage()
  return activeDialog === "add" ? <output aria-label="Lesson draft day">{addDay}</output> : null
}

async function renderMobile(overrides: Partial<DataProps> = {}, language = "en") {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    resources: {
      en: { schedule: enSchedule, system: enSystem },
      ru: { schedule: ruSchedule, system: ruSystem },
    },
  })
  const router = createRouter({
    routeTree: createRootRoute(),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const props: DataProps = {
    schedule: lessons,
    rawSchedule: lessons,
    hasToday: true,
    todayIdx: 0,
    refresh: vi.fn(),
    user: null,
    conflictedIds: new Set(),
    isOnline: true,
    onDeleteLesson: vi.fn(),
    currentLesson: null,
    currentProgress: 0,
    notesMap: new Map(),
    ...overrides,
  }
  const view = render(<ConfiguredMobileView {...props} />, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <I18nextProvider i18n={i18n}>
        <RouterContextProvider router={router}>
          <SchedulePageProvider>
            {children}
            <AddDialogProbe />
          </SchedulePageProvider>
        </RouterContextProvider>
      </I18nextProvider>
    ),
  })
  return {
    ...view,
    i18n,
    props,
    rerenderMobile: (updates: Partial<DataProps>) =>
      view.rerender(<ConfiguredMobileView {...props} {...updates} />),
  }
}

function expectActivePanel(tab: HTMLElement, heading: string) {
  expect(screen.getAllByRole("tab", { selected: true })).toEqual([tab])
  for (const other of screen.getAllByRole("tab")) {
    expect(other).toHaveAttribute("tabindex", other === tab ? "0" : "-1")
  }
  const panel = screen.getByRole("tabpanel")
  expect(tab.id).not.toBe("")
  expect(tab).toHaveAttribute("aria-controls", panel.id)
  expect(panel).toHaveAttribute("aria-labelledby", tab.id)
  expect(panel).toHaveAccessibleName(tab.textContent ?? "")
  expect(within(panel).getByRole("heading", { level: 2, name: heading })).toBeVisible()
  return panel
}

beforeEach(() => {
  useScheduleUIStore.getState().resetPreferences()
})

afterEach(() => {
  cleanup()
  useScheduleUIStore.getState().resetPreferences()
})

describe("ScheduleMobileView behavior", () => {
  it.each([
    { language: "en", title: "Schedule", monday: "Monday", saturday: "Saturday" },
    { language: "ru", title: "Расписание", monday: "Понедельник", saturday: "Суббота" },
  ])("wraps keyboard selection between linked day panels in $language", async (labels) => {
    const user = userEvent.setup()
    await renderMobile({}, labels.language)
    const tablist = screen.getByRole("tablist", { name: labels.title })
    const tabs = within(tablist).getAllByRole("tab")
    expect(tabs).toHaveLength(6)
    expectActivePanel(tabs[0]!, labels.monday)

    await user.tab()
    expect(tabs[0]).toHaveFocus()
    const left = createEvent.keyDown(tabs[0]!, { key: "ArrowLeft", cancelable: true })
    fireEvent(tabs[0]!, left)
    expect(left.defaultPrevented).toBe(true)
    expect(tabs[5]).toHaveFocus()
    expectActivePanel(tabs[5]!, labels.saturday)
    expect(screen.queryByRole("heading", { name: earlyLesson.subject! })).not.toBeInTheDocument()

    const right = createEvent.keyDown(tabs[5]!, { key: "ArrowRight", cancelable: true })
    fireEvent(tabs[5]!, right)
    expect(right.defaultPrevented).toBe(true)
    expect(tabs[0]).toHaveFocus()
    expectActivePanel(tabs[0]!, labels.monday)
    expect(screen.getByRole("heading", { name: earlyLesson.subject! })).toBeVisible()

    const unrelated = createEvent.keyDown(tabs[0]!, { key: "a", cancelable: true })
    fireEvent(tabs[0]!, unrelated)
    expect(unrelated.defaultPrevented).toBe(false)
    expect(tabs[0]).toHaveFocus()
    expectActivePanel(tabs[0]!, labels.monday)
  })

  it("groups refreshed lessons by day and renders each day in start-time order", async () => {
    const user = userEvent.setup()
    const { rerenderMobile } = await renderMobile()
    expect(screen.getByRole("tab", { name: /^Mon/ })).toHaveTextContent("Mon2")
    expect(within(screen.getByRole("tabpanel")).getAllByRole("heading", { level: 3 })).toHaveLength(
      2
    )
    expect(
      screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)
    ).toEqual(["Linear Algebra", "Geometry"])
    expect(screen.queryByRole("heading", { name: "Physics" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /^Tue/ }))
    expectActivePanel(screen.getByRole("tab", { name: /^Tue/ }), "Tuesday")
    expect(
      screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)
    ).toEqual(["Physics"])

    const replacement = { ...lateLesson, id: "chemistry", weekday: "tuesday", subject: "Chemistry" }
    const refreshed = [replacement, earlyLesson]
    rerenderMobile({ schedule: refreshed, rawSchedule: refreshed })
    expect(screen.getByRole("tab", { name: /^Mon/ })).toHaveTextContent("Mon1")
    expect(screen.getByRole("tab", { name: /^Tue/ })).toHaveTextContent("Tue1")
    expect(screen.getByRole("heading", { name: "Chemistry" })).toBeVisible()
    expect(screen.queryByRole("heading", { name: "Physics" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /^Mon/ }))
    expect(screen.getByRole("heading", { name: "Linear Algebra" })).toBeVisible()
    expect(screen.queryByRole("heading", { name: "Geometry" })).not.toBeInTheDocument()
    expect(lessons.map((lesson) => lesson.id)).toEqual(["geometry", "physics", "algebra"])
  })

  it("keeps the selected day while translated tab and panel labels update", async () => {
    const user = userEvent.setup()
    const { i18n } = await renderMobile()
    await user.click(screen.getByRole("tab", { name: /^Tue/ }))

    await act(() => i18n.changeLanguage("ru"))

    expect(screen.getByRole("tablist", { name: "Расписание" })).toBeVisible()
    expectActivePanel(screen.getByRole("tab", { name: /^Вт/ }), "Вторник")
    expect(screen.getByRole("heading", { name: "Physics" })).toBeVisible()
    expect(screen.queryByRole("tab", { name: /^Tue/ })).not.toBeInTheDocument()
  })

  it.each([
    { day: "Saturday", hasToday: true, todayIdx: 5, selected: /^Sat/ },
    { day: "Monday", hasToday: false, todayIdx: -1, selected: /^Mon/ },
  ])("selects $day for the weekend boundary supplied by the schedule data", async (data) => {
    const user = userEvent.setup()
    await renderMobile({ hasToday: data.hasToday, todayIdx: data.todayIdx })
    const initialTab = screen.getByRole("tab", { name: data.selected })
    expectActivePanel(initialTab, data.day)

    await user.tab()
    expect(initialTab).toHaveFocus()
    await user.keyboard(data.hasToday ? "{ArrowRight}" : "{ArrowLeft}")
    const destination = screen.getByRole("tab", { name: data.hasToday ? /^Mon/ : /^Sat/ })
    expect(destination).toHaveFocus()
    expectActivePanel(destination, data.hasToday ? "Monday" : "Saturday")
  })

  it("shows a retryable offline state when no schedule has been cached", async () => {
    const user = userEvent.setup()
    const refresh = vi.fn()
    await renderMobile({ schedule: [], rawSchedule: [], isOnline: false, refresh })

    expect(
      screen.getByRole("heading", { name: "This section is unavailable offline" })
    ).toBeVisible()
    expect(screen.queryByText("No lessons for this day")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(refresh).toHaveBeenCalledExactlyOnceWith()
  })

  it.each([
    { state: "online with no lessons", isOnline: true, rawSchedule: [] },
    { state: "offline with cached lessons filtered out", isOnline: false, rawSchedule: lessons },
  ])("shows a normal empty day when $state", async ({ isOnline, rawSchedule }) => {
    await renderMobile({ schedule: [], rawSchedule, isOnline })

    expect(screen.getByRole("heading", { name: "No lessons for this day" })).toBeVisible()
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Mon" })).toBeVisible()
  })

  it("announces completion only while the completed current day is displayed", async () => {
    const user = userEvent.setup()
    await renderMobile({ todayComplete: true })
    expect(screen.getByRole("status")).toHaveTextContent("Great day! All lessons complete")

    await user.click(screen.getByRole("tab", { name: /^Tue/ }))

    expectActivePanel(screen.getByRole("tab", { name: /^Tue/ }), "Tuesday")
    expect(screen.queryByText("Great day! All lessons complete")).not.toBeInTheDocument()
  })

  it("uses the active day and lesson when a teacher adds or deletes", async () => {
    const user = userEvent.setup()
    const onDeleteLesson = vi.fn()
    await renderMobile({
      user: { id: "teacher", email: "teacher@example.test", is_active: true, role: "teacher" },
      onDeleteLesson,
    })
    await user.click(screen.getByRole("tab", { name: /^Tue/ }))
    await user.click(screen.getByRole("button", { name: "Add lesson for Tuesday" }))
    expect(screen.getByRole("status", { name: "Lesson draft day" })).toHaveTextContent("tuesday")

    await user.click(screen.getByRole("button", { name: "Delete lesson" }))
    expect(onDeleteLesson).toHaveBeenCalledExactlyOnceWith("physics")
  })

  it("applies the live compact preference without losing selection or current-lesson status", async () => {
    await renderMobile({
      currentLesson: earlyLesson,
      notesMap: new Map([[earlyLesson.id, true]]),
      conflictedIds: new Set([lateLesson.id]),
    })
    const currentCard = screen.getByLabelText("Linear Algebra, 09:00–10:30, A-101")
    expect(currentCard).toHaveAttribute("aria-current", "time")
    expect(screen.getByText("Dr. Ivanova")).toBeVisible()
    expect(screen.getByTitle("Has a note")).toBeInTheDocument()
    expect(
      screen.getByLabelText("Geometry, 12:00–13:30, A-101, Schedule conflict")
    ).not.toHaveAttribute("aria-current")

    act(() => useScheduleUIStore.getState().toggleCompactMode())

    expect(screen.queryByText("Dr. Ivanova")).not.toBeInTheDocument()
    expect(screen.queryByTitle("Has a note")).not.toBeInTheDocument()
    expectActivePanel(screen.getByRole("tab", { name: /^Mon/ }), "Monday")
    expect(currentCard).toHaveAttribute("aria-current", "time")
    expect(screen.getByText("Schedule conflict")).toBeVisible()

    act(() => useScheduleUIStore.getState().toggleCompactMode())
    expect(screen.getByText("Dr. Ivanova")).toBeVisible()
    expect(screen.getByTitle("Has a note")).toBeInTheDocument()
  })
})
