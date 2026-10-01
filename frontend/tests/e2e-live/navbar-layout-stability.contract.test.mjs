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
  assert.match(fixtures, /export async function loginAs\(page: Page, role: Role\)/u)
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
