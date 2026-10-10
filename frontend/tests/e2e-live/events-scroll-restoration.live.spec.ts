import { expect, type Page } from "@playwright/test"
import { loginAs, test } from "./fixtures"

const LANGUAGE_KEY = "ue:language"

const EVENT_LOCALES = [
  {
    code: "ru",
    languageOption: /Русский|Russian/u,
    listHeading: "Мероприятия",
    archiveTab: /Прошедшие|Past events/u,
    eventTitle: /^Архив: Выпускной вечер 2026$/u,
  },
  {
    code: "en",
    languageOption: /Английский|English/u,
    listHeading: "Events",
    archiveTab: /Прошедшие|Past events/u,
    eventTitle: /^Archive: Class of 2026 graduation ceremony$/u,
  },
] as const

type EventLocale = (typeof EVENT_LOCALES)[number]

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

async function chooseLanguage(page: Page, languageOption: RegExp) {
  const option = page.getByRole("radio", { name: languageOption })
  await expect(option).toBeVisible()
  // The native radio is visually hidden; use the actual Settings label just
  // as a user would. Storage and cookie values below are observations only.
  await option.locator("xpath=ancestor::label").click()
  await expect(option).toBeChecked()
}

async function selectLanguageThroughSettings(page: Page, locale: EventLocale) {
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/u })).toBeVisible()
  await openLanguageOptions(page)

  // Ensure both locale cases exercise a real preference change through the UI,
  // even when the fresh browser context starts in Russian.
  const otherLanguageOption = locale.code === "en" ? /Русский|Russian/u : /Английский|English/u
  await chooseLanguage(page, otherLanguageOption)
  await expect(page.locator("html")).toHaveAttribute("lang", locale.code === "en" ? "ru" : "en")
  await chooseLanguage(page, locale.languageOption)
  await expect(page.locator("html")).toHaveAttribute("lang", locale.code)
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), LANGUAGE_KEY))
    .toBe(locale.code)
  await expect
    .poll(() => page.evaluate(() => document.cookie))
    .toContain(`ue:language=${locale.code}`)
}

async function verifyLanguagePersistsAfterReload(page: Page, locale: EventLocale) {
  await page.reload()
  await expect(page.locator("html")).toHaveAttribute("lang", locale.code)
  await expect(page.getByRole("heading", { name: /Settings|Настройки/u })).toBeVisible()
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), LANGUAGE_KEY))
    .toBe(locale.code)
  await expect
    .poll(() => page.evaluate(() => document.cookie))
    .toContain(`ue:language=${locale.code}`)

  await openLanguageOptions(page)
  await expect(page.getByRole("radio", { name: locale.languageOption })).toBeChecked()
}

async function verifyEventsHistoryForLanguage(page: Page, locale: EventLocale) {
  // Confirm the selected Settings control and its persisted server-visible
  // cookie before navigating into the acceptance flow.
  await expect(page.getByRole("radio", { name: locale.languageOption })).toBeChecked()
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), LANGUAGE_KEY))
    .toBe(locale.code)
  await expect
    .poll(() => page.evaluate(() => document.cookie))
    .toContain(`ue:language=${locale.code}`)

  await page.goto("/events")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/events")
  await expect(page.locator("html")).toHaveAttribute("lang", locale.code)
  await expect(page.getByRole("heading", { name: locale.listHeading })).toBeVisible()

  const archiveTab = page.getByRole("tab", { name: locale.archiveTab })
  await expect(archiveTab).toBeVisible()
  await archiveTab.click()
  await expect(page).toHaveURL(/\/events\?tab=archive$/u)
  const archiveUrl = page.url()

  // This seeded archive event is the last item in chronological order. The
  // test reads its details and history without changing or registering it.
  const selectedEvent = page.getByRole("link", { name: locale.eventTitle })
  await expect(selectedEvent).toBeVisible()
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await selectedEvent.scrollIntoViewIfNeeded()

  const selectedHref = await selectedEvent.getAttribute("href")
  expect(selectedHref).toMatch(/^\/events\/[0-9a-f-]+$/u)
  const selectedUrl = new URL(selectedHref ?? "", page.url())
  const originalPosition = await selectedEvent.evaluate((link) => ({
    scrollY: Math.round(window.scrollY),
    top: Math.round(link.getBoundingClientRect().top),
  }))
  expect(
    originalPosition.scrollY,
    `${locale.code} seeded Events archive item must be below the initial viewport`
  ).toBeGreaterThan(0)

  await selectedEvent.click()
  await expect(page).toHaveURL(selectedUrl.href)
  const detailHeading = page.getByRole("heading", { name: locale.eventTitle, exact: true })
  await expect(detailHeading).toBeVisible()
  const originalDetailPosition = await detailHeading.evaluate((heading) => ({
    scrollY: Math.round(window.scrollY),
    top: Math.round(heading.getBoundingClientRect().top),
  }))

  await page.goBack()
  await expect(page).toHaveURL(archiveUrl)
  await expect(archiveTab).toHaveAttribute("aria-selected", "true")
  const restoredEvent = page.getByRole("link", { name: locale.eventTitle })
  await expect(restoredEvent).toHaveAttribute("href", selectedHref ?? "")
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: `${locale.code} Back should restore the Events archive scroll position`,
    })
    .toBe(originalPosition.scrollY)
  await expect
    .poll(() => restoredEvent.evaluate((link) => Math.round(link.getBoundingClientRect().top)))
    .toBe(originalPosition.top)

  await page.goForward()
  await expect(page).toHaveURL(selectedUrl.href)
  const restoredDetailHeading = page.getByRole("heading", {
    name: locale.eventTitle,
    exact: true,
  })
  await expect(restoredDetailHeading).toBeVisible()
  await expect
    .poll(() => restoredDetailHeading.evaluate(() => Math.round(window.scrollY)), {
      message: `${locale.code} Forward should restore the event detail scroll position`,
    })
    .toBe(originalDetailPosition.scrollY)
  await expect
    .poll(() =>
      restoredDetailHeading.evaluate((heading) => Math.round(heading.getBoundingClientRect().top))
    )
    .toBe(originalDetailPosition.top)

  await page.goBack()
  await expect(page).toHaveURL(archiveUrl)
  await expect(archiveTab).toHaveAttribute("aria-selected", "true")
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: `${locale.code} Back after Forward should restore the Events archive position`,
    })
    .toBe(originalPosition.scrollY)
  const restoredEventAfterForward = page.getByRole("link", { name: locale.eventTitle })
  await expect(restoredEventAfterForward).toBeVisible()
  await expect(restoredEventAfterForward).toHaveAttribute("href", selectedHref ?? "")
  await expect
    .poll(() =>
      restoredEventAfterForward.evaluate((link) => Math.round(link.getBoundingClientRect().top))
    )
    .toBe(originalPosition.top)
  await expect(page).toHaveURL(archiveUrl)
}

for (const locale of EVENT_LOCALES) {
  test(`browser history restores the Events archive position in ${locale.code}`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" })
    await loginAs(page, "student")

    await selectLanguageThroughSettings(page, locale)
    await verifyLanguagePersistsAfterReload(page, locale)
    await verifyEventsHistoryForLanguage(page, locale)
  })
}
