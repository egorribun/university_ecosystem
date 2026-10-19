import { render, screen, within } from "@testing-library/react"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AttendanceCard } from "../AttendanceCard"
import { GradesCard } from "../GradesCard"
import { ParticipationCard } from "../ParticipationCard"
import TrendChip from "../TrendChip"
import enActivity from "@/i18n/locales/en/activity.json"
import ruActivity from "@/i18n/locales/ru/activity.json"

type Language = "en" | "ru"

async function renderActivityCards(language: Language, attendanceTrend = 2.5) {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    resources: { en: { activity: enActivity }, ru: { activity: ruActivity } },
    interpolation: { escapeValue: false },
  })

  return render(
    <I18nextProvider i18n={i18n}>
      <div>
        <AttendanceCard
          hasInitiallyLoaded
          ringSize={64}
          attendance={{
            percent: 80,
            present: 8,
            total: 10,
            trend: attendanceTrend,
            periodKey: "90d",
            periodLabel: "90 days",
            recent: [],
          }}
        />
        <GradesCard
          hasInitiallyLoaded
          ringSize={64}
          grades={{ average: 4.2, scale: "5", trend: 0.5, recent: [] }}
        />
        <ParticipationCard
          hasInitiallyLoaded
          ringSize={64}
          separator=" • "
          participation={{ events: 4, trend: 2, recent: [] }}
        />
      </div>
    </I18nextProvider>
  )
}

beforeEach(() => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query) =>
      ({
        matches: query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

const localizedCases: Array<{
  language: Language
  attendanceName: string
  attendanceTitle: string
  gradesName: string
  participationName: string
  attendanceTrend: string
  gradesTrend: string
  participationTrend: string
}> = [
  {
    language: "en",
    attendanceName: enActivity.a11y.attendanceCard,
    attendanceTitle: "Event registrations",
    gradesName: enActivity.a11y.gradesCard,
    participationName: enActivity.a11y.participationCard,
    attendanceTrend: "+2.5 pp",
    gradesTrend: "+0.5 points",
    participationTrend: "+2 events",
  },
  {
    language: "ru",
    attendanceName: ruActivity.a11y.attendanceCard,
    attendanceTitle: "Регистрации на мероприятия",
    gradesName: ruActivity.a11y.gradesCard,
    participationName: ruActivity.a11y.participationCard,
    attendanceTrend: "+2,5 п.п.",
    gradesTrend: "+0,5 балла",
    participationTrend: "+2 события",
  },
]

describe("activity trend units", () => {
  it.each(localizedCases)("renders localized real-card trends in $language", async (row) => {
    await renderActivityCards(row.language)

    const attendance = within(screen.getByRole("group", { name: row.attendanceName }))
    const grades = within(screen.getByRole("group", { name: row.gradesName }))
    const participation = within(screen.getByRole("group", { name: row.participationName }))
    expect(attendance.getByText(row.attendanceTitle)).toBeVisible()
    expect(attendance.getByText(row.attendanceTrend)).toBeVisible()
    expect(grades.getByText(row.gradesTrend)).toBeVisible()
    expect(participation.getByText(row.participationTrend)).toBeVisible()
  })

  it.each([
    { language: "en" as const, value: -0.04, expected: "0.0 pp" },
    { language: "ru" as const, value: -0.04, expected: "0,0 п.п." },
    { language: "en" as const, value: -2.5, expected: "-2.5 pp" },
    { language: "ru" as const, value: -2.5, expected: "-2,5 п.п." },
  ])("formats signed attendance trends in $language", async ({ language, value, expected }) => {
    await renderActivityCards(language, value)

    const name = language === "ru" ? ruActivity.a11y.attendanceCard : enActivity.a11y.attendanceCard
    const attendance = within(screen.getByRole("group", { name }))
    expect(attendance.getByText(expected)).toBeVisible()
    expect(attendance.queryByText(/[-−]0[.,]0/)).not.toBeInTheDocument()
  })
})

describe("localized trend plurals", () => {
  it.each([
    { language: "en", unit: "points" as const, value: 1, expected: "+1.0 point" },
    { language: "en", unit: "events" as const, value: -1, expected: "-1 event" },
    { language: "ru", unit: "points" as const, value: 5, expected: "+5,0 баллов" },
    { language: "ru", unit: "events" as const, value: 1, expected: "+1 событие" },
    { language: "ru", unit: "events" as const, value: 5, expected: "+5 событий" },
    { language: "ru", unit: "events" as const, value: -2, expected: "-2 события" },
  ])("formats $expected in $language", async ({ language, unit, value, expected }) => {
    const i18n = createInstance()
    await i18n.init({
      lng: language,
      resources: { en: { activity: enActivity }, ru: { activity: ruActivity } },
      interpolation: { escapeValue: false },
    })
    render(
      <I18nextProvider i18n={i18n}>
        <TrendChip value={value} unit={unit} />
      </I18nextProvider>
    )
    expect(screen.getByText(expected)).toBeVisible()
  })
})
