import { expect, test } from "./fixtures"
import type { Page, Request } from "@playwright/test"

async function ensureServiceWorkerControlsPage(page: Page) {
  await page.evaluate(async () => {
    if (!("serviceWorker" in navigator)) {
      throw new Error("Service Worker support is required for offline locale acceptance")
    }
    await navigator.serviceWorker.ready
  })

  if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller)))) {
    await page.reload({ waitUntil: "domcontentloaded" })
  }

  await expect
    .poll(() => page.evaluate(() => Boolean(navigator.serviceWorker?.controller)))
    .toBe(true)
}

type Language = "en" | "ru"
const offlineLocaleCopy: Record<
  Language,
  { signIn: string; signUp: string; name: string; title: string }
> = {
  en: { signIn: "Sign in", signUp: "Sign up", name: "Name", title: "GUU Ecosystem" },
  ru: { signIn: "Вход", signUp: "Регистрация", name: "Имя", title: "Экосистема ГУУ" },
}

for (const language of ["en", "ru"] as const) {
  test(`the real offline app shell preserves ${language} i18n for an unvisited route`, async ({
    page,
    context,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "The real Service Worker fallback requires Chromium")

    const liveBaseUrl = process.env.LIVE_BASE_URL
    if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")
    const copy = offlineLocaleCopy[language]

    // Locale is an isolated browser preference. The app and worker remain real;
    // the shell must honor the same cookie/localStorage values after disconnect.
    await context.addCookies([{ name: "ue:language", value: language, url: liveBaseUrl }])
    await page.addInitScript((selectedLanguage: Language) => {
      window.localStorage.setItem("ue:language", selectedLanguage)
    }, language)

    await page.goto("/login", { waitUntil: "domcontentloaded" })
    await expect(page.getByRole("heading", { name: copy.signIn })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("lang", language)
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await ensureServiceWorkerControlsPage(page)

    const precacheEvidence = await page.evaluate(async () => {
      const precacheNames = (await caches.keys()).filter((name) =>
        name.startsWith("workbox-precache")
      )
      const precachedPaths = (
        await Promise.all(
          precacheNames.map(async (name) => {
            const cache = await caches.open(name)
            return (await cache.keys()).map((request) => new URL(request.url).pathname)
          })
        )
      ).flat()

      return { precacheNames, precachedPaths }
    })
    expect(precacheEvidence.precacheNames.length).toBeGreaterThan(0)

    const cdp = await context.newCDPSession(page)
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true })
    const failedAssets: string[] = []
    const offlineAssetRequests: string[] = []
    const appOrigin = new URL(page.url()).origin
    const recordOfflineAssetRequest = (request: Request) => {
      const url = new URL(request.url())
      if (url.origin === appOrigin && ["script", "stylesheet"].includes(request.resourceType())) {
        offlineAssetRequests.push(url.pathname)
      }
    }
    const recordFailedAsset = (request: Request) => {
      if (["script", "stylesheet"].includes(request.resourceType())) {
        failedAssets.push(new URL(request.url()).pathname)
      }
    }
    page.on("request", recordOfflineAssetRequest)
    page.on("requestfailed", recordFailedAsset)

    await context.setOffline(true)
    try {
      const response = await page.goto("/register", { waitUntil: "domcontentloaded" })
      expect(response?.status()).toBe(200)
      await expect(page.locator("html")).toHaveAttribute("data-render-mode", "static-spa")
      await page.waitForFunction(() => window.__APP_HYDRATED === true)

      await expect(page.locator("html")).toHaveAttribute("lang", language)
      await expect(page.getByRole("heading", { name: copy.signUp })).toBeVisible()
      await expect(page.getByRole("textbox", { name: copy.name })).toBeVisible()
      await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible()
      expect(await page.title()).toBe(copy.title)

      const visibleText = await page.locator("body").innerText()
      expect(visibleText).not.toMatch(/\b(?:auth|common|system):[\w.]+/u)
      expect(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
      expect(failedAssets).toEqual([])
      expect(offlineAssetRequests.length).toBeGreaterThan(0)
      expect(
        offlineAssetRequests.every((path) => precacheEvidence.precachedPaths.includes(path))
      ).toBe(true)
    } finally {
      page.off("request", recordOfflineAssetRequest)
      page.off("requestfailed", recordFailedAsset)
      await context.setOffline(false)
      await cdp.detach()
    }
  })
}
