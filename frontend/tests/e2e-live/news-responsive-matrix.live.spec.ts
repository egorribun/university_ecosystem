import { expect, loginAs, test } from "./fixtures"
import type { Locator, Page } from "@playwright/test"

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

const WIDTHS = [360, 390, 768, 1024, 1440] as const
const VIEWPORT_HEIGHT = 900
const NEWS_VIEWPORT_DIAGNOSTIC_LIMIT = 20
const NEWS_VIEWPORT_DIAGNOSTIC_PIXEL_LIMIT = 999_999
const emittedNewsViewportTuples = new Set<string>()

function boundedNewsViewportPixel(value: number): number | undefined {
  if (!Number.isFinite(value)) return undefined
  const rounded = Math.round(value)
  const bounded = Math.max(
    -NEWS_VIEWPORT_DIAGNOSTIC_PIXEL_LIMIT,
    Math.min(NEWS_VIEWPORT_DIAGNOSTIC_PIXEL_LIMIT, rounded)
  )
  return Number.isSafeInteger(bounded) ? bounded : undefined
}

async function reportNewsHeadingViewport(
  page: Page,
  heading: Locator,
  language: keyof typeof NEWS_LOCALIZATIONS,
  width: (typeof WIDTHS)[number]
): Promise<void> {
  try {
    const project = test.info().project.name
    if ((project !== "desktop" && project !== "mobile") || !WIDTHS.includes(width)) {
      return
    }

    const tuple = project + "/" + language + "/" + width
    if (
      emittedNewsViewportTuples.has(tuple) ||
      emittedNewsViewportTuples.size >= NEWS_VIEWPORT_DIAGNOSTIC_LIMIT
    ) {
      return
    }

    const [bounds, viewport] = await Promise.all([
      heading.boundingBox(),
      page.evaluate(() => ({ height: window.innerHeight, scrollY: window.scrollY })),
    ])
    if (bounds === null) return

    const values = {
      viewportHeight: boundedNewsViewportPixel(viewport.height),
      scrollY: boundedNewsViewportPixel(viewport.scrollY),
      top: boundedNewsViewportPixel(bounds.y),
      bottom: boundedNewsViewportPixel(bounds.y + bounds.height),
      left: boundedNewsViewportPixel(bounds.x),
      right: boundedNewsViewportPixel(bounds.x + bounds.width),
    }
    if (Object.values(values).some((value) => value === undefined)) return

    process.stdout.write(
      "UE_LIVE_NEWS_VIEWPORT_V1 project=" +
        project +
        " language=" +
        language +
        " width=" +
        width +
        " viewportHeight=" +
        values.viewportHeight +
        " scrollY=" +
        values.scrollY +
        " top=" +
        values.top +
        " bottom=" +
        values.bottom +
        " left=" +
        values.left +
        " right=" +
        values.right +
        "\n"
    )
    emittedNewsViewportTuples.add(tuple)
  } catch {
    // Diagnostics must never replace the existing viewport assertion.
  }
}

test.use({ trace: "off", screenshot: "off", video: "off" })

async function selectLanguageThroughSettings(
  page: Page,
  language: keyof typeof NEWS_LOCALIZATIONS
) {
  const locale = NEWS_LOCALIZATIONS[language]
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

  const option = page.getByRole("radio", { name: locale.languageOption })
  await expect(option).toBeVisible()
  await option.locator("xpath=ancestor::label").click()
  await expect(option).toBeChecked()
  await expect(page.locator("html")).toHaveAttribute("lang", locale.language)
}

async function waitForLayout(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    )
  })
}

async function verifyNewsWidths(
  page: Page,
  language: keyof typeof NEWS_LOCALIZATIONS
): Promise<void> {
  const locale = NEWS_LOCALIZATIONS[language]
  await page.goto("/news")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/news")
  await expect(page.locator("html")).toHaveAttribute("lang", locale.language)
  await expect(page.getByRole("heading", { name: locale.listHeading, exact: true })).toBeVisible()
  await waitForLayout(page)

  const scienceFilter = page.getByRole("button", { name: locale.categoryOption })
  await scienceFilter.click()
  await expect.poll(() => new URL(page.url()).searchParams.get("cat")).toBe("science")
  await expect(scienceFilter).toHaveAttribute("aria-current", "page")
  await waitForLayout(page)

  const heading = page.getByRole("heading", { name: locale.listHeading, exact: true })
  const seededArticle = page.getByRole("link", { name: locale.articleTitle })
  await expect(seededArticle).toBeVisible()

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: VIEWPORT_HEIGHT })
    await waitForLayout(page)
    await expect(page.locator("html")).toHaveAttribute("lang", locale.language)
    await expect(heading).toBeVisible()
    await reportNewsHeadingViewport(page, heading, language, width)
    await expect(heading).toBeInViewport()
    await expect(seededArticle).toBeVisible()

    const metrics = await page.evaluate(() => {
      const main = document.querySelector<HTMLElement>("#main-content")
      if (!main) throw new Error("main content landmark is missing")
      const rect = main.getBoundingClientRect()
      return {
        viewportWidth: window.innerWidth,
        documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        mainLeft: rect.left,
        mainRight: rect.right,
      }
    })
    const articleBounds = await seededArticle.boundingBox()

    expect(metrics.viewportWidth, `${language} viewport width`).toBe(width)
    expect(
      metrics.documentWidth,
      `${language} document overflow at ${width}px`
    ).toBeLessThanOrEqual(width + 1)
    expect(
      metrics.mainLeft,
      `${language} main content starts in viewport at ${width}px`
    ).toBeGreaterThanOrEqual(0)
    expect(
      metrics.mainRight,
      `${language} main content ends in viewport at ${width}px`
    ).toBeLessThanOrEqual(width + 1)
    expect(articleBounds, `${language} seeded article is rendered at ${width}px`).not.toBeNull()
    if (articleBounds) {
      expect(
        articleBounds.x,
        `${language} article starts in viewport at ${width}px`
      ).toBeGreaterThanOrEqual(0)
      expect(
        articleBounds.x + articleBounds.width,
        `${language} article ends in viewport at ${width}px`
      ).toBeLessThanOrEqual(width + 1)
    }
  }
}

test("seeded News core content reflows without page overflow in RU and EN", async ({ page }) => {
  await loginAs(page, "student")

  for (const language of ["ru", "en"] as const) {
    await selectLanguageThroughSettings(page, language)
    await verifyNewsWidths(page, language)
  }
})
