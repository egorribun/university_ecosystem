import type { Page, Route } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// R41 (ТЗ §9, negative scope): the Activity page must not offer learning goals
// or attendance targets. Registration statistics are in scope; goal and target
// controls are not. The stats summary is mocked with a populated payload so the
// negative checks run against the real populated page, not an error state.

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
      { date: "2026-11-11", registered: 3, total: 5 },
    ],
    trend: [],
    recent: [
      { date: "2026-11-10", status: "present", course: "Algorithms" },
      { date: "2026-11-11", status: "late", course: "Databases" },
    ],
  },
  grades: {
    average: 4.2,
    scale: 5,
    trend: [],
    recent: [{ course: "Algorithms", score: 4, max: 5, date: "2026-11-10" }],
  },
  participation: {
    events: 4,
    hours: 6,
    groups: 2,
    trend: [],
    recent: [{ title: "Tech talk", date: "2026-11-09", role: "participant" }],
  },
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
      await page.emulateMedia({ colorScheme: "light" })

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

      const visibleText = await page.locator("body").innerText()
      expect(visibleText).not.toMatch(FORBIDDEN_TEXT)

      await expect(page.locator(FORBIDDEN_TEST_ID)).toHaveCount(0)
    })
  }
}
