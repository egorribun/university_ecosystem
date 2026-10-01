import { expect, test } from "./fixtures"
import type { Page } from "@playwright/test"

async function assertNoTechnicalErrorText(page: Page): Promise<void> {
  const visibleText = await page.locator("body").innerText()
  expect(visibleText).not.toMatch(
    /Internal Server Error|Traceback \(most recent call last\)|(?:TypeError|ReferenceError|SyntaxError):|at\s+\S+:\d+:\d+/u
  )
}

test("unknown public document returns the localized 404 shell after initialization", async ({
  page,
}) => {
  const unsafeRequests: string[] = []
  page.on("request", (request) => {
    if (!["GET", "HEAD"].includes(request.method())) {
      unsafeRequests.push(`${request.method()} ${new URL(request.url()).pathname}`)
    }
  })

  // The production SSR wrapper serves its static 404 document for unmatched
  // HTML paths. This route has no extension and cannot mutate application data.
  const response = await page.goto("/__live-e2e-missing-route-404__")
  expect(response).not.toBeNull()
  expect(response?.status()).toBe(404)
  expect(response?.headers()["content-language"]).toBe("ru")

  await expect(page.locator("html[data-not-found-page]")).toHaveAttribute("lang", "ru")
  await expect(page.getByRole("heading", { name: "Страница не найдена" })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.readyState)).toBe("complete")
  await assertNoTechnicalErrorText(page)

  const state = await page.evaluate(() => {
    const translations = [...document.querySelectorAll<HTMLElement>("[data-i18n]")].map((node) => ({
      key: node.getAttribute("data-i18n"),
      text: node.textContent?.trim() ?? "",
    }))
    const loadedResources = performance.getEntriesByType("resource").map((entry) => entry.name)

    return {
      shellPresent: document.querySelector("html[data-not-found-page]") !== null,
      readyState: document.readyState,
      language: document.documentElement.lang,
      pageTitle: document.title,
      translations,
      translatorLoaded: loadedResources.some(
        (resource) => new URL(resource).pathname === "/not-found-i18n.js"
      ),
    }
  })

  expect(state.shellPresent).toBe(true)
  expect(state.readyState).toBe("complete")
  expect(state.language).toBe("ru")
  expect(state.pageTitle).toBe("Страница не найдена — Экосистема ГУУ")
  expect(state.translatorLoaded).toBe(true)
  expect(state.translations).toHaveLength(4)
  for (const { key, text } of state.translations) {
    expect(text.trim()).not.toBe("")
    expect(text).not.toBe(key)
  }
  expect(unsafeRequests).toEqual([])
})

test("English browser resolves localized 404 content after initialization", async ({ browser }) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const context = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "en-US",
  })
  try {
    const page = await context.newPage()
    const unsafeRequests: string[] = []
    page.on("request", (request) => {
      if (!["GET", "HEAD"].includes(request.method())) {
        unsafeRequests.push(`${request.method()} ${new URL(request.url()).pathname}`)
      }
    })

    const response = await page.goto("/__live-e2e-missing-route-404-en__")
    expect(response).not.toBeNull()
    expect(response?.status()).toBe(404)

    const serverHtml = await response!.text()
    expect(serverHtml).toContain('<html lang="ru" data-not-found-page>')
    expect(serverHtml).toContain("<title>Страница не найдена — Экосистема ГУУ</title>")
    expect(serverHtml).toContain('data-i18n="notFound.title">Страница не найдена</h1>')
    expect(serverHtml).toContain("notFound.description")
    expect(serverHtml).not.toMatch(/>\s*notFound\.(?:title|description|home|login)\s*</u)

    await expect(page.locator("html[data-not-found-page]")).toHaveAttribute("lang", "en")
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.readyState)).toBe("complete")
    await assertNoTechnicalErrorText(page)

    const state = await page.evaluate(() => {
      const translations = [...document.querySelectorAll<HTMLElement>("[data-i18n]")].map(
        (node) => ({
          key: node.getAttribute("data-i18n"),
          text: node.textContent?.trim() ?? "",
        })
      )
      const loadedResources = performance.getEntriesByType("resource").map((entry) => entry.name)

      return {
        language: document.documentElement.lang,
        pageTitle: document.title,
        translations,
        translatorLoaded: loadedResources.some(
          (resource) => new URL(resource).pathname === "/not-found-i18n.js"
        ),
      }
    })

    expect(state.language).toBe("en")
    expect(state.pageTitle).toBe("Page not found — GUU Ecosystem")
    expect(state.translatorLoaded).toBe(true)
    expect(state.translations).toHaveLength(4)
    for (const { key, text } of state.translations) {
      expect(text.trim()).not.toBe("")
      expect(text).not.toBe(key)
    }
    expect(unsafeRequests).toEqual([])
  } finally {
    await context.close()
  }
})
