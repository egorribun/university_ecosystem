import type { Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

const THEME_KEY = "ue-mode"
const LANGUAGE_KEY = "ue:language"

async function openThemeOptions(page: Page) {
  const accordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Тема|Theme/i })
    .first()
  await expect(accordion).toBeVisible()
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

async function chooseTheme(page: Page, name: RegExp) {
  const option = page.getByRole("radio", { name })
  await expect(option).toBeVisible()
  // Radio inputs use a visually hidden native input; activate the real
  // wrapping label, matching the way the other appearance settings are used.
  await option.locator("xpath=ancestor::label").click()
  await expect(option).toBeChecked()
}

async function openLanguageOptions(page: Page) {
  const accordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Язык интерфейса|Interface language/u })
    .first()
  await expect(accordion).toBeVisible()
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

async function chooseLanguage(page: Page, name: RegExp) {
  const option = page.getByRole("radio", { name })
  await expect(option).toBeVisible()
  await option.locator("xpath=ancestor::label").click()
  await expect(option).toBeChecked()
}

async function verifyReloadedAppearance(
  page: Page,
  language: "en" | "ru",
  settingsHeading: RegExp,
  languageOption: RegExp,
  theme: "dark" | "light",
  themeOption: RegExp
) {
  await expect(page.locator("html")).toHaveAttribute("lang", language)
  await expect(page.getByRole("heading", { name: settingsHeading })).toBeVisible()
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), LANGUAGE_KEY))
    .toBe(language)
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain(`ue:language=${language}`)
  if (theme === "dark") {
    await expect(page.locator("html")).toHaveClass(/\bdark\b/u)
  } else {
    await expect(page.locator("html")).not.toHaveClass(/\bdark\b/u)
  }

  await openLanguageOptions(page)
  await expect(page.getByRole("radio", { name: languageOption })).toBeChecked()
  await openThemeOptions(page)
  await expect(page.getByRole("radio", { name: themeOption })).toBeChecked()
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY)).toBe(theme)
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain(`ue-mode=${theme}`)
}

test("theme and language preferences survive reload and are restored", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  // This seeded student is synthetic and exists only in the disposable live stand.
  // Theme state is browser-local; the test does not write or clean up account data.
  await loginAs(page, "student")
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

  await openThemeOptions(page)
  await chooseTheme(page, /Система|System/i)
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/u)
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY))
    .toBe("system")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=system")

  // System mode follows subsequent OS preference changes without rewriting
  // the user's persisted choice to the currently resolved light/dark value.
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" })
  await expect(page.locator("html")).toHaveClass(/\bdark\b/u)
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY))
    .toBe("system")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=system")

  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/u)
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY))
    .toBe("system")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=system")

  await chooseTheme(page, /Тёмная|Dark/i)
  await expect(page.locator("html")).toHaveClass(/\bdark\b/u)
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY)).toBe("dark")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=dark")

  await page.reload()
  await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()
  await openThemeOptions(page)
  await expect(page.getByRole("radio", { name: /Тёмная|Dark/i })).toBeChecked()
  await expect(page.locator("html")).toHaveClass(/\bdark\b/u)
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY)).toBe("dark")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=dark")

  await openLanguageOptions(page)
  await chooseLanguage(page, /Английский|English/u)
  await expect(page.locator("html")).toHaveAttribute("lang", "en")
  await page.reload()
  await verifyReloadedAppearance(page, "en", /Settings/u, /English/u, "dark", /Dark/u)

  await chooseTheme(page, /Light/u)
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/u)
  await page.reload()
  await verifyReloadedAppearance(page, "en", /Settings/u, /English/u, "light", /Light/u)

  await chooseLanguage(page, /Русский|Russian/u)
  await expect(page.locator("html")).toHaveAttribute("lang", "ru")
  await page.reload()
  await verifyReloadedAppearance(page, "ru", /Настройки/u, /Русский/u, "light", /Светлая/u)

  // Restore the browser-local defaults through the same UI used to change them.
  await openThemeOptions(page)
  await chooseTheme(page, /Система|System/i)
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/u)
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), THEME_KEY))
    .toBe("system")
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain("ue-mode=system")
})
