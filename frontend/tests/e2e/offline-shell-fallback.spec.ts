import type { Request as PlaywrightRequest } from "@playwright/test"
import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"

const ensureControlledByServiceWorker = async (page: Page) => {
  await page.waitForLoadState("networkidle")
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })

  let controlled = await page.evaluate(() => Boolean(navigator.serviceWorker.controller))
  if (!controlled) {
    await page.reload({ waitUntil: "networkidle" })
    controlled = await page.evaluate(() => Boolean(navigator.serviceWorker.controller))
  }

  expect(controlled).toBeTruthy()
}

test.describe("PWA precached shell fallback", () => {
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "This acceptance contract requires Chromium Service Worker and CDP support."
  )

  test("hydrates a fresh deep link from the precached shell while offline", async ({
    page,
    context,
  }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)
    await ensureControlledByServiceWorker(page)

    const precacheEvidence = await page.evaluate(async () => {
      const bundlePaths = [...document.scripts]
        .map((script) => (script.src ? new URL(script.src).pathname : null))
        .filter((pathname): pathname is string => pathname?.endsWith(".js") ?? false)
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

      return { bundlePaths, precacheNames, precachedPaths }
    })

    expect(precacheEvidence.bundlePaths.length).toBeGreaterThan(0)
    expect(precacheEvidence.precacheNames.length).toBeGreaterThan(0)
    expect(
      precacheEvidence.bundlePaths.some((path) => precacheEvidence.precachedPaths.includes(path))
    ).toBe(true)

    // Keep browser HTTP cache from satisfying the navigation's bundle requests:
    // the real service worker's Workbox precache must provide the current app code.
    const cdp = await context.newCDPSession(page)
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true })

    const failedBundles: string[] = []
    const recordBundleFailure = (request: PlaywrightRequest) => {
      if (["script", "stylesheet"].includes(request.resourceType())) {
        failedBundles.push(request.url())
      }
    }
    page.on("requestfailed", recordBundleFailure)

    await context.setOffline(true)
    try {
      // /events has not been opened online in this context; the navigation must
      // fall back to the canonical static shell and load its precached JS.
      const response = await page.goto("/events", { waitUntil: "domcontentloaded" })
      expect(response?.status()).toBe(200)
      await expect(page.locator("html")).toHaveAttribute("data-render-mode", "static-spa")
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.getByRole("heading", { name: "Мероприятия" })).toBeVisible()
      expect(failedBundles).toEqual([])
    } finally {
      page.off("requestfailed", recordBundleFailure)
      await context.setOffline(false)
      await cdp.detach()
    }
  })
})
