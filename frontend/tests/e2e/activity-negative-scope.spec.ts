import type { Page, Route } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// R41 (ТЗ §9, negative scope): the Activity page must not offer learning goals
// or attendance targets. Registration statistics are in scope; goal and target
// controls are not. The stats summary is mocked with a populated payload so the
// negative checks run against the real populated page, not an error state.
// R40 checks the same mocked summary through the real chart transformations.
// This is frontend fixture evidence, not proof of populated live backend data.

const LANGUAGE_STORAGE_KEY = "ue:language"

// Visible copy that would announce a learning goal, a learning target or an
// attendance target (RU and EN). Event "registration" copy is allowed.
const FORBIDDEN_TEXT =
  /\b(learning goals?|learning targets?|learning objectives?|goals?|attendance targets?|target attendance)\b|учебн\w*\s+цел|цел\w*\s+обучения|целев\w*\s+посещаем|посещаемост\w*\s+цел|цел\w*\s+посещаем/iu

const FORBIDDEN_TEST_ID =
  '[data-testid*="goal" i], [data-testid*="target" i], [data-testid*="learning" i], [data-testid*="attendance-target" i]'

// Section titles rendered for a populated page (ru/activity.json, en/activity.json).
const POPULATED_SECTION_TITLE: Record<string, string> = {
  ru: "Регистрации на мероприятия",
  en: "Event registrations",
}

const LOCALES = [
  { locale: "ru", label: "RU" },
  { locale: "en", label: "EN" },
] as const

const VIEWPORTS = [
  { width: 1440, height: 900, label: "1440" },
  { width: 390, height: 844, label: "390" },
] as const

const SUMMARY_ENVELOPE = {
  attendance: {
    percent: 72,
    present: 18,
    total: 25,
    streak_days: 3,
    period_key: "90d",
    period_label: "90 days",
    daily: [
      { date: "2026-11-10", registered: 4, total: 5 },
      { date: "2026-11-09", registered: 11, total: 15 },
      { date: "2026-11-11", registered: 3, total: 5 },
    ],
    trend: 12,
    recent: [
      { date: "2026-11-10", status: "present", course: "Algorithms" },
      { date: "2026-11-11", status: "late", course: "Databases" },
    ],
  },
  grades: {
    average: 84,
    scale: "100",
    trend: -6,
    recent: [
      { course: "Algorithms", score: 80, date: "2026-11-10" },
      { course: "Algorithms", score: 90, date: "2026-11-11" },
      { course: "Databases", score: 82, date: "2026-11-10" },
    ],
  },
  participation: {
    events: 4,
    hours: 6,
    groups: 2,
    trend: -1,
    recent: [{ title: "Tech talk", date: "2026-11-09", role: "participant" }],
  },
}

// Explicit expected copy keeps locale regressions observable instead of deriving
// expectations from the same translations/components under test.
const POPULATED_COPY = {
  ru: {
    heatmap: "Тепловая карта активности по дням",
    contribution: "активностей",
    trend: "Линейный график доли регистраций на мероприятия",
    dates: ["9 ноября 2026 г.", "10 ноября 2026 г.", "11 ноября 2026 г."],
    grades: "Столбчатая диаграмма оценок по предметам",
    gradeCard: "Статистика оценок",
    gradeGauge: "Шкала оценок: 84.0 из 100",
    gradeTrend: "-6,0 баллов",
    comparison: "Сравнение периодов",
    labels: ["Регистрации", "Ср. оценка", "События"],
    previous: ["было 60%", "было 90.0", "было 5"],
  },
  en: {
    heatmap: "Activity heatmap calendar showing daily contributions",
    contribution: "activities",
    trend: "Line chart showing event registration percentage over time",
    dates: ["November 9, 2026", "November 10, 2026", "November 11, 2026"],
    grades: "Bar chart showing grades by subject",
    gradeCard: "Grade statistics",
    gradeGauge: "Grade gauge showing 84.0 out of 100",
    gradeTrend: "-6.0 points",
    comparison: "Period Comparison",
    labels: ["Registrations", "Avg. grade", "Events"],
    previous: ["vs 60%", "vs 90.0", "vs 5"],
  },
} as const

async function expectPopulatedValues(page: Page, locale: keyof typeof POPULATED_COPY) {
  const copy = POPULATED_COPY[locale]
  const heatmap = page.getByRole("group", { name: copy.heatmap, exact: true })
  await expect(heatmap).toBeVisible()
  // Counts merge all three recent arrays; daily registration totals are not
  // heatmap counts. Each section is below the five-item truncation boundary.
  for (const [date, count, level] of [
    ["2026-11-09", 1, 2],
    ["2026-11-10", 3, 4],
    ["2026-11-11", 2, 3],
    ["2026-11-14", 0, 0],
  ] as const) {
    const cell = heatmap.getByRole("img", {
      name: `${date}: ${count} ${copy.contribution}`,
      exact: true,
    })
    await expect(cell).toBeVisible()
    await expect(cell).toHaveAttribute("style", `background-color: var(--activity-heat-${level});`)
    await expect(
      heatmap
        .getByRole("row")
        .filter({ has: page.getByRole("rowheader", { name: date, exact: true }) })
        .getByRole("cell")
    ).toHaveText(String(count))
  }
  await expect(heatmap.locator("tbody tr")).toHaveCount(90)

  const trend = page.getByRole("img", { name: copy.trend, exact: true })
  await expect(trend).toBeVisible()
  for (const date of copy.dates) await expect(trend.getByText(date, { exact: true })).toBeVisible()
  // The visible polyline must plot sorted daily ratios (73%, 80%, 60%), not recent-feed counts.
  const points = await trend.locator("polyline").getAttribute("points")
  const coordinates = points?.split(/[ ,]/u).map(Number)
  expect(coordinates).toHaveLength(6)
  for (const [index, expected] of [36, 64.5, 212, 23.6666666667, 388, 140.3333333333].entries()) {
    expect(coordinates?.[index]).toBeCloseTo(expected, 5)
  }
  const trendTable = page.getByRole("table", { name: copy.trend, exact: true })
  await expect(trendTable.locator("tbody th")).toHaveText([...copy.dates])
  await expect(trendTable.locator("tbody td")).toHaveText(["73", "80", "60"])

  const grades = page.getByRole("img", { name: copy.grades, exact: true })
  await expect(grades).toBeVisible()
  await expect(grades.getByText("85.0/100", { exact: true })).toBeVisible()
  await expect(grades.getByText("82.0/100", { exact: true })).toBeVisible()
  const gradeTable = page.getByRole("table", { name: copy.grades, exact: true })
  await expect(gradeTable.locator("tbody th")).toHaveText(["Algorithms", "Databases"])
  await expect(gradeTable.locator("tbody td")).toHaveText(["85.0 / 100", "82.0 / 100"])
  const gradeCard = page.getByRole("group", { name: copy.gradeCard, exact: true })
  await expect(gradeCard.getByText("84/100", { exact: true })).toBeVisible()
  await expect(gradeCard.getByRole("img", { name: copy.gradeGauge, exact: true })).toBeVisible()
  await expect(gradeCard.getByText(copy.gradeTrend, { exact: true })).toBeVisible()

  const comparison = page.getByRole("region", { name: copy.comparison, exact: true })
  for (const [index, current, delta] of [
    [0, "72%", "+20.0%"],
    [1, "84.0", "-6.7%"],
    [2, "4", "-20.0%"],
  ] as const) {
    const card = comparison.locator(".activity-comparative-card").filter({
      has: page.getByText(copy.labels[index], { exact: true }),
    })
    await expect(card.getByText(current, { exact: true })).toBeVisible()
    await expect(card.getByText(copy.previous[index], { exact: true })).toBeVisible()
    await expect(card.getByText(delta, { exact: true })).toBeVisible()
  }
}

async function mockActivitySummary(page: Page): Promise<void> {
  // Registered after the shared mock, so this handler runs first and falls back
  // to it for every other request.
  await page.route("**/*", async (route: Route) => {
    const url = new URL(route.request().url())
    if (route.request().method() !== "GET" || !/\/stats\/summary\/?$/u.test(url.pathname)) {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SUMMARY_ENVELOPE),
    })
  })
}

async function openActivity(page: Page, locale: string): Promise<void> {
  // Registered after the shared mock, so this init script runs last and keeps
  // the requested language instead of the shared RU default.
  await page.addInitScript(
    ({ key, lang }: { key: string; lang: string }) => {
      window.localStorage.setItem(key, lang)
    },
    { key: LANGUAGE_STORAGE_KEY, lang: locale }
  )
  // The shared mock sets the ue:language cookie to ru for every context. Set
  // the requested locale after it so SSR and the client agree on EN.
  const baseURL = test.info().project.use.baseURL ?? "http://127.0.0.1:5173"
  await page
    .context()
    .addCookies([{ name: LANGUAGE_STORAGE_KEY, value: locale, url: new URL(baseURL).origin }])
  await page.goto("/activity", { waitUntil: "domcontentloaded" })
  await page.waitForFunction(() => window.__APP_HYDRATED === true, null, { timeout: 15_000 })
  await page.waitForURL(/\/activity$/u)
}

for (const { locale, label: localeLabel } of LOCALES) {
  for (const viewport of VIEWPORTS) {
    test(`activity page has no learning goal or attendance target UI at ${viewport.label}px ${localeLabel}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
      // Keep heatmap calendar cells stable without freezing animation/network timers.
      await page.clock.setFixedTime(new Date("2026-11-14T12:00:00Z"))

      await useMockApi(page, { authenticated: true })
      await mockActivitySummary(page)
      await openActivity(page, locale)

      // The populated page must render its registration section with values,
      // and no error alert may be shown, before the negative checks run.
      await expect(
        page.getByText(POPULATED_SECTION_TITLE[locale] ?? "", { exact: false }).first()
      ).toBeVisible({ timeout: 30_000 })
      await expect(page.getByText("72", { exact: false }).first()).toBeVisible()
      // The route announcer is an empty role="alert"; only alerts with text count.
      await expect(page.getByRole("alert").filter({ hasText: /\S/u })).toHaveCount(0)

      await expectPopulatedValues(page, locale)

      const visibleText = await page.locator("body").innerText()
      expect(visibleText).not.toMatch(FORBIDDEN_TEXT)

      await expect(page.locator(FORBIDDEN_TEST_ID)).toHaveCount(0)
    })
  }
}
