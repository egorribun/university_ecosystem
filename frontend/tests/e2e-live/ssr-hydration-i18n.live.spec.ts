import { expect, test, type BrowserContext, type Page } from "@playwright/test"
import { loginAs } from "./fixtures"

type Language = "ru" | "en"

const HYDRATION_DIAGNOSTIC =
  /hydration|hydrated|server(?:-rendered)? html|text content does not match|expected server html|react error #(?:418|423|425)/iu

async function inspectRawTranslationKeys(page: Page, serverMarkup: string | null) {
  return page.evaluate((markup) => {
    const rawNamespaceKey = /\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu
    const hasRawTranslationKey = (root: ParentNode | null) => {
      if (!root) return false

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

    let server: boolean | null = null
    if (markup !== null) {
      const serverDocument = new DOMParser().parseFromString(markup, "text/html")
      server = hasRawTranslationKey(serverDocument.querySelector("#root"))
    }

    return {
      server,
      client: hasRawTranslationKey(document.querySelector("#root")),
    }
  }, serverMarkup)
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
    const response = await page.goto("/dashboard", { waitUntil: "domcontentloaded" })
    expect(response?.status()).toBe(200)
    expect(response?.headers()["content-type"] ?? "").toContain("text/html")

    const serverMarkup = await response?.text()
    expect(serverMarkup).toBeTruthy()
    const serverLanguage = serverMarkup?.match(/<html\b[^>]*\blang=["'](ru|en)["']/u)?.[1]
    expect(serverLanguage).toBe(language)
    expect(serverMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await expect(page.getByRole("main")).toBeVisible()

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
    const newsServerLanguage = newsServerMarkup?.match(/<html\b[^>]*\blang=["'](ru|en)["']/u)?.[1]
    expect(newsServerLanguage).toBe(language)
    expect(newsServerMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await expect(
      page.getByRole("heading", { name: expectedNewsHeading, exact: true })
    ).toBeVisible()
    const newsRawTranslationKeys = await inspectRawTranslationKeys(page, newsServerMarkup ?? "")
    expect(newsRawTranslationKeys.server).toBe(false)
    expect(newsRawTranslationKeys.client).toBe(false)
    expect(hydrationDiagnostics).toBe(0)
    expect(uncaughtPageErrors).toBe(0)
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
