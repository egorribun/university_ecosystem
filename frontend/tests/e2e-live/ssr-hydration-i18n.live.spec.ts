import { type BrowserContext, type Page } from "@playwright/test"
import { JSDOM } from "jsdom"
import { extractSeoMetadata, normalizeMetadataText } from "./seo-metadata.mjs"
import { matchesNewsSearchLocale } from "./ssr-news-locale.mjs"
import enActivity from "../../src/i18n/locales/en/activity.json" with { type: "json" }
import enDashboard from "../../src/i18n/locales/en/dashboard.json" with { type: "json" }
import enNavigation from "../../src/i18n/locales/en/navigation.json" with { type: "json" }
import ruDashboard from "../../src/i18n/locales/ru/dashboard.json" with { type: "json" }
import ruActivity from "../../src/i18n/locales/ru/activity.json" with { type: "json" }
import ruNavigation from "../../src/i18n/locales/ru/navigation.json" with { type: "json" }
import enNews from "../../src/i18n/locales/en/news.json" with { type: "json" }
import ruNews from "../../src/i18n/locales/ru/news.json" with { type: "json" }
import { expect, loginAs, test } from "./fixtures"

type Language = "ru" | "en"
type TitleLandmark = "activity" | "dashboard" | "news"

const PAGE_TITLE_CATALOGS = {
  activity: { en: enActivity.title, ru: ruActivity.title },
  dashboard: { en: enDashboard.pageTitle, ru: ruDashboard.pageTitle },
  news: { en: enNews.pageTitle, ru: ruNews.pageTitle },
} satisfies Record<TitleLandmark, Record<Language, string>>

const NEWS_SEARCH_PLACEHOLDER_CATALOGS = {
  en: enNews.search.placeholder,
  ru: ruNews.search.placeholder,
} satisfies Record<Language, string>

const PAGE_DESCRIPTION_CATALOGS = {
  activity: { en: enActivity.pageDescription, ru: ruActivity.pageDescription },
  dashboard: { en: enNavigation.brandDescription, ru: ruNavigation.brandDescription },
  news: { en: enNews.pageDescription, ru: ruNews.pageDescription },
} satisfies Record<TitleLandmark, Record<Language, string>>

const PAGE_SOCIAL_DESCRIPTION_CATALOGS = {
  activity: { en: enActivity.pageDescription, ru: ruActivity.pageDescription },
  dashboard: { en: enNavigation.socialDescription, ru: ruNavigation.socialDescription },
  news: { en: enNews.pageDescription, ru: ruNews.pageDescription },
} satisfies Record<TitleLandmark, Record<Language, string>>

const ROOT_BRAND_CATALOGS = {
  en: {
    title: enNavigation.brandName,
    description: enNavigation.brandDescription,
    socialDescription: enNavigation.socialDescription,
  },
  ru: {
    title: ruNavigation.brandName,
    description: ruNavigation.brandDescription,
    socialDescription: ruNavigation.socialDescription,
  },
} satisfies Record<Language, { title: string; description: string; socialDescription: string }>

function expectedRootHeadSnapshot(language: Language) {
  const { title, description, socialDescription } = ROOT_BRAND_CATALOGS[language]

  return {
    title,
    titleCount: 1,
    metaTitle: null,
    description,
    descriptionCount: 1,
    ogType: "website",
    ogTitle: title,
    ogDescription: socialDescription,
    ogImage: "/icon-512.png",
    twitterCard: "summary_large_image",
    twitterTitle: title,
    twitterDescription: socialDescription,
    twitterImage: "/icon-512.png",
    seoMetaCounts: {
      'meta[name="title"]': 0,
      'meta[name="description"]': 1,
      'meta[property="og:type"]': 1,
      'meta[property="og:title"]': 1,
      'meta[property="og:description"]': 1,
      'meta[property="og:image"]': 1,
      'meta[name="twitter:card"]': 1,
      'meta[name="twitter:title"]': 1,
      'meta[name="twitter:description"]': 1,
      'meta[name="twitter:image"]': 1,
    },
  }
}

function expectedDocumentTitle(language: Language, landmark: TitleLandmark): string {
  const localizedTitle = PAGE_TITLE_CATALOGS[landmark][language]
  if (typeof localizedTitle !== "string" || localizedTitle.trim() === "") {
    throw new Error("Missing " + language + " " + landmark + " page-title resource")
  }
  return normalizeMetadataText(localizedTitle + " | University Ecosystem")
}

function readDocumentTitle(markup: string | null): string | null {
  return extractSeoMetadata(markup)?.title ?? null
}

function readNewsSearchPlaceholder(markup: string | null): string | null {
  if (markup === null) return null
  const root = new JSDOM(markup).window.document.querySelector("#root")
  return (
    root
      ?.querySelector<HTMLInputElement>(".news-theme header input[placeholder]")
      ?.getAttribute("placeholder") ?? null
  )
}

function readHeadSnapshot(markup: string | null) {
  return extractSeoMetadata(markup)
}

function expectedPageHeadSnapshot(language: Language, landmark: TitleLandmark) {
  const title = expectedDocumentTitle(language, landmark)
  const description = PAGE_DESCRIPTION_CATALOGS[landmark][language]
  const socialDescription = PAGE_SOCIAL_DESCRIPTION_CATALOGS[landmark][language]

  return {
    title,
    titleCount: 1,
    metaTitle: title,
    description,
    descriptionCount: 1,
    ogType: "website",
    ogTitle: title,
    ogDescription: socialDescription,
    ogImage: "/icon-512.png",
    twitterCard: "summary_large_image",
    twitterTitle: title,
    twitterDescription: socialDescription,
    twitterImage: "/icon-512.png",
    seoMetaCounts: Object.fromEntries(
      [
        'meta[name="title"]',
        'meta[name="description"]',
        'meta[property="og:type"]',
        'meta[property="og:title"]',
        'meta[property="og:description"]',
        'meta[property="og:image"]',
        'meta[name="twitter:card"]',
        'meta[name="twitter:title"]',
        'meta[name="twitter:description"]',
        'meta[name="twitter:image"]',
      ].map((selector) => [selector, 1])
    ),
  }
}

async function assertSingleClientHead(
  page: Page,
  language: Language,
  landmark: TitleLandmark,
  title: string,
  description: string
): Promise<void> {
  await expect(page.locator("head title")).toHaveCount(1)
  await expect(page.locator("head title")).toHaveText(title)
  await expect(page.locator('head meta[name="description"]')).toHaveCount(1)
  await expect(page.locator('head meta[name="description"]')).toHaveAttribute(
    "content",
    description
  )
  const metadata = [
    ['meta[name="title"]', title],
    ['meta[name="description"]', description],
    ['meta[property="og:type"]', "website"],
    ['meta[property="og:title"]', title],
    ['meta[property="og:description"]', PAGE_SOCIAL_DESCRIPTION_CATALOGS[landmark][language]],
    ['meta[property="og:image"]', "/icon-512.png"],
    ['meta[name="twitter:card"]', "summary_large_image"],
    ['meta[name="twitter:title"]', title],
    ['meta[name="twitter:description"]', PAGE_SOCIAL_DESCRIPTION_CATALOGS[landmark][language]],
    ['meta[name="twitter:image"]', "/icon-512.png"],
  ] as const
  for (const [selector, content] of metadata) {
    const locator = page.locator(`head ${selector}`)
    await expect(locator).toHaveCount(1)
    await expect(locator).toHaveAttribute("content", content)
  }
}

async function assertSingleRootClientHead(page: Page, language: Language): Promise<void> {
  const headMarkup = await page.locator("head").evaluate((head) => head.outerHTML)
  expect(extractSeoMetadata(headMarkup)).toEqual(expectedRootHeadSnapshot(language))
}

const HYDRATION_DIAGNOSTIC =
  /hydration|hydrated|server(?:-rendered)? html|text content does not match|expected server html|react error #(?:418|423|425)/iu

function hasRawTranslationKey(markup: string | null): boolean {
  if (markup === null) return false

  // Parse captured server/client markup outside the CSP-constrained page. JSDOM
  // does not execute embedded scripts unless explicitly configured to do so.
  const root = new JSDOM(markup).window.document.querySelector("#root")
  if (!root) return false

  const rawNamespaceKey = /\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu
  const visibleText = root.textContent ?? ""
  const accessibleText = Array.from(
    root.querySelectorAll<HTMLElement>(
      "[aria-label], [aria-description], [title], [placeholder], [alt], [value], [aria-valuetext]"
    )
  )
    .flatMap((element) => [
      element.getAttribute("aria-label"),
      element.getAttribute("aria-description"),
      element.getAttribute("title"),
      element.getAttribute("placeholder"),
      element.getAttribute("alt"),
      element.getAttribute("value"),
      element.getAttribute("aria-valuetext"),
    ])
    .filter((value): value is string => value !== null)
    .join(" ")

  return rawNamespaceKey.test(`${visibleText} ${accessibleText}`)
}

async function inspectRawTranslationKeys(page: Page, serverMarkup: string | null) {
  const clientMarkup = await page.evaluate(() => document.querySelector("#root")?.outerHTML ?? null)
  return {
    server: serverMarkup === null ? null : hasRawTranslationKey(serverMarkup),
    client: hasRawTranslationKey(clientMarkup),
  }
}

async function assertDashboardHydratesAndNavigatesInLanguage(
  page: Page,
  context: BrowserContext,
  language: Language
): Promise<void> {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  // The demo student is synthetic and this acceptance only reads UI content.
  // Locale is isolated to this browser context; no account or application data changes.
  await loginAs(page, "student")
  await context.addCookies([{ name: "ue:language", value: language, url: liveBaseUrl }])
  await page.addInitScript((selectedLanguage: Language) => {
    window.localStorage.setItem("ue:language", selectedLanguage)
  }, language)

  let hydrationDiagnostics = 0
  let uncaughtPageErrors = 0
  const onConsole = (message: import("@playwright/test").ConsoleMessage) => {
    if (
      (message.type() === "warning" || message.type() === "error") &&
      HYDRATION_DIAGNOSTIC.test(message.text())
    ) {
      hydrationDiagnostics += 1
    }
  }
  const onPageError = () => {
    uncaughtPageErrors += 1
  }
  page.on("console", onConsole)
  page.on("pageerror", onPageError)

  try {
    // A document navigation exercises server rendering; SPA navigation alone
    // would miss the server cookie → <html lang> boundary.
    const response = await page.goto("/dashboard", {
      waitUntil: "domcontentloaded",
    })
    expect(response?.status()).toBe(200)
    expect(response?.headers()["content-type"] ?? "").toContain("text/html")

    const serverMarkup = await response?.text()
    expect(serverMarkup).toBeTruthy()
    const serverLanguage = serverMarkup?.match(/<html\b[^>]*\blang=["'](ru|en)["']/u)?.[1]
    expect(serverLanguage).toBe(language)
    expect(readDocumentTitle(serverMarkup ?? null)).toBe(
      expectedDocumentTitle(language, "dashboard")
    )
    expect(readHeadSnapshot(serverMarkup ?? null)).toMatchObject(
      expectedPageHeadSnapshot(language, "dashboard")
    )
    expect(serverMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await expect(page.getByRole("main")).toBeVisible()
    expect(normalizeMetadataText(await page.title())).toBe(
      expectedDocumentTitle(language, "dashboard")
    )
    await assertSingleClientHead(
      page,
      language,
      "dashboard",
      expectedDocumentTitle(language, "dashboard"),
      PAGE_DESCRIPTION_CATALOGS.dashboard[language]
    )

    const rawTranslationKeys = await inspectRawTranslationKeys(page, serverMarkup ?? "")
    expect(rawTranslationKeys.server).toBe(false)
    expect(rawTranslationKeys.client).toBe(false)
    expect(hydrationDiagnostics).toBe(0)
    expect(uncaughtPageErrors).toBe(0)

    // Exercise a real client-side route transition on both projects and
    // locales; this is navigation through the rendered app, not a mocked API.
    const newsLink = page.locator('a[href="/news"]:visible').first()
    await expect(newsLink).toBeVisible()
    await newsLink.click()
    await expect(page).toHaveURL(/\/news$/u)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    const expectedNewsHeading = language === "en" ? "University news" : "Новости университета"
    await expect(
      page.getByRole("heading", { name: expectedNewsHeading, exact: true })
    ).toBeVisible()
    const spaNewsMarkup = await page.locator("#root").evaluate((root) => root.outerHTML)
    expect(matchesNewsSearchLocale(spaNewsMarkup, NEWS_SEARCH_PLACEHOLDER_CATALOGS[language])).toBe(
      true
    )

    expect(normalizeMetadataText(await page.title())).toBe(expectedDocumentTitle(language, "news"))
    await assertSingleClientHead(
      page,
      language,
      "news",
      expectedDocumentTitle(language, "news"),
      PAGE_DESCRIPTION_CATALOGS.news[language]
    )
    const spaTranslationKeys = await inspectRawTranslationKeys(page, null)
    expect(spaTranslationKeys.client).toBe(false)
    expect(hydrationDiagnostics).toBe(0)
    expect(uncaughtPageErrors).toBe(0)

    // A full document reload of the destination proves its server-rendered
    // locale and markup agree with the same browser context as well.
    const newsResponse = await page.reload({ waitUntil: "domcontentloaded" })
    expect(newsResponse?.status()).toBe(200)
    expect(newsResponse?.headers()["content-type"] ?? "").toContain("text/html")
    const newsServerMarkup = await newsResponse?.text()
    expect(newsServerMarkup).toBeTruthy()
    expect(readNewsSearchPlaceholder(newsServerMarkup ?? null)).toBe(
      NEWS_SEARCH_PLACEHOLDER_CATALOGS[language]
    )
    expect(
      matchesNewsSearchLocale(newsServerMarkup ?? null, NEWS_SEARCH_PLACEHOLDER_CATALOGS[language])
    ).toBe(true)
    const newsServerLanguage = newsServerMarkup?.match(/<html\b[^>]*\blang=["'](ru|en)["']/u)?.[1]
    expect(newsServerLanguage).toBe(language)
    expect(readDocumentTitle(newsServerMarkup ?? null)).toBe(
      expectedDocumentTitle(language, "news")
    )
    expect(readHeadSnapshot(newsServerMarkup ?? null)).toMatchObject(
      expectedPageHeadSnapshot(language, "news")
    )
    expect(newsServerMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await expect(
      page.getByRole("heading", { name: expectedNewsHeading, exact: true })
    ).toBeVisible()
    const hydratedNewsMarkup = await page.locator("#root").evaluate((root) => root.outerHTML)
    expect(
      matchesNewsSearchLocale(hydratedNewsMarkup, NEWS_SEARCH_PLACEHOLDER_CATALOGS[language])
    ).toBe(true)
    expect(normalizeMetadataText(await page.title())).toBe(expectedDocumentTitle(language, "news"))
    await assertSingleClientHead(
      page,
      language,
      "news",
      expectedDocumentTitle(language, "news"),
      PAGE_DESCRIPTION_CATALOGS.news[language]
    )
    const newsRawTranslationKeys = await inspectRawTranslationKeys(page, newsServerMarkup ?? "")
    expect(newsRawTranslationKeys.server).toBe(false)
    expect(newsRawTranslationKeys.client).toBe(false)
    expect(hydrationDiagnostics).toBe(0)
    expect(uncaughtPageErrors).toBe(0)

    // The data-only route must remove the root fallback during an actual SPA
    // navigation. The reload below separately verifies the SSR fallback and
    // its replacement during hydration.
    const activityLink = page.locator('a[href="/activity"]:visible').first()
    await expect(activityLink).toBeVisible()
    await activityLink.click()
    await expect(page).toHaveURL(/\/activity$/u)
    await assertSingleClientHead(
      page,
      language,
      "activity",
      expectedDocumentTitle(language, "activity"),
      PAGE_DESCRIPTION_CATALOGS.activity[language]
    )

    // /activity is a data-only SSR route: the server must retain its root
    // fallback metadata, and client hydration must replace it with the page's
    // localized metadata without leaving duplicate head entries behind.
    const activityResponse = await page.goto("/activity", { waitUntil: "domcontentloaded" })
    expect(activityResponse?.status()).toBe(200)
    const activityServerMarkup = await activityResponse?.text()
    expect(readHeadSnapshot(activityServerMarkup ?? null)).toEqual(
      expectedRootHeadSnapshot(language)
    )
    expect(activityServerMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await assertSingleClientHead(
      page,
      language,
      "activity",
      expectedDocumentTitle(language, "activity"),
      PAGE_DESCRIPTION_CATALOGS.activity[language]
    )
  } finally {
    page.off("console", onConsole)
    page.off("pageerror", onPageError)
  }
}

test("Russian dashboard SSR hydrates and preserves i18n across News navigation", async ({
  page,
  context,
}) => {
  await assertDashboardHydratesAndNavigatesInLanguage(page, context, "ru")
})

test("English dashboard SSR hydrates and preserves i18n across News navigation", async ({
  page,
  context,
}) => {
  await assertDashboardHydratesAndNavigatesInLanguage(page, context, "en")
})

test("a public route retains one localized root metadata fallback", async ({ page, context }) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  await context.addCookies([{ name: "ue:language", value: "en", url: liveBaseUrl }])
  const response = await page.goto("/login", { waitUntil: "domcontentloaded" })
  expect(response?.status()).toBe(200)
  const serverMarkup = await response?.text()
  expect(readHeadSnapshot(serverMarkup ?? null)).toEqual(expectedRootHeadSnapshot("en"))

  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await assertSingleRootClientHead(page, "en")
})
