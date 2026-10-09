import { expect, type Page } from "@playwright/test"
import { loginAs, test } from "./fixtures"

const NEWS_LOCALIZATIONS = {
  en: {
    languageOption: /English|Английский/u,
    language: "en",
    listHeading: /^(?:University news|University news ?[0-9]+)$/u,
    categoryOption: /Science/u,
    articleTitle: "GUU ranks among the country's top 20 universities",
  },
  ru: {
    languageOption: /Русский|Russian/u,
    language: "ru",
    listHeading: /^(?:Новости университета|Новости университета ?[0-9]+)$/u,
    categoryOption: /Наука/u,
    articleTitle: "ГУУ вошёл в топ-20 лучших университетов страны",
  },
} as const

async function switchLanguageThroughSettings(page: Page, language: "en" | "ru") {
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/u })).toBeVisible()

  const languageAccordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Язык интерфейса|Interface language/u })
    .first()
  await expect(languageAccordion).toBeVisible()
  if ((await languageAccordion.getAttribute("aria-expanded")) !== "true") {
    await languageAccordion.click()
  }
  await expect(languageAccordion).toHaveAttribute("aria-expanded", "true")

  const option = page.getByRole("radio", { name: NEWS_LOCALIZATIONS[language].languageOption })
  await expect(option).toBeVisible()
  // Activate the real Settings control; the browser storage/cookie are only
  // observed after the UI updates the language preference.
  await option.locator("xpath=ancestor::label").click()
  await expect(option).toBeChecked()
  await expect(page.locator("html")).toHaveAttribute("lang", language)
  await expect.poll(() => page.evaluate(() => localStorage.getItem("ue:language"))).toBe(language)
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain(`ue:language=${language}`)
}

async function verifyLanguagePersistsAfterReload(page: Page, language: "en" | "ru") {
  await page.reload()
  await expect(page.locator("html")).toHaveAttribute("lang", language)
  await expect(page.getByRole("heading", { name: /Settings|Настройки/u })).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem("ue:language"))).toBe(language)
  await expect.poll(() => page.evaluate(() => document.cookie)).toContain(`ue:language=${language}`)

  const languageAccordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Язык интерфейса|Interface language/u })
    .first()
  if ((await languageAccordion.getAttribute("aria-expanded")) !== "true") {
    await languageAccordion.click()
  }
  const selectedOption = page.getByRole("radio", {
    name: NEWS_LOCALIZATIONS[language].languageOption,
  })
  await expect(selectedOption).toBeChecked()
}

async function verifyNewsHistoryForLanguage(page: Page, language: "en" | "ru") {
  const locale = NEWS_LOCALIZATIONS[language]
  await page.goto("/news")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/news")
  await expect(page.locator("html")).toHaveAttribute("lang", locale.language)
  const listHeading = page.getByRole("heading", { name: locale.listHeading, exact: true })
  await expect(listHeading).toBeVisible()

  const beforeFilterScrollY = await page.evaluate(() => Math.round(window.scrollY))
  const scienceFilter = page.getByRole("button", { name: locale.categoryOption })
  await scienceFilter.click()
  await expect.poll(() => new URL(page.url()).searchParams.get("cat")).toBe("science")
  await expect(scienceFilter).toHaveAttribute("aria-current", "page")
  await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(beforeFilterScrollY)

  if ((page.viewportSize()?.width ?? 1024) < 640) {
    await expect
      .poll(() =>
        scienceFilter.evaluate((button) => {
          const toolbar = button.closest<HTMLElement>('[role="toolbar"]')
          if (!toolbar) return Number.POSITIVE_INFINITY
          const toolbarRect = toolbar.getBoundingClientRect()
          const buttonRect = button.getBoundingClientRect()
          const centerDelta =
            buttonRect.left + buttonRect.width / 2 - (toolbarRect.left + toolbar.clientWidth / 2)
          return Math.abs(centerDelta)
        })
      )
      .toBeLessThanOrEqual(2)
  }

  const listUrl = page.url()

  // This synthetic article is part of the repeatable RU/EN demo seed. Opening
  // and returning never edits or deletes content or bookmarks for any account.
  const selectedNews = page.getByRole("link", { name: locale.articleTitle })
  await expect(selectedNews).toBeVisible()
  await expect(selectedNews).toContainText(locale.articleTitle)
  await page.evaluate(() => document.fonts.ready.then(() => undefined))

  const maxScrollY = await page.evaluate(() => {
    const scrollElement = document.scrollingElement
    return scrollElement ? Math.round(scrollElement.scrollHeight - window.innerHeight) : 0
  })
  expect(maxScrollY, `${language} News feed must have a real scrollable range`).toBeGreaterThan(0)
  const targetScrollY = await selectedNews.evaluate((link) => {
    const scrollElement = document.scrollingElement
    const maximumScrollY = scrollElement
      ? Math.round(scrollElement.scrollHeight - window.innerHeight)
      : 0
    const documentTop = window.scrollY + link.getBoundingClientRect().top
    return Math.min(maximumScrollY, Math.max(1, Math.round(documentTop - window.innerHeight / 3)))
  })
  expect(
    targetScrollY,
    `${language} News feed target must require nonzero scrolling`
  ).toBeGreaterThan(0)
  await page.evaluate(
    (scrollY) => window.scrollTo({ top: scrollY, behavior: "instant" }),
    targetScrollY
  )
  await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(targetScrollY)
  await expect(selectedNews).toBeInViewport()

  const selectedHref = await selectedNews.getAttribute("href")
  expect(selectedHref).toMatch(/^\/news\/[0-9a-f-]+$/u)
  const selectedUrl = new URL(selectedHref ?? "", page.url())
  const originalPosition = await selectedNews.evaluate((link) => ({
    scrollY: Math.round(window.scrollY),
    top: Math.round(link.getBoundingClientRect().top),
  }))
  expect(
    originalPosition.scrollY,
    `${language} seeded News article position must be captured after a nonzero feed scroll`
  ).toBeGreaterThan(0)

  await selectedNews.click()
  await expect(page).toHaveURL(selectedUrl.href)
  const detailHeading = page.getByRole("heading", { name: locale.articleTitle, exact: true })
  await expect(detailHeading).toBeVisible()
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await page.evaluate(() => window.scrollTo({ top: 320, behavior: "instant" }))
  const originalDetailPosition = await detailHeading.evaluate((heading) => ({
    scrollY: Math.round(window.scrollY),
    top: Math.round(heading.getBoundingClientRect().top),
  }))
  const detailScrollY = originalDetailPosition.scrollY
  expect(
    detailScrollY,
    `${language} News detail must have a restorable reading position`
  ).toBeGreaterThan(0)

  await page.goBack()
  await expect(page).toHaveURL(listUrl)
  await expect(listHeading).toBeVisible()
  await expect(page.getByRole("button", { name: locale.categoryOption })).toHaveAttribute(
    "aria-current",
    "page"
  )
  const restoredNews = page.getByRole("link", { name: locale.articleTitle })
  await expect(restoredNews).toBeVisible()
  await expect(restoredNews).toHaveAttribute("href", selectedHref ?? "")
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: `${language} Back should restore the News feed scroll position`,
    })
    .toBe(originalPosition.scrollY)
  await expect
    .poll(() => restoredNews.evaluate((link) => Math.round(link.getBoundingClientRect().top)))
    .toBe(originalPosition.top)

  await page.goForward()
  await expect(page).toHaveURL(selectedUrl.href)
  const restoredDetailHeading = page.getByRole("heading", {
    name: locale.articleTitle,
    exact: true,
  })
  await expect(restoredDetailHeading).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: `${language} Forward should restore the News article reading position`,
    })
    .toBe(originalDetailPosition.scrollY)
  await expect
    .poll(() =>
      restoredDetailHeading.evaluate((heading) => Math.round(heading.getBoundingClientRect().top))
    )
    .toBe(originalDetailPosition.top)

  await page.goBack()
  await expect(page).toHaveURL(listUrl)
  await expect(listHeading).toBeVisible()
  await expect(page.getByRole("button", { name: locale.categoryOption })).toHaveAttribute(
    "aria-current",
    "page"
  )
  const restoredNewsAfterForward = page.getByRole("link", { name: locale.articleTitle })
  await expect(restoredNewsAfterForward).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: `${language} Back after Forward should return to the same News feed position`,
    })
    .toBe(originalPosition.scrollY)
  await expect(restoredNewsAfterForward).toHaveAttribute("href", selectedHref ?? "")
  await expect
    .poll(() =>
      restoredNewsAfterForward.evaluate((link) => Math.round(link.getBoundingClientRect().top))
    )
    .toBe(originalPosition.top)
}

test("News feed Back/Forward restores the seeded article position in Russian and English", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")

  await switchLanguageThroughSettings(page, "en")
  await verifyLanguagePersistsAfterReload(page, "en")
  await verifyNewsHistoryForLanguage(page, "en")

  await switchLanguageThroughSettings(page, "ru")
  await verifyLanguagePersistsAfterReload(page, "ru")
  await verifyNewsHistoryForLanguage(page, "ru")
})
