import type { Page } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// R41 (ТЗ §9, negative scope): the Activity page must not offer learning goals
// or attendance targets. Registration statistics are in scope; goal and target
// controls are not. The page is loaded first so the negative checks cannot
// pass on an empty or redirected document.

const LANGUAGE_STORAGE_KEY = "ue:language"

// Visible copy that would announce a learning goal, a learning target or an
// attendance target (RU and EN). Event "registration" copy is allowed.
const FORBIDDEN_TEXT =
  /\b(learning goals?|learning targets?|learning objectives?|goals?|attendance targets?|target attendance)\b|учебн\w*\s+цел|цел\w*\s+обучения|целев\w*\s+посещаем|посещаемост\w*\s+цел|цел\w*\s+посещаем/iu

const FORBIDDEN_TEST_ID =
  '[data-testid*="goal" i], [data-testid*="target" i], [data-testid*="learning" i], [data-testid*="attendance-target" i]'

const LOCALES = [
  { locale: "ru", label: "RU" },
  { locale: "en", label: "EN" },
] as const

const VIEWPORTS = [
  { width: 1440, height: 900, label: "1440" },
  { width: 390, height: 844, label: "390" },
] as const

async function openActivity(page: Page, locale: string): Promise<void> {
  // Registered after the shared mock, so this init script runs last and keeps
  // the requested language instead of the shared RU default.
  await page.addInitScript(
    ({ key, lang }: { key: string; lang: string }) => {
      window.localStorage.setItem(key, lang)
    },
    { key: LANGUAGE_STORAGE_KEY, lang: locale }
  )
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
      await openActivity(page, locale)

      // The page must have rendered real content before the negative checks run.
      await expect(page.locator("main h1, main h2").first()).toBeVisible({ timeout: 30_000 })

      const visibleText = await page.locator("body").innerText()
      expect(visibleText.trim().length).toBeGreaterThan(0)
      expect(visibleText).not.toMatch(FORBIDDEN_TEXT)

      await expect(page.locator(FORBIDDEN_TEST_ID)).toHaveCount(0)
    })
  }
}
