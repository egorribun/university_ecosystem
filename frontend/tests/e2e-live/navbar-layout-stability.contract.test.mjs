import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./navbar-layout-stability.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const navbarUrl = new URL("../../src/components/navbar/Navbar.tsx", import.meta.url)
const navbarLogoUrl = new URL("../../src/components/navbar/NavbarLogo.tsx", import.meta.url)
const pillUrl = new URL("../../src/components/navbar/NavbarPill.tsx", import.meta.url)
const scrollBehaviorUrl = new URL("../../src/hooks/ui/useScrollBehavior.ts", import.meta.url)
const scrollConstantsUrl = new URL("../../src/constants/scroll.ts", import.meta.url)

const [spec, fixtures, config, navbar, navbarLogo, pill, scrollBehavior, scrollConstants] =
  await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(navbarUrl, "utf8"),
    readFile(navbarLogoUrl, "utf8"),
    readFile(pillUrl, "utf8"),
    readFile(scrollBehaviorUrl, "utf8"),
    readFile(scrollConstantsUrl, "utf8"),
  ])

test("live navbar stability measures real scroll-driven layout shifts", () => {
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/news["']\)/u)
  assert.match(spec, /PerformanceObserver/u)
  assert.match(spec, /layout-shift/u)
  assert.match(spec, /hadRecentInput/u)
  assert.match(spec, /NAVBAR_CLS_LIMIT\s*=\s*0\.1/u)
  assert.match(spec, /expect\(finalMetrics\.cls\)\.toBeLessThan\(NAVBAR_CLS_LIMIT\)/u)
  assert.match(spec, /vt-navbar/u)
  assert.match(spec, /getBoundingClientRect\(\)/u)
  assert.match(spec, /classList\.contains\(["']relative["']\)/u)
  assert.match(spec, /window\.scrollTo\(0,\s*180\)/u)
  assert.match(spec, /window\.scrollTo\(0,\s*0\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|useMockApi/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)
  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*loginPasswordForRole\(role\),\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
})

test("navbar CLS observation includes font and image stabilization", () => {
  const observerInstallation = spec.indexOf("await page.addInitScript")
  const newsNavigation = spec.indexOf('await page.goto("/news")')
  const fontReadiness = spec.indexOf("await document.fonts.ready")
  const imageDecode = spec.indexOf("image.decode()")

  assert.ok(observerInstallation >= 0, "install the observer before target-page navigation")
  assert.ok(observerInstallation < newsNavigation)
  assert.ok(newsNavigation < fontReadiness)
  assert.ok(fontReadiness < imageDecode)
  assert.match(
    spec,
    /observer\.observe\(\{\s*type:\s*["']layout-shift["'],\s*buffered:\s*true\s*\}\)/u
  )
  assert.match(spec, /expect\(decodedNavbarImages\)\.toBeGreaterThan\(0\)/u)
})

test("the measurement exercises the fixed navbar shell and production scroll threshold", () => {
  assert.match(navbar, /<nav[\s\S]{0,180}className=\{cn\([\s\S]{0,180}vt-navbar/u)
  assert.match(navbar, /h-\(--navbar-height\)/u)
  assert.match(navbar, /<NavbarPill[\s\S]{0,180}isCompact=\{showPill\}/u)
  assert.match(pill, /transition-\[transform,opacity\]/u)
  assert.match(navbarLogo, /<SmartImage[\s\S]*?loading="eager"/u)
  assert.match(scrollBehavior, /NAVBAR_SCROLL_ENTER_THRESHOLD/u)
  assert.match(scrollBehavior, /requestAnimationFrame\(commitScrollState\)/u)
  assert.match(scrollConstants, /NAVBAR_SCROLL_ENTER_THRESHOLD\s*=\s*72/u)
  assert.match(scrollConstants, /NAVBAR_SCROLL_EXIT_THRESHOLD\s*=\s*24/u)
})

test("the live run is Chromium-project discoverable with diagnostic artifacts disabled", () => {
  assert.match(spec, /test\.skip\(testInfo\.project\.name\s*!==\s*["']desktop["']/u)
  assert.match(
    spec,
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']\s*\}\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})

test("the desktop spacing diagnostic emits bounded geometry only on failing samples", async () => {
  const spec = await readFile(specUrl, "utf8")
  assert.match(spec, /const NAVBAR_GEOMETRY_DIAGNOSTIC_LIMIT = 6/u)
  assert.match(spec, /UE_LIVE_NAVBAR_GEOMETRY_V1 project=/u)
  assert.match(spec, /sample\.messengerLeft - sample\.referenceRight < 12/u)
  assert.match(spec, /sample\.nameRight > sample\.settingsLeft \+ 1/u)
  assert.match(spec, /sample\.settingsRight > sample\.contentRight \+ 1/u)
  assert.match(spec, /sample\.scrollWidth > sample\.clientWidth \+ 1/u)
})

// Bottom navigation and the drawer share the production navbar shell. Keep
// their rapid-input acceptance contract in this existing CI entrypoint.
test("mobile navigation preserves native rapid input, final content, and history assertions", async () => {
  const navigationSpec = await readFile(
    new URL("./footer-bottom-navigation.live.spec.ts", import.meta.url),
    "utf8"
  )
  assert.match(navigationSpec, /for \(const width of \[390, 360\]\)/u)
  assert.match(
    navigationSpec,
    /await verifyRapidMobileNavigation\(page, testInfo\.project\.use\.hasTouch === true\)/u
  )
  assert.equal((navigationSpec.match(/^test\(/gmu) ?? []).length, 2)
  const rapid = navigationSpec.slice(
    navigationSpec.indexOf("async function verifyRapidMobileNavigation")
  )
  assert.match(
    rapid,
    /const rapidPaths = \["\/events", "\/schedule", "\/profile", "\/news"\] as const/u
  )
  const burst = rapid.slice(
    rapid.indexOf("for (const point of points)"),
    rapid.indexOf('await expectCurrentRoute("/news")')
  )
  assert.match(burst, /await page\.touchscreen\.tap\(point\.x, point\.y\)/u)
  assert.match(burst, /await page\.mouse\.click\(point\.x, point\.y\)/u)
  assert.doesNotMatch(burst, /expect|waitFor|goto|evaluate|locator|boundingBox/u)
  assert.match(rapid, /a\[aria-current="page"\].*\.toHaveCount\(1\)/u)
  assert.match(rapid, /new URL\(page\.url\(\)\)\.pathname\)\.toBe\(path\)/u)
  assert.match(rapid, /path === "\/news" \? newsHeading : eventsTabs\)\.toBeVisible\(\)/u)
  assert.match(rapid, /path === "\/news" \? eventsTabs : newsHeading\)\.toHaveCount\(0\)/u)
  assert.match(rapid, /activation < 2/u)
  assert.match(rapid, /window\.history\.length\)\)\.toBe\(historyLength\)/u)
  assert.match(rapid, /await drawerEvents\.tap\(\)/u)
  assert.match(rapid, /await page\.goBack\(\)\s+await expectCurrentRoute\("\/news"\)/u)
  assert.match(rapid, /await page\.goForward\(\)\s+await expectCurrentRoute\("\/events"\)/u)
  assert.equal((rapid.match(/await expect\(drawer\)\.toHaveCount\(0\)/gu) ?? []).length, 3)
  assert.match(
    rapid,
    /consoleErrorCount, "rapid navigation must not emit console errors"\)\.toBe\(0\)/u
  )
  assert.doesNotMatch(
    rapid,
    /waitForTimeout|setTimeout|dispatchEvent\(|\.route\(|test\.skip|setDefaultTimeout|test\.setTimeout/u
  )
})
