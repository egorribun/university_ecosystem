import { expect, loginAs, test } from "./fixtures"

type Language = "ru" | "en"

const HYDRATION_DIAGNOSTIC =
  /hydration|hydrated|server(?:-rendered)? html|text content does not match|expected server html|react error #(?:418|423|425)/iu

test.use({ trace: "off", screenshot: "off", video: "off" })

async function assertScheduleHydratesInLanguage(
  page: import("@playwright/test").Page,
  context: import("@playwright/test").BrowserContext,
  language: Language
): Promise<void> {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

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
    const response = await page.goto("/schedule", { waitUntil: "domcontentloaded" })
    expect(response?.status()).toBe(200)
    await expect.poll(() => new URL(page.url()).pathname).toBe("/schedule")
    expect(response?.headers()["content-type"] ?? "").toContain("text/html")

    const serverMarkup = await response?.text()
    const serverLanguage = serverMarkup?.match(/<html\b[^>]*\blang=["'](ru|en)["']/u)?.[1]
    expect(serverLanguage).toBe(language)
    expect(serverMarkup?.includes('data-ssr-auth="authenticated:student"')).toBe(true)

    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await expect(page.getByRole("main")).toBeVisible()
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    const scheduleViewName = language === "ru" ? "Расписание" : "Schedule"
    const scheduleView = page
      .getByRole("grid", { name: scheduleViewName, exact: true })
      .or(page.getByRole("tablist", { name: scheduleViewName, exact: true }))
    await expect(scheduleView).toBeVisible()

    const rawTranslationKey = await page.locator("#root").evaluate((root) => {
      const rawNamespaceKey = /\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu
      const visibleText = root.textContent ?? ""
      const accessibleText = Array.from(
        root.querySelectorAll<HTMLElement>("[aria-label], [title], [placeholder]")
      )
        .flatMap((element) => [
          element.getAttribute("aria-label"),
          element.getAttribute("title"),
          element.getAttribute("placeholder"),
        ])
        .filter((value): value is string => value !== null)
        .join(" ")

      return rawNamespaceKey.test(`${visibleText} ${accessibleText}`)
    })

    expect(rawTranslationKey).toBe(false)
    expect(hydrationDiagnostics).toBe(0)
    expect(uncaughtPageErrors).toBe(0)
  } finally {
    page.off("console", onConsole)
    page.off("pageerror", onPageError)
  }
}

test("Russian schedule SSR markup hydrates without raw i18n keys", async ({ page, context }) => {
  await assertScheduleHydratesInLanguage(page, context, "ru")
})

test("English schedule SSR markup hydrates without raw i18n keys", async ({ page, context }) => {
  await assertScheduleHydratesInLanguage(page, context, "en")
})
