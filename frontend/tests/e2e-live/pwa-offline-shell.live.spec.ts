import { expect, ownedSessionOrigin, test } from "./fixtures"
import type { Page, Request } from "@playwright/test"
import { startPwaUpdateProxy } from "./pwa-update-proxy"
import { replacePrecacheRevision } from "./pwa-precache-revision"

const CONTROLLER_CHANGE_COUNT = "__pwa_update_controllerchange_count"
const PWA_UPDATE_LIFECYCLE_DIAG_PREFIX = "PWA_UPDATE_LIFECYCLE_DIAG "
type PwaWorkerState =
  "none" | "parsed" | "installing" | "installed" | "activating" | "activated" | "redundant"

type PwaUpdateLifecycleState = {
  diagnosticStatus: "available" | "unavailable"
  controllerChangeCount: number | null
  controllerPresent: boolean | null
  controllerState: PwaWorkerState
  installingState: PwaWorkerState
  waitingState: PwaWorkerState
  activeState: PwaWorkerState
  controllerIsActive: boolean | null
}

async function assertStaticSpaDocumentResponse(
  response: { status(): number; text(): Promise<string> } | null | undefined
): Promise<void> {
  expect(response?.status()).toBe(200)
  expect(response).not.toBeNull()
  // main.tsx consumes this marker synchronously before the live DOM is observable.
  expect(await response!.text()).toMatch(
    /<html(?=\s|>)[^>]*\sdata-render-mode=["']static-spa["'](?=\s|>)[^>]*>/iu
  )
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

async function readPwaUpdateLifecycleState(
  page: Page,
  storageKey: string
): Promise<PwaUpdateLifecycleState> {
  const unavailable: PwaUpdateLifecycleState = {
    diagnosticStatus: "unavailable",
    controllerChangeCount: null,
    controllerPresent: null,
    controllerState: "none",
    installingState: "none",
    waitingState: "none",
    activeState: "none",
    controllerIsActive: null,
  }
  try {
    const state = await page.evaluate(async (key): Promise<PwaUpdateLifecycleState> => {
      const stateOf = (worker: ServiceWorker | null): PwaWorkerState => worker?.state ?? "none"
      try {
        const serviceWorker = navigator.serviceWorker
        const registration = await serviceWorker.getRegistration()
        const controller = serviceWorker.controller
        const active = registration?.active ?? null
        const storedCount = Number(sessionStorage.getItem(key) ?? "0")
        const controllerChangeCount =
          Number.isSafeInteger(storedCount) && storedCount >= 0 && storedCount <= 64
            ? storedCount
            : null
        return {
          diagnosticStatus: "available",
          controllerChangeCount,
          controllerPresent: controller !== null,
          controllerState: stateOf(controller),
          installingState: stateOf(registration?.installing ?? null),
          waitingState: stateOf(registration?.waiting ?? null),
          activeState: stateOf(active),
          controllerIsActive: controller && active ? controller === active : null,
        }
      } catch {
        return {
          diagnosticStatus: "unavailable",
          controllerChangeCount: null,
          controllerPresent: null,
          controllerState: "none",
          installingState: "none",
          waitingState: "none",
          activeState: "none",
          controllerIsActive: null,
        }
      }
    }, storageKey)
    return state
  } catch {
    return unavailable
  }
}

async function emitPwaUpdateLifecycleDiagnostic(
  page: Page,
  projectName: string,
  storageKey: string,
  workerTransformApplied: boolean,
  bundleUpdateResponseSeen: boolean,
  routeEntries: number,
  originMatches: number,
  bundlePathMatches: number,
  serviceWorkerRequestSeen: boolean
): Promise<void> {
  const project = projectName === "desktop" || projectName === "mobile" ? projectName : undefined
  if (!project) return
  const state = await readPwaUpdateLifecycleState(page, storageKey)
  const safeCount = (value: number): number | null =>
    Number.isSafeInteger(value) && value >= 0 && value <= 64 ? value : null
  const record = {
    schema: 1,
    project,
    ...state,
    workerTransformApplied,
    bundleUpdateResponseSeen,
    routeEntries: safeCount(routeEntries),
    originMatches: safeCount(originMatches),
    bundlePathMatches: safeCount(bundlePathMatches),
    serviceWorkerRequestSeen,
  }
  try {
    process.stdout.write(`${PWA_UPDATE_LIFECYCLE_DIAG_PREFIX}${JSON.stringify(record)}\n`)
  } catch {
    // Failure diagnostics must not change the original acceptance result.
  }
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
      await assertStaticSpaDocumentResponse(response)
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
  }, testInfo) => {
    test.skip(browserName !== "chromium", "the Service Worker update acceptance requires Chromium")

    const updateProxy = await startPwaUpdateProxy(context, ownedSessionOrigin())
    let cdp: Awaited<ReturnType<typeof context.newCDPSession>> | undefined

    try {
      await page.addInitScript((storageKey) => {
        navigator.serviceWorker?.addEventListener("controllerchange", () => {
          const current = Number(sessionStorage.getItem(storageKey) ?? "0")
          sessionStorage.setItem(storageKey, String(current + 1))
        })
      }, CONTROLLER_CHANGE_COUNT)

      await page.goto(new URL("/login", updateProxy.origin).toString(), {
        waitUntil: "domcontentloaded",
      })
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

      cdp = await context.newCDPSession(page)
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true })

      // First prove a public route can still load from the original precache while
      // offline. No account is created and no application API is intercepted.
      await context.setOffline(true)
      const offlineResponse = await page.goto(
        new URL("/forgot-password", updateProxy.origin).toString(),
        { waitUntil: "domcontentloaded" }
      )
      await assertStaticSpaDocumentResponse(offlineResponse)
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page).toHaveURL(/\/forgot-password$/u)
      await context.setOffline(false)

      const appOrigin = new URL(page.url()).origin
      const marker = `pwa-build-marker-${Date.now()}-${Math.random().toString(16).slice(2)}`
      const updateRevision = `pwa-update-${marker}`
      let workerUpdateResponses = 0
      let bundleUpdateResponses = 0
      const bundleRouteCounterLimit = 64
      const incrementBundleRouteCounter = (current: number): number =>
        Math.min(current + 1, bundleRouteCounterLimit)
      let routeEntries = 0
      let originMatches = 0
      let bundlePathMatches = 0
      let serviceWorkerRequestSeen = false

      // The loopback proxy handles the actual service-worker update fetch; Chromium
      // browser routes do not intercept service-worker main script updates.
      updateProxy.setWorkerResponseTransform((source) => {
        const updatedSource = replacePrecacheRevision(source, appBundlePath, updateRevision)
        workerUpdateResponses += 1
        return updatedSource
      })
      await context.route("**/assets/**", async (route) => {
        const request = route.request()
        routeEntries = incrementBundleRouteCounter(routeEntries)
        if (request.serviceWorker() !== null) serviceWorkerRequestSeen = true
        const url = new URL(request.url())
        if (url.origin !== appOrigin) {
          await route.continue()
          return
        }
        originMatches = incrementBundleRouteCounter(originMatches)
        if (url.pathname !== appBundlePath) {
          await route.continue()
          return
        }
        bundlePathMatches = incrementBundleRouteCounter(bundlePathMatches)

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

      await page.evaluate(async () => {
        const activeRegistration = await navigator.serviceWorker.ready
        await activeRegistration.update()
      })

      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page).toHaveURL(/\/forgot-password$/u)
      expect(workerUpdateResponses).toBeGreaterThan(0)
      try {
        await expect
          .poll(() =>
            page.evaluate(
              (storageKey) => Number(sessionStorage.getItem(storageKey) ?? "0"),
              CONTROLLER_CHANGE_COUNT
            )
          )
          .toBeGreaterThan(0)
        expect(bundleUpdateResponses).toBeGreaterThan(0)
      } catch (assertionFailure) {
        try {
          const project = testInfo.project.name
          if (project === "desktop" || project === "mobile") {
            process.stdout.write(
              `PWA_BUNDLE_ROUTE_DIAG ${JSON.stringify({
                schema: 1,
                project,
                routeEntries,
                originMatches,
                bundlePathMatches,
                serviceWorkerRequestSeen,
              })}\n`
            )
          }
          await emitPwaUpdateLifecycleDiagnostic(
            page,
            project,
            CONTROLLER_CHANGE_COUNT,
            workerUpdateResponses > 0,
            bundleUpdateResponses > 0,
            routeEntries,
            originMatches,
            bundlePathMatches,
            serviceWorkerRequestSeen
          )
        } catch {
          // Failure diagnostics must not alter the original acceptance result.
        }
        throw assertionFailure
      }

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
      const updatedOfflineResponse = await page.goto(
        new URL("/forgot-password", updateProxy.origin).toString(),
        {
          waitUntil: "domcontentloaded",
        }
      )
      await assertStaticSpaDocumentResponse(updatedOfflineResponse)
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.locator("#pwa-build-marker")).toHaveAttribute(
        "data-pwa-build-marker",
        marker
      )
      await expect(page).toHaveURL(/\/forgot-password$/u)
    } finally {
      try {
        await context.unroute("**/assets/**")
      } finally {
        try {
          await context.setOffline(false)
        } finally {
          try {
            if (cdp) await cdp.detach()
          } finally {
            await updateProxy.close()
          }
        }
      }
    }
  })
})
