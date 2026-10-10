import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./pwa-offline-shell.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const precachingUrl = new URL("../../src/sw/precaching.ts", import.meta.url)
const workboxConfigUrl = new URL("../../scripts/workbox-config.mjs", import.meta.url)
const serviceWorkerRegistrationUrl = new URL("../../src/push/register-sw.ts", import.meta.url)
const serviceWorkerUrl = new URL("../../src/sw.ts", import.meta.url)

const [spec, config, precaching, workboxConfig, serviceWorkerRegistration, serviceWorker] =
  await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(precachingUrl, "utf8"),
    readFile(workboxConfigUrl, "utf8"),
    readFile(serviceWorkerRegistrationUrl, "utf8"),
    readFile(serviceWorkerUrl, "utf8"),
  ])

test("live PWA shell acceptance exercises the real worker without server mutations or mocks", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /page\.goto\(["']\/login["']/u)
  assert.match(spec, /page\.goto\(["']\/register["']/u)
  assert.match(spec, /context\.setOffline\(true\)/u)
  assert.match(spec, /context\.setOffline\(false\)/u)
  assert.match(spec, /Network\.setCacheDisabled/u)
  assert.match(spec, /data-render-mode/u)
  assert.match(spec, /window\.__APP_HYDRATED/u)
  assert.match(spec, /workbox-precache/u)
  assert.match(spec, /requestfailed/u)
  assert.match(spec, /const offlineAssetRequests: string\[\] = \[\]/u)
  assert.match(spec, /const recordOfflineAssetRequest = \(request: Request\)/u)
  assert.match(spec, /offlineAssetRequests\.push\(url\.pathname\)/u)
  assert.match(
    spec,
    /offlineAssetRequests\.every\(\(path\) => precacheEvidence\.precachedPaths\.includes\(path\)\)/u
  )
  assert.doesNotMatch(
    spec,
    /useMockApi|page\.route|routeWebSocket|page\.request|\.fill\(|\.click\(/u
  )

  assert.match(precaching, /new NetworkOnly\(/u)
  assert.match(precaching, /handlerDidError/u)
  assert.match(precaching, /matchPrecache\("_shell\.html"\)/u)
  assert.ok(
    workboxConfig.includes('globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"]'),
    "the production precache must include shell HTML and its app bundles"
  )
})

test("live PWA update replaces the active precache and proves the new app bundle works offline", () => {
  assert.match(
    spec,
    /updates the active service worker online and serves the new precached bundle offline/u
  )
  assert.match(spec, /replacePrecacheRevision/u)
  assert.match(spec, /context\.route\(["']\*\*\/sw\.js["']/u)
  assert.match(spec, /context\.route\(["']\*\*\/assets\/\*\*["']/u)
  assert.match(spec, /url\.pathname !== appBundlePath/u)
  assert.match(spec, /pwa-build-marker/u)
  assert.match(spec, /controllerchange/u)
  assert.match(spec, /await activeRegistration\.update\(\)/u)
  assert.match(spec, /setOffline\(true\)[\s\S]*?setOffline\(false\)[\s\S]*?setOffline\(true\)/u)
  assert.match(spec, /oldBundleCacheKeys[\s\S]*?not\.toContain/u)
  assert.match(spec, /newBundleCacheEntries[\s\S]*?hasBuildMarker/u)
  assert.match(
    spec,
    /newBundleCacheEntries\.some\([\s\S]*?new URL\(entry\.requestUrl\)\.searchParams\.get\(["']__WB_REVISION__["']\)\s*===\s*updateRevision/u
  )
  assert.doesNotMatch(spec, /routeWebSocket|page\.request|useMockApi/u)

  assert.match(serviceWorkerRegistration, /updateViaCache:\s*["']none["']/u)
  assert.match(serviceWorkerRegistration, /controllerchange[\s\S]*?window\.location\.reload\(\)/u)
  assert.match(serviceWorker, /self\.skipWaiting\(\)/u)
  assert.match(precaching, /cleanupOutdatedCaches\(\)/u)
})
