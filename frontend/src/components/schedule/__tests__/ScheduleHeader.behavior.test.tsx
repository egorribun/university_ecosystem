import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ScheduleHeader } from "@/components/schedule/ScheduleHeader"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import enSchedule from "@/i18n/locales/en/schedule.json"
import enCommon from "@/i18n/locales/en/common.json"
import ruSchedule from "@/i18n/locales/ru/schedule.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import { testUser } from "@/tests/mocks/handlers"
import type { ComponentProps } from "react"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

type HeaderProps = ComponentProps<typeof ScheduleHeader>

const baseProps: HeaderProps = {
  user: testUser,
  groups: [
    { id: "g1", name: "CS-2024" },
    { id: "g2", name: "CS-2025" },
  ],
  selectedGroup: "g1",
  setSelectedGroup: vi.fn(),
  currentLesson: null,
  nextLesson: null,
  timeLeftText: "",
  timeLeftShort: "",
  currentProgress: 0,
  todayLessons: [],
  nowTick: new Date("2026-06-15T10:45:00"),
}

const lesson: Lesson = {
  id: "lesson-1",
  weekday: "monday",
  parity: "both",
  start_time: "11:00:00",
  end_time: "12:30:00",
  subject: "Linear Algebra",
  teacher: "Dr. Ivanova",
  room: "ГУК-305",
  lesson_type: "lecture",
}

async function renderHeader(props: Partial<HeaderProps> = {}, language = "en") {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    resources: {
      en: { schedule: enSchedule, common: enCommon },
      ru: { schedule: ruSchedule, common: ruCommon },
    },
    interpolation: { escapeValue: false },
  })
  const view = render(<ScheduleHeader {...baseProps} {...props} />, {
    wrapper: ({ children }) => <I18nextProvider i18n={i18n}>{children}</I18nextProvider>,
  })
  return {
    ...view,
    rerenderHeader: (nextProps: Partial<HeaderProps>) =>
      view.rerender(<ScheduleHeader {...baseProps} {...props} {...nextProps} />),
  }
}

// Model the browser boundary while retaining the real useMediaQuery hook.
function installViewport(initialWidth: number) {
  let width = initialWidth
  const lists = new Set<MediaQueryList>()
  const matches = (query: string) => {
    const maxWidth = /^\(max-width: (\d+)px\)$/.exec(query)
    return maxWidth !== null && width <= Number(maxWidth[1])
  }
  vi.spyOn(window, "matchMedia").mockImplementation((query) => {
    const list = Object.assign(new EventTarget(), {
      matches: matches(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
    }) as MediaQueryList
    Object.defineProperty(list, "matches", { get: () => matches(query) })
    lists.add(list)
    return list
  })
  return (nextWidth: number) => {
    width = nextWidth
    for (const list of lists) {
      list.dispatchEvent(Object.assign(new Event("change"), { matches: matches(list.media) }))
    }
  }
}

describe("ScheduleHeader user-visible behavior", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(baseProps.nowTick)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it.each(["teacher", "admin"] as const)(
    "labels the %s group selector and supports keyboard selection",
    async (role) => {
      const setSelectedGroup = vi.fn()
      const { rerenderHeader } = await renderHeader({
        user: { ...testUser, role },
        setSelectedGroup,
      })
      const selector = screen.getByRole("combobox", { name: "Group" })
      expect(selector).toHaveTextContent("CS-2024")
      expect(selector).toHaveAttribute("aria-expanded", "false")
      const user = userEvent.setup()
      await user.tab()
      expect(selector).toHaveFocus()
      await user.keyboard("{Enter}{ArrowDown}{Enter}")
      expect(setSelectedGroup).toHaveBeenCalledExactlyOnceWith("g2")
      expect(selector).toHaveAttribute("aria-expanded", "false")

      rerenderHeader({ selectedGroup: "g2" })
      expect(selector).toHaveTextContent("CS-2025")
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Group CS-2025")
      expect(screen.queryByText("Group CS-2024")).not.toBeInTheDocument()
    }
  )

  it.each([
    ["en", "My schedule", "Schedule", "Group CS-2024"],
    ["ru", "Моё расписание", "Расписание", "Группа CS-2024"],
  ])(
    "localizes role titles and the actual selected group in %s",
    async (language, studentTitle, defaultTitle, groupTitle) => {
      const { rerenderHeader } = await renderHeader({}, language)
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(studentTitle)
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(groupTitle)
      expect(screen.queryByRole("combobox")).not.toBeInTheDocument()

      rerenderHeader({ user: { ...testUser, role: "teacher" } })
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(defaultTitle)
      expect(screen.getByRole("heading", { level: 1 })).not.toHaveTextContent(studentTitle)
    }
  )

  it("renders the loading profile's default title without privileged group controls", async () => {
    // AuthLayout permits its outlet while loading, and useScheduleData forwards
    // the nullable profile before group discovery/auto-selection completes.
    await renderHeader({ user: null, groups: [], selectedGroup: null })
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^Schedule$/)
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()
  })

  it.each([
    ["en", "Group"],
    ["ru", "Группа"],
  ])("shows the localized prompt before groups have loaded in %s", async (language, prompt) => {
    await renderHeader(
      { user: { ...testUser, role: "admin" }, groups: [], selectedGroup: null },
      language
    )
    expect(screen.getByRole("combobox", { name: prompt })).toHaveTextContent(prompt)
  })

  it("presents the current lesson's metadata, remaining percentage and live time", async () => {
    const currentLesson = { ...lesson, start_time: "10:00:00", end_time: "11:15:00" }
    await renderHeader({
      currentLesson,
      todayLessons: [currentLesson],
      currentProgress: 40,
      nowTick: new Date("2026-06-15T10:30:00"),
      timeLeftText: "Current lesson ends in 45 minutes",
      timeLeftShort: "45min",
    })
    expect(screen.getByRole("heading", { level: 3, name: "Linear Algebra" })).toBeVisible()
    expect(screen.getByText("Dr. Ivanova")).toBeVisible()
    expect(screen.getByText("ГУК-305")).toBeVisible()
    expect(screen.getByText("10:00–11:15")).toBeVisible()
    expect(screen.getByText("60%")).toBeVisible()
    const remaining = screen.getByLabelText("Current lesson ends in 45 minutes")
    expect(remaining).toHaveTextContent("45min")
    expect(remaining).toHaveAttribute("aria-live", "polite")
  })

  it("presents the next lesson's metadata and countdown at a nonzero minute", async () => {
    await renderHeader({
      nextLesson: lesson,
      todayLessons: [lesson],
      timeLeftText: "Next lesson starts in 15 minutes",
      timeLeftShort: "15min",
    })
    expect(screen.getByRole("heading", { level: 3, name: "Linear Algebra" })).toBeVisible()
    expect(screen.getByText("Dr. Ivanova")).toBeVisible()
    expect(screen.getByText("ГУК-305")).toBeVisible()
    expect(screen.getByText("11:00–12:30")).toBeVisible()
    expect(screen.getByLabelText("Next lesson starts in 15 minutes")).toHaveTextContent("15min")
    expect(screen.getByRole("timer", { name: "15 minutes 0 seconds remaining" })).toHaveAttribute(
      "aria-live",
      "polite"
    )
  })

  it("starts the countdown when the next lesson enters the half-hour window", async () => {
    vi.setSystemTime(new Date("2026-06-15T10:29:00"))
    const { rerenderHeader } = await renderHeader({
      nextLesson: lesson,
      todayLessons: [lesson],
      nowTick: new Date(),
      timeLeftText: "Next lesson starts in 31 minutes",
      timeLeftShort: "31min",
    })
    expect(screen.queryByRole("timer")).not.toBeInTheDocument()

    vi.setSystemTime(new Date("2026-06-15T10:30:00"))
    rerenderHeader({
      nowTick: new Date(),
      timeLeftText: "Next lesson starts in 30 minutes",
      timeLeftShort: "30min",
    })
    expect(screen.getByRole("timer", { name: "30 minutes 0 seconds remaining" })).toBeVisible()
  })

  it("keeps the current lesson visible while another lesson is upcoming", async () => {
    const currentLesson = {
      ...lesson,
      id: "current-lesson",
      subject: "Current Seminar",
      start_time: "10:00",
      end_time: "10:50",
    }
    await renderHeader({
      currentLesson,
      nextLesson: lesson,
      todayLessons: [currentLesson, lesson],
      currentProgress: 90,
      timeLeftText: "Current lesson ends in 5 minutes",
      timeLeftShort: "5min",
    })
    expect(screen.getByRole("heading", { level: 3, name: "Current Seminar" })).toBeVisible()
    expect(
      screen.queryByRole("heading", { level: 3, name: "Linear Algebra" })
    ).not.toBeInTheDocument()
    expect(screen.queryByRole("timer")).not.toBeInTheDocument()
  })

  it("keeps both progress-ring circles centered when the viewport changes", async () => {
    const resize = installViewport(1440)
    const currentLesson = { ...lesson, start_time: "10:00", end_time: "11:15" }
    const { container } = await renderHeader({
      currentLesson,
      todayLessons: [currentLesson],
      currentProgress: 60,
      timeLeftText: "Current lesson ends in 30 minutes",
      timeLeftShort: "30min",
    })
    const ring = container.querySelector("svg:has(> circle + circle)")
    expect(ring).toHaveAttribute("width", "80")
    expect(ring).toHaveAttribute("height", "80")
    expect(ring).toHaveAttribute("aria-hidden", "true")
    expect(ring?.querySelectorAll("circle")).toHaveLength(2)
    for (const circle of ring!.querySelectorAll("circle")) {
      expect(circle).toHaveAttribute("cx", "40")
      expect(circle).toHaveAttribute("cy", "40")
    }

    act(() => resize(390))
    expect(ring).toHaveAttribute("width", "64")
    expect(ring).toHaveAttribute("height", "64")
    for (const circle of ring!.querySelectorAll("circle")) {
      expect(circle).toHaveAttribute("cx", "32")
      expect(circle).toHaveAttribute("cy", "32")
    }
  })

  it("opens settings from its localized keyboard-accessible control", async () => {
    const onOpenSettings = vi.fn()
    await renderHeader({ onOpenSettings }, "ru")
    const user = userEvent.setup()
    const control = screen.getByRole("button", { name: "Настройки" })
    await user.tab()
    expect(control).toHaveFocus()
    await user.keyboard("{Enter}")
    expect(onOpenSettings).toHaveBeenCalledOnce()
  })

  it("updates the complete-day message when the selected group's lesson list changes", async () => {
    const { rerenderHeader } = await renderHeader({
      todayLessons: [lesson],
      nowTick: new Date("2026-06-15T17:00:00"),
    })
    expect(screen.getByText("Great day! All lessons complete")).toBeVisible()
    rerenderHeader({ selectedGroup: "g2", todayLessons: [] })
    expect(screen.getByText("No more lessons today")).toBeVisible()
    expect(screen.queryByText("Great day! All lessons complete")).not.toBeInTheDocument()
  })
})
