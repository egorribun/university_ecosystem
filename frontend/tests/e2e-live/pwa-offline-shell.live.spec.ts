import { expect, test } from "./fixtures"
import type { Page, Request } from "@playwright/test"

const CONTROLLER_CHANGE_COUNT = "__pwa_update_controllerchange_count"

function replacePrecacheRevision(
  workerSource: string,
  appBundlePath: string,
  revision: string
): string {
  const relativePath = appBundlePath.replace(/^\//u, "")
  const pathIndexes: number[] = []
  let searchFrom = 0
  while (true) {
    const index = workerSource.indexOf(relativePath, searchFrom)
    if (index < 0) break
    pathIndexes.push(index)
    searchFrom = index + relativePath.length
  }

  const entries = pathIndexes.flatMap((index) => {
    const start = workerSource.lastIndexOf("{", index)
    const end = workerSource.indexOf("}", index)
    if (start < 0 || end < 0) return []

    const entry = workerSource.slice(start, end + 1)
    const urlMatch = entry.match(/\burl\s*:\s*(["'])(.*?)\1/u)
    const manifestUrl = urlMatch?.[2]
    if (!manifestUrl) return []

    try {
      const manifestPath = new URL(manifestUrl, "https://pwa-update.invalid").pathname
      return manifestPath === appBundlePath ? [{ start, end, entry }] : []
    } catch {
      return []
    }
  })

  if (entries.length !== 1) {
    throw new Error("Expected exactly one precache entry for the selected app bundle")
  }

  const manifestEntry = entries[0]
  if (!manifestEntry) {
    throw new Error("Expected exactly one precache entry for the selected app bundle")
  }
  const { start, end, entry } = manifestEntry
  const updatedEntry = entry.replace(
    /(["']?revision["']?\s*:\s*)(?:null|["'][^"']*["'])/u,
    `$1${JSON.stringify(revision)}`
  )
  if (updatedEntry === entry) {
    throw new Error("The selected precache entry has no replaceable revision")
  }

  return `${workerSource.slice(0, start)}${updatedEntry}${workerSource.slice(end + 1)}`
}

function withoutStaleEntityHeaders(headers: Record<string, string>): Record<string, string> {
  const safeHeaders = { ...headers }
  delete safeHeaders["content-length"]
  delete safeHeaders["content-encoding"]
  delete safeHeaders["transfer-encoding"]
  return safeHeaders
}

async function readBundleCacheEvidence(page: Page, appBundlePath: string, marker: string) {
  return page.evaluate(
    async ({ path, expectedMarker }) => {
      const cacheNames = (await caches.keys()).filter((name) => name.startsWith("workbox-precache"))
      const entries: Array<{ cacheName: string; requestUrl: string; hasBuildMarker: boolean }> = []

      for (const cacheName of cacheNames) {
        const cache = await caches.open(cacheName)
        for (const request of await cache.keys()) {
          if (new URL(request.url).pathname !== path) continue
          const response = await cache.match(request)
          const body = response ? await response.text() : ""
          entries.push({
            cacheName,
            requestUrl: request.url,
            hasBuildMarker: body.includes(expectedMarker),
          })
        }
      }

      return entries
    },
    { path: appBundlePath, expectedMarker: marker }
  )
}

async function ensureServiceWorkerControlsPage(page: Page) {
  await page.evaluate(async () => {
    if (!("serviceWorker" in navigator)) {
      throw new Error("Service Worker support is required for the live offline-shell acceptance")
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

test.describe("PWA offline app shell on the live stack", () => {
  test("hydrates an unvisited public route from the precached shell while this context is offline", async ({
    page,
    context,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "the Service Worker offline navigation requires Chromium")

    // Only public pages are opened; the test never submits a form or invokes a
    // mutating endpoint. Loading the login page installs and warms the worker.
    await page.goto("/login", { waitUntil: "domcontentloaded" })
    await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible()
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await ensureServiceWorkerControlsPage(page)
    await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible()
    await page.waitForFunction(() => window.__APP_HYDRATED === true)

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

    expect(precacheEvidence.precacheNames.length).toBeGreaterThan(0)
    expect(
      precacheEvidence.bundlePaths.some((path) => precacheEvidence.precachedPaths.includes(path))
    ).toBe(true)

    // Disable the ordinary HTTP cache so only the real Service Worker can
    // supply the navigation shell and its application assets after disconnect.
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
      // /register was not opened online, so this verifies the unvisited-route
      // fallback plus lazy route code from the same real Workbox precache.
      const response = await page.goto("/register", { waitUntil: "domcontentloaded" })
      expect(response?.status()).toBe(200)
      await expect(page.locator("html")).toHaveAttribute("data-render-mode", "static-spa")
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.getByLabel("E-mail")).toBeVisible()
      await expect(page).toHaveURL(/\/register$/)
      expect(failedAssets).toEqual([])
      expect(offlineAssetRequests.some((path) => path.endsWith(".js"))).toBe(true)
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

  test("updates the active service worker online and serves the new precached bundle offline", async ({
    page,
    context,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "the Service Worker update acceptance requires Chromium")

    await page.addInitScript((storageKey) => {
      navigator.serviceWorker?.addEventListener("controllerchange", () => {
        const current = Number(sessionStorage.getItem(storageKey) ?? "0")
        sessionStorage.setItem(storageKey, String(current + 1))
      })
    }, CONTROLLER_CHANGE_COUNT)

    await page.goto("/login", { waitUntil: "domcontentloaded" })
    await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible()
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await ensureServiceWorkerControlsPage(page)
    await page.evaluate(
      (storageKey) => sessionStorage.removeItem(storageKey),
      CONTROLLER_CHANGE_COUNT
    )

    const initialEvidence = await page.evaluate(async () => {
      const bundlePaths = [...document.scripts]
        .map((script) => (script.src ? new URL(script.src).pathname : null))
        .filter((pathname): pathname is string => pathname?.endsWith(".js") ?? false)
      const precacheNames = (await caches.keys()).filter((name) =>
        name.startsWith("workbox-precache")
      )
      const precacheEntries = (
        await Promise.all(
          precacheNames.map(async (cacheName) => {
            const cache = await caches.open(cacheName)
            return (await cache.keys()).map((request) => ({
              cacheName,
              requestUrl: request.url,
              path: new URL(request.url).pathname,
            }))
          })
        )
      ).flat()
      const appBundlePath = bundlePaths.find((path) =>
        precacheEntries.some((entry) => entry.path === path)
      )

      return { appBundlePath: appBundlePath ?? null, precacheEntries }
    })

    expect(initialEvidence.appBundlePath).not.toBeNull()
    const appBundlePath = initialEvidence.appBundlePath!
    const oldBundleCacheKeys = initialEvidence.precacheEntries
      .filter((entry) => entry.path === appBundlePath)
      .map((entry) => entry.requestUrl)
    expect(oldBundleCacheKeys.length).toBeGreaterThan(0)

    const cdp = await context.newCDPSession(page)
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true })

    // First prove a public route can still load from the original precache while
    // offline. No account is created and no application API is intercepted.
    await context.setOffline(true)
    const offlineResponse = await page.goto("/forgot-password", { waitUntil: "domcontentloaded" })
    expect(offlineResponse?.status()).toBe(200)
    await expect(page.locator("html")).toHaveAttribute("data-render-mode", "static-spa")
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page).toHaveURL(/\/forgot-password$/u)
    await context.setOffline(false)

    const appOrigin = new URL(page.url()).origin
    const marker = `pwa-build-marker-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const updateRevision = `pwa-update-${marker}`
    let workerUpdateResponses = 0
    let bundleUpdateResponses = 0

    // These routes alter only the real worker script and one exact, already
    // precached, versioned app bundle. All other traffic continues upstream.
    await context.route("**/sw.js", async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== appOrigin || url.pathname !== "/sw.js") {
        await route.continue()
        return
      }

      const response = await route.fetch()
      const source = await response.text()
      const updatedSource = replacePrecacheRevision(source, appBundlePath, updateRevision)
      workerUpdateResponses += 1
      await route.fulfill({
        response,
        body: updatedSource,
        headers: withoutStaleEntityHeaders(response.headers()),
      })
    })

    await context.route("**/assets/**", async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== appOrigin || url.pathname !== appBundlePath) {
        await route.continue()
        return
      }

      const response = await route.fetch()
      const source = await response.text()
      const markerScript = `\n;(() => { const marker = document.createElement("output"); marker.id = "pwa-build-marker"; marker.dataset.pwaBuildMarker = ${JSON.stringify(marker)}; marker.textContent = ${JSON.stringify(marker)}; marker.style.cssText = "position:fixed;top:0;left:0;z-index:2147483647;background:#fff;color:#000;padding:4px"; document.body.append(marker); })();\n`
      bundleUpdateResponses += 1
      await route.fulfill({
        response,
        body: `${source}${markerScript}`,
        headers: withoutStaleEntityHeaders(response.headers()),
      })
    })

    try {
      await page.evaluate(async () => {
        const activeRegistration = await navigator.serviceWorker.ready
        await activeRegistration.update()
      })

      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page).toHaveURL(/\/forgot-password$/u)
      expect(workerUpdateResponses).toBeGreaterThan(0)
      expect(bundleUpdateResponses).toBeGreaterThan(0)
      expect(
        await page.evaluate(
          (storageKey) => Number(sessionStorage.getItem(storageKey) ?? "0"),
          CONTROLLER_CHANGE_COUNT
        )
      ).toBeGreaterThan(0)

      const newBundleCacheEntries = await readBundleCacheEvidence(page, appBundlePath, marker)
      const newBundleCacheKeys = newBundleCacheEntries.map((entry) => entry.requestUrl)
      expect(newBundleCacheEntries.some((entry) => entry.hasBuildMarker)).toBe(true)
      expect(
        newBundleCacheEntries.some(
          (entry) =>
            new URL(entry.requestUrl).searchParams.get("__WB_REVISION__") === updateRevision
        )
      ).toBe(true)
      for (const oldKey of oldBundleCacheKeys) {
        expect(newBundleCacheKeys).not.toContain(oldKey)
      }

      await context.setOffline(true)
      const updatedOfflineResponse = await page.goto("/forgot-password", {
        waitUntil: "domcontentloaded",
      })
      expect(updatedOfflineResponse?.status()).toBe(200)
      await expect(page.locator("html")).toHaveAttribute("data-render-mode", "static-spa")
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.locator("#pwa-build-marker")).toHaveAttribute(
        "data-pwa-build-marker",
        marker
      )
      await expect(page).toHaveURL(/\/forgot-password$/u)
    } finally {
      await context.unroute("**/sw.js")
      await context.unroute("**/assets/**")
      await context.setOffline(false)
      await cdp.detach()
    }
  })
})
