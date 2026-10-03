import assert from "node:assert/strict"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./ssr-hydration-i18n.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const authRouteUrl = new URL("../../src/routes/_auth.tsx", import.meta.url)
const dashboardRouteUrl = new URL("../../src/routes/_auth/dashboard.tsx", import.meta.url)
const newsRouteUrl = new URL("../../src/routes/_auth/news.index.tsx", import.meta.url)
const rootRouteUrl = new URL("../../src/routes/__root.tsx", import.meta.url)
const serverUrl = new URL("../../src/server.ts", import.meta.url)
const ssrThemeUrl = new URL("../../src/ssrTheme.ts", import.meta.url)
const hydrationUrl = new URL("../../src/app/hydration.ts", import.meta.url)

test("live dashboard acceptance covers real RU/EN SSR hydration without raw keys", async () => {
  assert.equal(existsSync(specUrl), true, "the authenticated SSR/i18n live scenario must exist")

  const [
    spec,
    config,
    authRoute,
    dashboardRoute,
    newsRoute,
    rootRoute,
    server,
    ssrTheme,
    hydration,
  ] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(authRouteUrl, "utf8"),
    readFile(dashboardRouteUrl, "utf8"),
    readFile(newsRouteUrl, "utf8"),
    readFile(rootRouteUrl, "utf8"),
    readFile(serverUrl, "utf8"),
    readFile(ssrThemeUrl, "utf8"),
    readFile(hydrationUrl, "utf8"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(authRoute, /ssr:\s*true/u)
  assert.match(dashboardRoute, /createFileRoute\(["']\/_auth\/dashboard["']\)/u)
  assert.match(dashboardRoute, /ssr:\s*true/u)
  assert.match(newsRoute, /createFileRoute\(["']\/_auth\/news\//u)
  assert.match(newsRoute, /prefetchNewsListQuery/u)
  assert.match(server, /extractLangFromRequest\(request\)/u)
  assert.match(ssrTheme, /parseCookie\(header,\s*["']ue:language["']\)/u)
  assert.match(rootRoute, /lang=\{lang\}/u)
  assert.match(rootRoute, /data-ssr-auth=\{ssrAuthMarker\}/u)
  assert.match(hydration, /window\.__APP_HYDRATED\s*=\s*true/u)

  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/dashboard["']/u)
  assert.match(spec, /name:\s*["']ue:language["']/u)
  assert.match(spec, /window\.localStorage\.setItem\(["']ue:language["']/u)
  assert.match(spec, /window\.__APP_HYDRATED\s*===\s*true/u)
  assert.match(spec, /data-ssr-auth/u)
  assert.match(spec, /serverLanguage/u)
  assert.match(spec, /hydrationDiagnostics/u)
  assert.match(spec, /rawTranslationKeys\.server/u)
  assert.match(spec, /rawTranslationKeys\.client/u)
  assert.match(spec, /new DOMParser\(\)\.parseFromString/u)
  assert.match(
    spec,
    /querySelectorAll<HTMLElement>\([\s\S]*?aria-label[\s\S]*?aria-description[\s\S]*?alt/u
  )
  assert.match(spec, /a\[href="\/news"\]:visible/u)
  assert.match(spec, /await newsLink\.click\(\)/u)
  assert.match(spec, /toHaveURL\(\/\\\/news\$\/u\)/u)
  assert.match(spec, /University news/u)
  assert.match(spec, /Новости университета/u)
  assert.match(spec, /const newsResponse = await page\.reload\(/u)
  assert.match(spec, /newsResponse\?\.status\(\)\)\.toBe\(200\)/u)
  assert.match(spec, /newsResponse\?\.headers\(\)\["content-type"\][\s\S]*?text\/html/u)
  assert.match(spec, /newsServerLanguage[\s\S]*?\.toBe\(language\)/u)
  assert.match(spec, /newsRawTranslationKeys\.server/u)
  assert.match(spec, /newsRawTranslationKeys\.client/u)
  assert.match(spec, /spaTranslationKeys\.client/u)
  assert.match(spec, /Russian dashboard SSR hydrates and preserves i18n across News navigation/u)
  assert.match(spec, /English dashboard SSR hydrates and preserves i18n across News navigation/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|page\.request/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|warn|error)/u)
})
