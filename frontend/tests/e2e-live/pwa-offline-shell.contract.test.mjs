import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFile } from "node:fs/promises"
import { clearTimeout as clearNodeTimeout, setTimeout as setNodeTimeout } from "node:timers"
import { URL } from "node:url"
import test from "node:test"
const { replacePrecacheRevision } = await import("./pwa-precache-revision.ts")

const primaryClickNavigationBarrierPattern =
  /await Promise\.all\(\[\s*page\.waitForEvent\("framenavigated", \{\s*predicate: \(frame\) => frame === page\.mainFrame\(\),\s*timeout: 15_000,\s*\}\),\s*updateReloadButton\(page\)\.click\(\),?\s*\]\)/u

const specUrl = new URL("./pwa-offline-shell.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const globalSetupUrl = new URL("../../scripts/playwright-live-global-setup.mjs", import.meta.url)
const precachingUrl = new URL("../../src/sw/precaching.ts", import.meta.url)
const workboxConfigUrl = new URL("../../scripts/workbox-config.mjs", import.meta.url)
const serviceWorkerRegistrationUrl = new URL("../../src/push/register-sw.ts", import.meta.url)
const serviceWorkerUrl = new URL("../../src/sw.ts", import.meta.url)
const updateProxyUrl = new URL("./pwa-update-proxy.ts", import.meta.url)

const [
  spec,
  config,
  globalSetup,
  precaching,
  workboxConfig,
  serviceWorkerRegistration,
  serviceWorker,
  updateProxy,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(globalSetupUrl, "utf8"),
  readFile(precachingUrl, "utf8"),
  readFile(workboxConfigUrl, "utf8"),
  readFile(serviceWorkerRegistrationUrl, "utf8"),
  readFile(serviceWorkerUrl, "utf8"),
  readFile(updateProxyUrl, "utf8"),
])

function assertProxySource(pattern, message) {
  assert.ok(pattern.test(updateProxy), message)
}

test("rewrites only the selected generated Workbox precache record", () => {
  const siblingEntry = '{"revision":"sibling-revision","url":"assets/route-chunk.js"}'
  const workerSource =
    'precacheAndRoute([{"revision":"old-app-revision","url":"assets/app-build.js"},' +
    siblingEntry +
    "]);"

  const transformed = replacePrecacheRevision(
    workerSource,
    "/assets/app-build.js",
    "pwa-build-marker-test"
  )

  assert.equal(
    transformed,
    workerSource.replace('"revision":"old-app-revision"', '"revision":"pwa-build-marker-test"'),
    "the generated quoted-key, revision-before-url entry changes only its selected revision"
  )
  assert.ok(transformed.includes(siblingEntry), "unselected precache records remain byte-identical")
})

test("retains support for the older bare-key Workbox precache form", () => {
  const workerSource =
    'precacheAndRoute([{revision:"old-app-revision",url:"assets/app-build.js"}]);'
  const transformed = replacePrecacheRevision(
    workerSource,
    "/assets/app-build.js",
    "pwa-build-marker-test"
  )

  assert.equal(
    transformed,
    workerSource.replace('revision:"old-app-revision"', 'revision:"pwa-build-marker-test"')
  )
})

test("fails closed when the selected bundle has multiple precache records", () => {
  const duplicateWorkerSource =
    'precacheAndRoute([{"revision":"first","url":"assets/app-build.js"},' +
    '{"revision":"second","url":"assets/app-build.js"}]);'

  assert.throws(
    () => replacePrecacheRevision(duplicateWorkerSource, "/assets/app-build.js", "marker"),
    /Expected exactly one precache entry for the selected app bundle/u
  )
})

test("live PWA shell acceptance exercises the real worker without server mutations or mocks", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /globalSetup:\s*["']\.\/scripts\/playwright-live-global-setup\.mjs["']/u)
  assert.match(globalSetup, /verify-endpoints/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /page\.goto\(["']\/login["']/u)
  assert.match(spec, /page\.goto\(["']\/register["']/u)
  assert.match(spec, /context\.setOffline\(true\)/u)
  assert.match(spec, /context\.setOffline\(false\)/u)
  assert.match(spec, /Network\.setCacheDisabled/u)
  assert.match(spec, /data-render-mode/u)
  assert.match(
    spec,
    /async function assertStaticSpaDocumentResponse\([\s\S]*?response!\.text\(\)[\s\S]*?data-render-mode/u,
    "the static shell marker is read from the original navigation response"
  )
  assert.match(spec, /expect\(response\?\.status\(\)\)\.toBe\(200\)/u)
  const staticSpaRootPattern =
    /<html(?=\s|>)[^>]*\sdata-render-mode=["']static-spa["'](?=\s|>)[^>]*>/iu
  assert.ok(
    spec.includes(
      String.raw`/<html(?=\s|>)[^>]*\sdata-render-mode=["']static-spa["'](?=\s|>)[^>]*>/iu`
    ),
    "the response check pins the exact HTML attribute boundary"
  )
  assert.match('<html data-render-mode="static-spa">', staticSpaRootPattern)
  assert.doesNotMatch('<html fake-data-render-mode="static-spa">', staticSpaRootPattern)
  assert.doesNotMatch('<htmlx data-render-mode="static-spa">', staticSpaRootPattern)
  assert.doesNotMatch(spec, /\\bdata-render-mode/u)
  assert.equal(
    (
      spec.match(
        /await assertStaticSpaDocumentResponse\((?:response|offlineResponse|updatedOfflineResponse)\)/gu
      ) ?? []
    ).length,
    3,
    "each offline shell response is checked before client bootstrap removes its marker"
  )
  assert.doesNotMatch(
    spec,
    /page\.locator\(["']html["']\)\)\.toHaveAttribute\(["']data-render-mode["']/u,
    "the consumed marker is not asserted against the post-bootstrap DOM"
  )
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
    /useMockApi|page\.route|routeWebSocket|page\.request|context\.request|\.(?:submit|requestSubmit)\s*\(/u,
    "the live scenario does not mock request handling, call request APIs, or submit a form"
  )
  assert.doesNotMatch(
    spec,
    /\.(?:post|put|delete|patch)\s*\(/u,
    "the live scenario does not issue application mutation methods"
  )
  assert.equal(
    [...spec.matchAll(/\bfetch\s*\(/gu)].length,
    1,
    "the sole fetch is the existing real asset-route fetch"
  )
  assert.match(spec, /const response = await route\.fetch\(\)/u)
  assert.equal(
    [...spec.matchAll(/context\.route\(/gu)].length,
    1,
    "the sole browser route remains the app-bundle marker asset route"
  )
  assert.equal(
    [...spec.matchAll(/\.fill\(/gu)].length,
    1,
    "the peer login draft is the only form field filled"
  )
  assert.match(
    spec,
    /const peerEmailInput = peerPage\.getByRole\("textbox", \{\s*name: "E-mail"\s*\}\)[\s\S]*?await peerEmailInput\.fill\(peerDraft\)/u,
    "the one filled field is the peer draft whose retention is checked"
  )
  assert.equal(
    [...spec.matchAll(/\.click\(/gu)].length,
    2,
    "only the two per-page update-consent buttons are clicked"
  )
  assert.match(
    spec,
    primaryClickNavigationBarrierPattern,
    "the primary main-frame navigation wait is armed with the real consent click"
  )
  assert.match(spec, /await updateReloadButton\(peerPage\)\.click\(\)/u)
  assert.match(
    spec,
    /system:installPrompt\.reload[\s\S]*?const UPDATE_RELOAD_BUTTON_NAME = "Reload"[\s\S]*?getByRole\("button", \{\s*name: UPDATE_RELOAD_BUTTON_NAME,\s*exact: true\s*\}\)/u,
    "consent clicks target the locale-pinned real translated button"
  )
  assert.match(spec, /context\.addCookies\(\[\{\s*name: "ue:language",\s*value: "en"/u)
  assert.match(spec, /localStorage\.setItem\("ue:language",\s*"en"\)/u)
  assert.match(spec, /await prepareUpdatePage\(page\)[\s\S]*?await page\.goto/u)
  assert.match(spec, /await prepareUpdatePage\(peerPage\)[\s\S]*?await peerPage\.goto/u)

  assert.match(precaching, /new NetworkOnly\(/u)
  assert.match(precaching, /handlerDidError/u)
  assert.match(precaching, /matchPrecache\("_shell\.html"\)/u)
  assert.ok(
    workboxConfig.includes('globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json,woff2}"]'),
    "the production precache must include shell HTML and its app bundles"
  )
})

test("live PWA update replaces the active precache and proves the new app bundle works offline", () => {
  assert.match(
    spec,
    /updates the active service worker online and serves the new precached bundle offline/u
  )
  assert.match(spec, /replacePrecacheRevision/u)
  assert.match(spec, /import \{ replacePrecacheRevision \} from ["']\.\/pwa-precache-revision["']/u)
  assert.match(spec, /startPwaUpdateProxy\(context,\s*ownedSessionOrigin\(\)\)/u)
  assert.match(spec, /setWorkerResponseTransform/u)
  assert.doesNotMatch(spec, /context\.route\(["']\*\*\/sw\.js["']/u)
  assert.match(spec, /context\.route\(["']\*\*\/assets\/\*\*["']/u)
  assert.match(spec, /const bundleRouteCounterLimit = 64/u)
  assert.match(spec, /PWA_BUNDLE_ROUTE_DIAG /u)
  assert.match(
    spec,
    /bundleUpdateResponses\)\.toBeGreaterThan\(0\)[\s\S]*?catch \(assertionFailure\)[\s\S]*?PWA_BUNDLE_ROUTE_DIAG/u,
    "route diagnostics are emitted only when the unchanged bundle-response assertion fails"
  )
  assert.match(
    spec,
    /PWA_BUNDLE_ROUTE_DIAG \$\{JSON\.stringify\(\{\s*schema: 1,\s*project,\s*routeEntries,\s*originMatches,\s*bundlePathMatches,\s*serviceWorkerRequestSeen,\s*\}\)\}/u,
    "the route failure record contains only its closed numeric and boolean fields"
  )
  assert.match(spec, /routeEntries = incrementBundleRouteCounter\(routeEntries\)/u)
  assert.match(spec, /originMatches = incrementBundleRouteCounter\(originMatches\)/u)
  assert.match(spec, /bundlePathMatches = incrementBundleRouteCounter\(bundlePathMatches\)/u)
  assert.match(spec, /request\.serviceWorker\(\) !== null/u)
  assert.doesNotMatch(
    spec,
    /PWA_BUNDLE_ROUTE_DIAG[\s\S]{0,500}(?:request\.url\(\)|url\.href|error\.message)/u,
    "the failure record contains only bounded counters and a boolean"
  )
  assertProxySource(
    /import \{ isIP, type AddressInfo \} from ["\x27]node:net["\x27]/u,
    "proxy uses Node loopback address helpers"
  )
  assertProxySource(
    /parsed\.protocol !== ["\x27]http:["\x27]/u,
    "proxy requires HTTP for the owned local stand"
  )
  assertProxySource(
    /parsed\.hostname !== ["\x27]localhost["\x27]/u,
    "proxy pins the configured live origin host"
  )
  assertProxySource(
    /const proxyOrigin = new URL\(["\x27]http:\/\/localhost:0["\x27]\)/u,
    "browser-facing proxy keeps localhost origin semantics"
  )
  assertProxySource(
    /server\.listen\(\s*0\s*,\s*["\x27]127\.0\.0\.1["\x27]/u,
    "proxy binds only to IPv4 loopback"
  )
  assertProxySource(
    /proxyOrigin\.port = String\(\(address as AddressInfo\)\.port\)/u,
    "proxy advertises the port of its bound loopback listener"
  )
  assertProxySource(
    /proxyReady\s*=\s*true/u,
    "proxy becomes ready only after its actual loopback address is verified"
  )
  assertProxySource(
    /isLoopbackAddress\(address\.address\)/u,
    "proxy verifies the bound address is loopback"
  )
  assertProxySource(
    /const address = server\.address\(\)[\s\S]*?if\s*\(!address\s*\|\|\s*typeof address === ["\x27]string["\x27]\s*\|\|\s*!isLoopbackAddress\(address\.address\)\)[\s\S]*?proxyOrigin\.port = String\(\(address as AddressInfo\)\.port\)[\s\S]*?proxyReady = true/u,
    "proxy exposes its origin only after verifying the loopback bind"
  )
  assertProxySource(
    /request\.method\s*!==\s*["\x27]GET["\x27]\s*&&\s*request\.method\s*!==\s*["\x27]HEAD["\x27]/u,
    "proxy rejects unsafe request methods"
  )
  assertProxySource(/Allow:\s*["\x27]GET, HEAD["\x27]/u, "proxy declares its safe methods")
  assert.match(
    spec,
    /finally\s*\{\s*try\s*\{[\s\S]*?\}\s*finally\s*\{\s*await updateProxy\.close\(\)\s*\}\s*\}/u
  )
  assertProxySource(
    /upstreamTarget\.origin !== upstreamOrigin\.origin/u,
    "proxy rejects any target outside the signed upstream origin"
  )
  assertProxySource(
    /const upstreamPort = Number\(upstreamOrigin\.port\)[\s\S]*?Number\.isSafeInteger\(upstreamPort\)[\s\S]*?upstreamPort < LIVE_STAND_MIN_PORT[\s\S]*?upstreamPort > LIVE_STAND_MAX_PORT/u,
    "proxy validates the numeric destination port before opening a socket"
  )
  assertProxySource(
    /requestHeaders\.host = proxyOrigin\.host[\s\S]*?httpRequest\(\s*["']http:\/\/127\.0\.0\.1["']\s*,\s*\{\s*hostname:\s*["']127\.0\.0\.1["']\s*,\s*port:\s*upstreamPort\s*,\s*method:\s*request\.method\s*,\s*path:\s*`\$\{upstreamTarget\.pathname\}\$\{upstreamTarget\.search\}`\s*,\s*headers:\s*requestHeaders/u,
    "proxy fixes the socket authority and forwards only the validated request path"
  )
  assert.doesNotMatch(updateProxy, /httpRequest\(\s*upstreamTarget/u)
  assertProxySource(
    /request\.method\s*===\s*["\x27]GET["\x27]\s*&&\s*upstreamTarget\.pathname\s*===\s*["\x27]\/sw\.js["\x27]/u,
    "only GET /sw.js receives the worker transform"
  )
  assertProxySource(
    /response\.on\(["\x27]close["\x27],\s*\(\)\s*=>\s*\{\s*if\s*\(!response\.writableEnded\)\s*upstreamRequest\.destroy\(\)/u,
    "closed browser responses cancel stalled upstream requests"
  )
  assertProxySource(
    /if\s*\(response\.destroyed\)\s*return/u,
    "upstream errors do not write to destroyed clients"
  )
  assertProxySource(/MAX_WORKER_SCRIPT_BYTES/u, "worker transformation remains size bounded")
  assert.match(spec, /url\.pathname !== appBundlePath/u)
  assert.match(spec, /pwa-build-marker/u)
  assert.match(spec, /controllerchange/u)
  assert.match(spec, /const previousController = serviceWorker\.controller/u)
  assert.match(spec, /if \(!previousController\)\s*\{\s*throw new Error/u)
  assert.match(
    spec,
    /const onControllerChange = \(\) => \{\s*const currentController = serviceWorker\.controller\s*if \(!currentController \|\| currentController === previousController\) return\s*serviceWorker\.removeEventListener\("controllerchange", onControllerChange\)\s*resolve\(\)\s*\}/u,
    "the observer ignores null or same-controller events and resolves only after identity changes"
  )
  assert.match(spec, /serviceWorker\.addEventListener\("controllerchange", onControllerChange\)/u)
  assert.match(spec, /const peerPage = await context\.newPage\(\)/u)
  const updateTestStartIndex = spec.indexOf(
    'test("updates the active service worker online and serves the new precached bundle offline"'
  )
  const updatePageBaselineIndex = spec.indexOf("const updatePageInitialUrl = page.url()")
  const updatePageInitialTimeOriginIndex = spec.indexOf(
    "const updatePageInitialTimeOrigin = await page.evaluate(() => performance.timeOrigin)",
    updateTestStartIndex
  )
  const updatePageNavigationCounterIndex = spec.indexOf(
    "let updatePageMainFrameNavigations = 0",
    updatePageInitialTimeOriginIndex
  )
  const updatePageNavigationListenerIndex = spec.indexOf(
    'page.on("framenavigated", (frame) => {',
    updatePageNavigationCounterIndex
  )
  const updatePageNavigationCounterHandlerIndex = spec.indexOf(
    "if (frame === page.mainFrame()) updatePageMainFrameNavigations += 1",
    updatePageNavigationListenerIndex
  )
  const updateStartIndex = spec.indexOf("await activeRegistration.update()")
  const updatePromptIndex = spec.indexOf("await waitForPwaLiveUpdatePrompt(page)", updateStartIndex)
  const updatePromptVisibleIndex = spec.indexOf(
    "await expect(updateReloadButton(page)).toBeVisible()",
    updatePromptIndex
  )
  const waitingWorkerIndex = spec.indexOf(
    "Boolean((await navigator.serviceWorker.ready).waiting)",
    updatePromptVisibleIndex
  )
  const workerResponseAssertionIndex = spec.indexOf(
    "expect(workerUpdateResponses).toBeGreaterThan(0)",
    waitingWorkerIndex
  )
  const preConsentUrlIndex = spec.indexOf(
    "await expect(page).toHaveURL(updatePageInitialUrl)",
    workerResponseAssertionIndex
  )
  const preConsentTimeOriginIndex = spec.indexOf(
    "expect(await page.evaluate(() => performance.timeOrigin)).toBe(updatePageInitialTimeOrigin)",
    preConsentUrlIndex
  )
  const preConsentNoNavigationIndex = spec.indexOf(
    "expect(updatePageMainFrameNavigations).toBe(0)",
    preConsentTimeOriginIndex
  )
  const pageOneConsentIndex = spec.indexOf(
    "updateReloadButton(page).click()",
    preConsentNoNavigationIndex
  )
  const pageOnePromiseAllStartIndex = spec.lastIndexOf("await Promise.all([", pageOneConsentIndex)
  const pageOneNavigationWaitIndex = spec.indexOf(
    'page.waitForEvent("framenavigated", {',
    pageOnePromiseAllStartIndex
  )
  const pageOnePromiseAllEndIndex = spec.indexOf("])", pageOneConsentIndex)
  const pageOneHydrationIndex = spec.indexOf(
    "await page.waitForFunction(() => window.__APP_HYDRATED === true)",
    pageOneConsentIndex
  )
  const pageOneReloadUrlIndex = spec.indexOf(
    "await expect(page).toHaveURL(/\\/forgot-password$/u)",
    pageOneHydrationIndex
  )
  const pageOneNavigationCountIndex = spec.indexOf(
    "expect(updatePageMainFrameNavigations).toBe(1)",
    pageOneReloadUrlIndex
  )
  const bundleAssertionIndex = spec.indexOf("expect(bundleUpdateResponses).toBeGreaterThan(0)")
  const updateTestEndIndex = spec.indexOf("\n  })", updateTestStartIndex)
  const updateTestSource = spec.slice(updateTestStartIndex, updateTestEndIndex)
  const primaryPageNavigationWaitCount = [
    ...updateTestSource.matchAll(/page\.waitForEvent\("framenavigated",/gu),
  ].length
  const peerControllerArmIndex = spec.indexOf(
    "await armDifferentServiceWorkerControllerBarrier(peerPage)",
    preConsentNoNavigationIndex
  )
  const primaryFlowIndices = [
    updateTestStartIndex,
    updatePageBaselineIndex,
    updatePageInitialTimeOriginIndex,
    updatePageNavigationCounterIndex,
    updatePageNavigationListenerIndex,
    updatePageNavigationCounterHandlerIndex,
    updateStartIndex,
    updatePromptIndex,
    updatePromptVisibleIndex,
    waitingWorkerIndex,
    workerResponseAssertionIndex,
    preConsentUrlIndex,
    preConsentTimeOriginIndex,
    preConsentNoNavigationIndex,
    peerControllerArmIndex,
    pageOnePromiseAllStartIndex,
    pageOneNavigationWaitIndex,
    pageOneConsentIndex,
    pageOnePromiseAllEndIndex,
    pageOneHydrationIndex,
    pageOneReloadUrlIndex,
    pageOneNavigationCountIndex,
    bundleAssertionIndex,
    updateTestEndIndex,
  ]
  assert.ok(
    primaryFlowIndices.every((index) => index >= 0),
    "every primary-page update and consent barrier marker exists"
  )
  assert.ok(
    updateTestStartIndex < updatePageBaselineIndex &&
      updatePageBaselineIndex < updatePageInitialTimeOriginIndex &&
      updatePageInitialTimeOriginIndex < updatePageNavigationCounterIndex &&
      updatePageNavigationCounterIndex < updatePageNavigationListenerIndex &&
      updatePageNavigationListenerIndex < updatePageNavigationCounterHandlerIndex &&
      updatePageNavigationCounterHandlerIndex < updateStartIndex &&
      updateStartIndex < updatePromptIndex &&
      updatePromptIndex < updatePromptVisibleIndex &&
      updatePromptVisibleIndex < waitingWorkerIndex &&
      waitingWorkerIndex < workerResponseAssertionIndex &&
      workerResponseAssertionIndex < preConsentUrlIndex &&
      preConsentUrlIndex < preConsentTimeOriginIndex &&
      preConsentTimeOriginIndex < preConsentNoNavigationIndex &&
      preConsentNoNavigationIndex < peerControllerArmIndex &&
      peerControllerArmIndex < pageOnePromiseAllStartIndex &&
      pageOnePromiseAllStartIndex < pageOneNavigationWaitIndex &&
      pageOneNavigationWaitIndex < pageOneConsentIndex &&
      pageOneConsentIndex < pageOnePromiseAllEndIndex &&
      pageOnePromiseAllEndIndex < pageOneHydrationIndex &&
      pageOneHydrationIndex < pageOneReloadUrlIndex &&
      pageOneReloadUrlIndex < pageOneNavigationCountIndex &&
      pageOneNavigationCountIndex < bundleAssertionIndex &&
      bundleAssertionIndex < updateTestEndIndex,
    "prompt and pre-consent identity checks precede the click-scoped waiter and post-consent reload"
  )
  assert.equal(
    primaryPageNavigationWaitCount,
    1,
    "the update test has exactly one primary-page navigation waiter"
  )
  const primaryWaitSourceBeforeConsent = spec.slice(
    updateTestStartIndex,
    pageOnePromiseAllStartIndex
  )
  const primaryNavigationWaitSourcePattern = /page\.waitForEvent\("framenavigated",/u
  assert.doesNotMatch(
    primaryWaitSourceBeforeConsent,
    primaryNavigationWaitSourcePattern,
    "the primary navigation deadline is not armed before the click-scoped group"
  )
  const earlyNavigationWaitMutation = primaryWaitSourceBeforeConsent.replace(
    "const updatePageInitialUrl = page.url()",
    'const earlyNavigationWait = page.waitForEvent("framenavigated", {})\n      const updatePageInitialUrl = page.url()'
  )
  assert.notEqual(earlyNavigationWaitMutation, primaryWaitSourceBeforeConsent)
  assert.throws(
    () => assert.doesNotMatch(earlyNavigationWaitMutation, primaryNavigationWaitSourcePattern),
    (error) => error?.name === "AssertionError",
    "the early-wait negative control is rejected by the no-early-wait guard"
  )
  const primaryConsentBarrierSource = spec.slice(
    pageOnePromiseAllStartIndex,
    pageOnePromiseAllEndIndex + 2
  )
  const unawaitedPrimaryConsentBarrierSource = primaryConsentBarrierSource.replace(
    "await Promise.all(",
    "Promise.all("
  )
  assert.notEqual(unawaitedPrimaryConsentBarrierSource, primaryConsentBarrierSource)
  assert.doesNotMatch(
    unawaitedPrimaryConsentBarrierSource,
    primaryClickNavigationBarrierPattern,
    "the contract rejects an unawaited navigation-and-consent group"
  )
  const primaryConsentBarrierWithoutClick = primaryConsentBarrierSource.replace(
    "updateReloadButton(page).click(),",
    ""
  )
  assert.notEqual(primaryConsentBarrierWithoutClick, primaryConsentBarrierSource)
  assert.doesNotMatch(
    primaryConsentBarrierWithoutClick,
    primaryClickNavigationBarrierPattern,
    "the contract requires the real primary-page consent click"
  )
  const identityArmIndex = spec.indexOf(
    "await armDifferentServiceWorkerControllerBarrier(peerPage)"
  )
  const identityWaitIndex = spec.indexOf("await peerNewController", pageOneConsentIndex)
  const peerPromptVisibleIndex = spec.indexOf(
    "await expect(updateReloadButton(peerPage)).toBeVisible()",
    identityWaitIndex
  )
  const peerUrlRetainedIndex = spec.indexOf(
    "await expect(peerPage).toHaveURL(peerInitialUrl)",
    peerPromptVisibleIndex
  )
  const peerDraftRetainedIndex = spec.indexOf(
    "await expect(peerEmailInput).toHaveValue(peerDraft)",
    peerUrlRetainedIndex
  )
  const peerTimeOriginRetainedIndex = spec.indexOf(
    "expect(await peerPage.evaluate(() => performance.timeOrigin)).toBe(peerInitialTimeOrigin)",
    peerDraftRetainedIndex
  )
  const peerNoNavigationIndex = spec.indexOf(
    "expect(peerMainFrameNavigations).toBe(0)",
    peerTimeOriginRetainedIndex
  )
  const peerConsentIndex = spec.indexOf(
    "await updateReloadButton(peerPage).click()",
    peerNoNavigationIndex
  )
  const peerPostReloadNavigationIndex = spec.indexOf(
    "expect(peerMainFrameNavigations).toBe(1)",
    peerConsentIndex
  )
  const peerFlowIndices = [
    identityArmIndex,
    pageOneConsentIndex,
    identityWaitIndex,
    peerPromptVisibleIndex,
    peerUrlRetainedIndex,
    peerDraftRetainedIndex,
    peerTimeOriginRetainedIndex,
    peerNoNavigationIndex,
    peerConsentIndex,
    peerPostReloadNavigationIndex,
  ]
  assert.ok(
    peerFlowIndices.every((index) => index >= 0),
    "every peer consent sequence marker exists"
  )
  assert.ok(
    identityArmIndex >= 0 &&
      identityArmIndex < pageOneConsentIndex &&
      pageOneConsentIndex < identityWaitIndex &&
      identityWaitIndex < peerPromptVisibleIndex &&
      peerPromptVisibleIndex < peerUrlRetainedIndex &&
      peerUrlRetainedIndex < peerDraftRetainedIndex &&
      peerDraftRetainedIndex < peerTimeOriginRetainedIndex &&
      peerTimeOriginRetainedIndex < peerNoNavigationIndex &&
      peerNoNavigationIndex < peerConsentIndex &&
      peerConsentIndex < peerPostReloadNavigationIndex,
    "the peer's different-controller event precedes its unchanged-document checks and own consent click"
  )
  const activationWaitSource = spec.slice(updateStartIndex, bundleAssertionIndex)
  assert.match(
    activationWaitSource,
    /await expect\s*\.poll\([\s\S]*?CONTROLLER_CHANGE_COUNT[\s\S]*?\.toBeGreaterThan\(0\)/u,
    "the bundle response is asserted after the existing controllerchange readiness signal"
  )
  const diagnosticTryStartIndex = spec.lastIndexOf("try {", bundleAssertionIndex)
  const diagnosticCatchStartIndex = spec.indexOf("} catch (assertionFailure)", bundleAssertionIndex)
  assert.ok(
    diagnosticTryStartIndex >= updateStartIndex && diagnosticCatchStartIndex > bundleAssertionIndex,
    "controllerchange and bundle acceptance remain inside the diagnostic try/catch"
  )
  const diagnosticTrySource = spec.slice(diagnosticTryStartIndex, diagnosticCatchStartIndex)
  assert.match(
    diagnosticTrySource,
    /await expect\s*\.poll\([\s\S]*?CONTROLLER_CHANGE_COUNT[\s\S]*?\.toBeGreaterThan\(0\)[\s\S]*?expect\(bundleUpdateResponses\)\.toBeGreaterThan\(0\)[\s\S]*?const pageControllerChangeCount\s*=\s*await page\.evaluate\([\s\S]*?CONTROLLER_CHANGE_COUNT[\s\S]*?expect\(pageControllerChangeCount\)\.toBeGreaterThan\(0\)/u,
    "both controller counters and the bundle response remain strict assertions within that guard"
  )
  const diagnosticThrowIndex = spec.indexOf("throw assertionFailure", diagnosticCatchStartIndex)
  assert.ok(diagnosticThrowIndex > diagnosticCatchStartIndex)
  const diagnosticCatchSource = spec.slice(
    diagnosticCatchStartIndex,
    diagnosticThrowIndex + "throw assertionFailure".length
  )
  assert.match(
    diagnosticCatchSource,
    /PWA_BUNDLE_ROUTE_DIAG[\s\S]*?emitPwaUpdateLifecycleDiagnostic[\s\S]*?throw assertionFailure/u,
    "failure diagnostics still emit and rethrow the original assertion"
  )
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
  assert.match(
    serviceWorkerRegistration,
    /const updateConsents = new WeakMap<ServiceWorker, UpdateConsent>\(\)\s*let reloadRequested = false\s*const updateConsentFor = \(worker: ServiceWorker\): UpdateConsent => \{\s*const existing = updateConsents\.get\(worker\)\s*if \(existing\) return existing\s*const consent: UpdateConsent = \{\s*accepted: false,\s*controllerChanged: false,\s*notified: false,\s*\}\s*updateConsents\.set\(worker, consent\)\s*return consent\s*\}/u,
    "new consent state is unaccepted and bound to that worker on cache miss"
  )
  assert.match(
    serviceWorkerRegistration,
    /const reloadAfterAcceptedUpdate = \(worker: ServiceWorker, consent: UpdateConsent\) => \{\s*if \(reloadRequested \|\| !consent\.accepted \|\| !consent\.controllerChanged\) return\s*if \(serviceWorkerContainer\.controller !== worker\) return\s*reloadRequested = true\s*window\.location\.reload\(\)\s*\}/u,
    "reload requires this page's consent and controller change to that same worker"
  )
  assert.equal(
    [...serviceWorkerRegistration.matchAll(/window\.location\.reload\(\)/gu)].length,
    1,
    "the gated update helper remains the only registration reload path"
  )
  assert.match(
    serviceWorkerRegistration,
    /const showUpdateAvailable = \(worker: ServiceWorker\) => \{\s*const consent = updateConsentFor\(worker\)[\s\S]*?const detail: ServiceWorkerUpdateEventDetail = \{\s*update: async \(\) => \{[\s\S]*?consent\.accepted = true[\s\S]*?reloadAfterAcceptedUpdate\(worker, consent\)\s*\}/u,
    "the prompted worker's own consent state is accepted before its per-page reload helper runs"
  )
  assert.equal(
    [...serviceWorkerRegistration.matchAll(/consent\.accepted\s*=\s*true/gu)].length,
    1,
    "only the prompted update callback can accept the worker"
  )
  assert.match(
    serviceWorkerRegistration,
    /let observedController = serviceWorkerContainer\.controller\s*serviceWorkerContainer\.addEventListener\("controllerchange", \(\) => \{\s*if \(reloadRequested\) return\s*const currentController = serviceWorkerContainer\.controller\s*if \(currentController === observedController\) return\s*const previousController = observedController\s*observedController = currentController\s*if \(!previousController \|\| !currentController\) return\s*const consent = updateConsentFor\(currentController\)\s*consent\.controllerChanged = true\s*showUpdateAvailable\(currentController\)\s*reloadAfterAcceptedUpdate\(currentController, consent\)\s*\}\)/u,
    "controller activation is paired with consent by the exact worker identity"
  )
  assert.match(serviceWorker, /self\.skipWaiting\(\)/u)
  assert.match(precaching, /cleanupOutdatedCaches\(\)/u)
})

// Exercise the proxy with a transport-only loopback peer. This server exposes no
// application, API, or authentication behavior; all sentinel values are synthetic.
const { createServer, request: httpRequest } = await import("node:http")
const { EventEmitter } = await import("node:events")
const { startPwaUpdateProxy } = await import("./pwa-update-proxy.ts")

function withinDeadline(promise, message, timeoutMs = 3_000) {
  let timer
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setNodeTimeout(() => reject(new Error(message)), timeoutMs)
    }),
  ]).finally(() => clearNodeTimeout(timer))
}

async function listenOnValidatedLoopbackPort(server) {
  const minPort = 20_000
  const portCount = 25_001
  const firstPort = minPort + Math.floor(Math.random() * portCount)
  for (let attempt = 0; attempt < 64; attempt += 1) {
    const port = minPort + ((firstPort - minPort + attempt) % portCount)
    try {
      await new Promise((resolve, reject) => {
        const onListening = () => {
          server.off("error", onError)
          resolve()
        }
        const onError = (error) => {
          server.off("listening", onListening)
          reject(error)
        }
        server.once("listening", onListening)
        server.once("error", onError)
        server.listen(port, "127.0.0.1")
      })
      return new URL(`http://localhost:${port}`)
    } catch (error) {
      if (error?.code !== "EADDRINUSE" && error?.code !== "EACCES") throw error
    }
  }
  throw new Error("Unable to bind the isolated transport test server")
}

async function closeTransportServer(server) {
  if (!server.listening) return
  await new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()))
    server.closeAllConnections()
  })
}

function requestRawProxyTarget(proxyOrigin, requestTarget, headers) {
  const target = new URL(proxyOrigin)
  return new Promise((resolve, reject) => {
    const requestOptions = {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      method: "GET",
      path: requestTarget,
    }
    if (headers !== undefined) requestOptions.headers = headers
    const request = httpRequest(requestOptions, (response) => {
      response.resume()
      response.once("end", () => resolve(response.statusCode ?? 0))
      response.once("error", reject)
    })
    request.once("error", reject)
    request.end()
  })
}

test(
  "PWA update proxy preserves ordinary transport, rejects unsafe forwarding, and closes stalled upstreams",
  { timeout: 12_000 },
  async () => {
    const originalWorkerSource = "self.__workerRevision = 'source-v1';"
    const transformedWorkerSource = "self.__workerRevision = 'transformed-revision';"
    const forwarded = []
    let markStalledRequestSeen
    let markStalledResponseClosed
    const stalledRequestSeen = new Promise((resolve) => {
      markStalledRequestSeen = resolve
    })
    const stalledResponseClosed = new Promise((resolve) => {
      markStalledResponseClosed = resolve
    })
    const upstream = createServer((request, response) => {
      const record = {
        method: request.method,
        url: request.url,
        host: request.headers.host,
        cookie: request.headers.cookie,
        origin: request.headers.origin,
        csrf: request.headers["x-csrf-token"],
      }
      forwarded.push(record)
      if (request.url === "/stalled") {
        markStalledRequestSeen()
        response.once("close", markStalledResponseClosed)
        return
      }
      if (request.url === "/sw.js") {
        response.writeHead(200, {
          "content-type": "application/javascript",
          "content-length": Buffer.byteLength(originalWorkerSource, "utf8"),
          etag: '"source-v1"',
          "last-modified": "Sun, 11 Oct 2026 12:00:00 GMT",
          "content-md5": "synthetic-stale-digest",
        })
        response.end(originalWorkerSource)
        return
      }
      response.writeHead(200, {
        "content-type": "text/plain",
        "set-cookie": "transport-probe=synthetic; Path=/; SameSite=Strict",
      })
      response.end("transport-probe")
    })

    let proxy
    let originServer
    try {
      originServer = await listenOnValidatedLoopbackPort(upstream)
      proxy = await startPwaUpdateProxy(new EventEmitter(), originServer.origin)
      assert.equal(new URL(proxy.origin).hostname, "localhost")
      const proxyHost = new URL(proxy.origin).host
      proxy.setWorkerResponseTransform((source) =>
        source.replace(originalWorkerSource, transformedWorkerSource)
      )

      const syntheticHeaders = {
        cookie: "transport-probe=synthetic-request",
        origin: proxy.origin,
        "x-csrf-token": "synthetic-csrf-probe",
      }
      const getResponse = await globalThis.fetch(
        new URL("/transport-probe?probe=1", proxy.origin),
        {
          headers: syntheticHeaders,
        }
      )
      assert.equal(getResponse.status, 200)
      assert.equal(await getResponse.text(), "transport-probe")
      assert.equal(
        getResponse.headers.get("set-cookie"),
        "transport-probe=synthetic; Path=/; SameSite=Strict"
      )
      assert.deepEqual(forwarded[0], {
        method: "GET",
        url: "/transport-probe?probe=1",
        host: proxyHost,
        cookie: syntheticHeaders.cookie,
        origin: syntheticHeaders.origin,
        csrf: syntheticHeaders["x-csrf-token"],
      })

      const headResponse = await globalThis.fetch(new URL("/transport-probe", proxy.origin), {
        method: "HEAD",
      })
      assert.equal(headResponse.status, 200)
      assert.equal(await headResponse.text(), "")
      assert.equal(forwarded[1].method, "HEAD")

      assert.notEqual(
        Buffer.byteLength(transformedWorkerSource, "utf8"),
        Buffer.byteLength(originalWorkerSource, "utf8")
      )
      const workerResponse = await globalThis.fetch(new URL("/sw.js", proxy.origin))
      assert.equal(workerResponse.status, 200)
      assert.equal(await workerResponse.text(), transformedWorkerSource)
      assert.equal(
        workerResponse.headers.get("content-length"),
        String(Buffer.byteLength(transformedWorkerSource, "utf8"))
      )
      assert.equal(workerResponse.headers.get("content-encoding"), null)
      for (const staleHeader of ["etag", "last-modified", "content-md5"]) {
        assert.equal(
          workerResponse.headers.get(staleHeader),
          null,
          `${staleHeader} must not describe rewritten bytes`
        )
      }
      assert.equal(forwarded[2].method, "GET")
      assert.equal(forwarded[2].url, "/sw.js")

      const beforeHostHeaderProbe = forwarded.length
      assert.equal(
        await requestRawProxyTarget(proxy.origin, "/host-header-probe", {
          host: "attacker.invalid",
        }),
        200
      )
      assert.equal(
        forwarded[beforeHostHeaderProbe]?.host,
        proxyHost,
        "an inbound Host header cannot control the upstream request Host"
      )

      const beforeAuthorityAttacks = forwarded.length
      assert.equal(
        await requestRawProxyTarget(proxy.origin, "http://example.invalid/private"),
        403,
        "absolute-form request targets cannot change the proxy's upstream authority"
      )
      assert.equal(
        await requestRawProxyTarget(proxy.origin, "//example.invalid/private"),
        403,
        "protocol-relative request targets cannot change the proxy's upstream authority"
      )
      assert.equal(forwarded.length, beforeAuthorityAttacks)

      assert.equal(
        await requestRawProxyTarget(proxy.origin, "/%2f%2fexample.invalid/private"),
        200,
        "an encoded slash path remains a path on the owned upstream"
      )
      assert.deepEqual(forwarded[beforeAuthorityAttacks], {
        method: "GET",
        url: "/%2f%2fexample.invalid/private",
        host: proxyHost,
        cookie: undefined,
        origin: undefined,
        csrf: undefined,
      })

      const beforeUnsafeMethod = forwarded.length
      const unsafeResponse = await globalThis.fetch(new URL("/transport-probe", proxy.origin), {
        method: "POST",
        body: "synthetic-body-that-must-not-be-forwarded",
      })
      assert.equal(unsafeResponse.status, 405)
      assert.equal(unsafeResponse.headers.get("allow"), "GET, HEAD")
      assert.equal(forwarded.length, beforeUnsafeMethod)

      const stalledFetch = globalThis.fetch(new URL("/stalled", proxy.origin)).then(
        () => false,
        () => true
      )
      await withinDeadline(
        stalledRequestSeen,
        "The loopback upstream did not receive the stalled request"
      )
      await withinDeadline(proxy.close(), "The proxy did not close with a stalled request")
      await withinDeadline(
        stalledResponseClosed,
        "Proxy close did not cancel the stalled upstream response"
      )
      assert.equal(
        await withinDeadline(stalledFetch, "The browser-side request did not close"),
        true
      )
    } finally {
      try {
        if (proxy) await proxy.close()
      } finally {
        await closeTransportServer(upstream)
      }
    }
  }
)
