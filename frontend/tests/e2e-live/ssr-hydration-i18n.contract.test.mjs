import assert from "node:assert/strict"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import { createInstance } from "i18next"
import { extractSeoMetadata, matchesRequestedCatalogTitle } from "./seo-metadata.mjs"

const specUrl = new URL("./ssr-hydration-i18n.live.spec.ts", import.meta.url)
const seoMetadataUrl = new URL("./seo-metadata.mjs", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const authRouteUrl = new URL("../../src/routes/_auth.tsx", import.meta.url)
const dashboardRouteUrl = new URL("../../src/routes/_auth/dashboard.tsx", import.meta.url)
const newsRouteUrl = new URL("../../src/routes/_auth/news.index.tsx", import.meta.url)
const rootRouteUrl = new URL("../../src/routes/__root.tsx", import.meta.url)
const seoComponentUrl = new URL("../../src/components/ui/SEO.tsx", import.meta.url)
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
    seoComponent,
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
    readFile(seoComponentUrl, "utf8"),
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
  assert.match(rootRoute, /export function ActivityRootSeoFallback/u)
  assert.match(rootRoute, /<SeoReadinessProvider>/u)
  assert.match(seoComponent, /useLayoutEffect\(\(\)\s*=>\s*\{/u)
  assert.match(seoComponent, /unregister\(instanceId\)/u)
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
  assert.match(spec, /new JSDOM\(markup\)/u)
  assert.match(
    spec,
    /page\.evaluate\(\s*\(\)\s*=> document\.querySelector\("#root"\)\?\.outerHTML/u
  )
  assert.doesNotMatch(spec, /new DOMParser\(\)|page\.evaluate\(\s*\(markup\)/u)
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
  assert.match(spec, /a public route retains one localized root metadata fallback/u)
  assert.match(spec, /assertSingleRootClientHead\(page,\s*["']en["']\)/u)
  assert.match(spec, /expectedRootHeadSnapshot\(language\)/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|page\.request/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|warn|error)/u)
})

test("live acceptance verifies each finite route title against its requested locale on SSR and client", async () => {
  const [spec, dashboardPage, newsPage, seoMetadata] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(new URL("../../src/pages/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../src/pages/News.tsx", import.meta.url), "utf8"),
    readFile(seoMetadataUrl, "utf8"),
  ])
  assert.match(dashboardPage, /t\(["']dashboard:pageTitle["']\)/u)
  assert.match(newsPage, /t\(["']news:pageTitle["']\)/u)
  assert.match(spec, /from ["']\.\.\/\.\.\/src\/i18n\/locales\/en\/dashboard\.json["']/u)
  assert.match(spec, /from ["']\.\.\/\.\.\/src\/i18n\/locales\/ru\/dashboard\.json["']/u)
  assert.match(spec, /from ["']\.\.\/\.\.\/src\/i18n\/locales\/en\/news\.json["']/u)
  assert.match(spec, /from ["']\.\.\/\.\.\/src\/i18n\/locales\/ru\/news\.json["']/u)
  assert.match(spec, /expectedDocumentTitle\(language,\s*["']dashboard["']\)/u)
  assert.match(spec, /expectedDocumentTitle\(language,\s*["']news["']\)/u)
  assert.match(spec, /readDocumentTitle\(serverMarkup/u)
  assert.match(spec, /readDocumentTitle\(newsServerMarkup/u)
  assert.match(spec, /page\.title\(\)/u)
  assert.match(spec, /PAGE_TITLE_CATALOGS\[landmark\]\[language\]/u)
  assert.doesNotMatch(spec, /Object\.values\(PAGE_TITLE_CATALOGS\[landmark\]\)/u)
  assert.match(spec, /extractSeoMetadata\(markup\)/u)
  assert.match(seoMetadata, /export function matchesRequestedCatalogTitle/u)
})

const dashboardCatalogUrls = {
  en: new URL("../../src/i18n/locales/en/dashboard.json", import.meta.url),
  ru: new URL("../../src/i18n/locales/ru/dashboard.json", import.meta.url),
}

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf8"))
}

test("the finite locale-title probe catches ordinary i18next fallback without rejecting shared text", async () => {
  const [enDashboard, ruDashboard] = await Promise.all([
    readJson(dashboardCatalogUrls.en),
    readJson(dashboardCatalogUrls.ru),
  ])
  const requestedLocaleCatalogs = { en: enDashboard, ru: ruDashboard }
  const missingEnglishTitleCatalogs = globalThis.structuredClone(requestedLocaleCatalogs)
  delete missingEnglishTitleCatalogs.en.pageTitle
  const i18nextResources = {
    en: { dashboard: missingEnglishTitleCatalogs.en },
    ru: { dashboard: missingEnglishTitleCatalogs.ru },
  }

  const fallbackInstance = createInstance()
  await fallbackInstance.init({
    lng: "en",
    fallbackLng: "ru",
    supportedLngs: ["en", "ru"],
    load: "currentOnly",
    resources: i18nextResources,
    ns: ["dashboard"],
    defaultNS: "common",
    initAsync: false,
    returnNull: false,
    interpolation: { escapeValue: false },
  })

  const fallbackTitle = fallbackInstance.t("dashboard:pageTitle")
  assert.equal(fallbackTitle, ruDashboard.pageTitle)
  assert.equal(/\b[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*\b/iu.test(fallbackTitle), false)
  const fallbackDocumentTitle = fallbackTitle + " | University Ecosystem"
  assert.equal(
    matchesRequestedCatalogTitle("en", requestedLocaleCatalogs, fallbackDocumentTitle),
    false
  )
  assert.equal(
    matchesRequestedCatalogTitle("en", missingEnglishTitleCatalogs, fallbackDocumentTitle),
    false
  )
  assert.equal(
    matchesRequestedCatalogTitle("ru", requestedLocaleCatalogs, fallbackDocumentTitle),
    true
  )

  for (const language of ["en", "ru"]) {
    const localizedInstance = createInstance()
    await localizedInstance.init({
      lng: language,
      fallbackLng: "ru",
      supportedLngs: ["en", "ru"],
      load: "currentOnly",
      resources: {
        en: { dashboard: enDashboard },
        ru: { dashboard: ruDashboard },
      },
      ns: ["dashboard"],
      defaultNS: "common",
      initAsync: false,
      returnNull: false,
    })
    const localizedTitle = localizedInstance.t("dashboard:pageTitle")
    assert.equal(localizedTitle, requestedLocaleCatalogs[language].pageTitle)
    assert.equal(
      matchesRequestedCatalogTitle(
        language,
        requestedLocaleCatalogs,
        localizedTitle + " | University Ecosystem"
      ),
      true
    )
  }

  const sharedTitleCatalogs = {
    en: { pageTitle: "University" },
    ru: { pageTitle: "University" },
  }
  for (const language of ["en", "ru"]) {
    const sharedInstance = createInstance()
    await sharedInstance.init({
      lng: language,
      fallbackLng: "ru",
      supportedLngs: ["en", "ru"],
      load: "currentOnly",
      resources: {
        en: { dashboard: sharedTitleCatalogs.en },
        ru: { dashboard: sharedTitleCatalogs.ru },
      },
      ns: ["dashboard"],
      defaultNS: "common",
      initAsync: false,
      returnNull: false,
    })
    const sharedTitle = sharedInstance.t("dashboard:pageTitle")
    assert.equal(sharedTitle, "University")
    assert.equal(
      matchesRequestedCatalogTitle(
        language,
        sharedTitleCatalogs,
        sharedTitle + " | University Ecosystem"
      ),
      true
    )
  }
})

test("shared SEO metadata extraction preserves values and counts for a root head", () => {
  const markup = `<!doctype html><html><head>
    <title>University Ecosystem</title>
    <meta name="description" content="University services">
    <meta property="og:type" content="website">
    <meta property="og:title" content="University Ecosystem">
    <meta property="og:description" content="University services">
    <meta property="og:image" content="/og-image.png">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="University Ecosystem">
    <meta name="twitter:description" content="University services">
    <meta name="twitter:image" content="/og-image.png">
  </head></html>`

  assert.deepEqual(extractSeoMetadata(markup), {
    title: "University Ecosystem",
    titleCount: 1,
    metaTitle: null,
    description: "University services",
    descriptionCount: 1,
    ogType: "website",
    ogTitle: "University Ecosystem",
    ogDescription: "University services",
    ogImage: "/og-image.png",
    twitterCard: "summary_large_image",
    twitterTitle: "University Ecosystem",
    twitterDescription: "University services",
    twitterImage: "/og-image.png",
    seoMetaCounts: {
      'meta[name="title"]': 0,
      'meta[name="description"]': 1,
      'meta[property="og:type"]': 1,
      'meta[property="og:title"]': 1,
      'meta[property="og:description"]': 1,
      'meta[property="og:image"]': 1,
      'meta[name="twitter:card"]': 1,
      'meta[name="twitter:title"]': 1,
      'meta[name="twitter:description"]': 1,
      'meta[name="twitter:image"]': 1,
    },
  })
})
