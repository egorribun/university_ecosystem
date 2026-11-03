import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"
import test from "node:test"
import { createInstance } from "i18next"
import sharp from "sharp"
import { applyNodeCspToHtmlResponse } from "../../scripts/server-csp.mjs"
import { extractSeoMetadata, matchesRequestedCatalogTitle } from "./seo-metadata.mjs"
import { matchesMainSkipLinkLocale } from "./ssr-common-locale.mjs"
import { matchesNewsSearchLocale } from "./ssr-news-locale.mjs"

const specUrl = new URL("./ssr-hydration-i18n.live.spec.ts", import.meta.url)
const ssrDocumentSpecUrl = new URL("../e2e-production/ssr-document-render.spec.ts", import.meta.url)
const dashboardCatalogUrls = {
  en: new URL("../../src/i18n/locales/en/dashboard.json", import.meta.url),
  ru: new URL("../../src/i18n/locales/ru/dashboard.json", import.meta.url),
}
const newsCatalogUrls = {
  en: new URL("../../src/i18n/locales/en/news.json", import.meta.url),
  ru: new URL("../../src/i18n/locales/ru/news.json", import.meta.url),
}
const commonCatalogUrls = {
  en: new URL("../../src/i18n/locales/en/common.json", import.meta.url),
  ru: new URL("../../src/i18n/locales/ru/common.json", import.meta.url),
}

// AUD-432 (full SSR): the rendered documents are executed by the production-server spec
// (tests/e2e-production/ssr-document-render.spec.ts). This contract executes the same policy code and the
// same locale probes on real catalog text, so no assertion depends on the spec or renderer text.

test("live acceptance projects record no traces, screenshots or video, and the executed SSR spec exists", async () => {
  assert.equal(existsSync(specUrl), true, "the authenticated SSR/i18n live scenario must exist")
  assert.equal(
    existsSync(ssrDocumentSpecUrl),
    true,
    "the executed production-server document render must exist"
  )
  const { default: liveConfig } = await import("../../playwright.live.config.ts")
  const projects = Object.fromEntries(liveConfig.projects.map((project) => [project.name, project]))
  assert.ok(projects.desktop && projects.mobile, "desktop and mobile live projects must exist")
  for (const name of ["desktop", "mobile"]) {
    const use = { ...liveConfig.use, ...projects[name].use }
    assert.equal(use.trace, "off", `${name} must not record traces`)
    assert.equal(use.screenshot, "off", `${name} must not capture screenshots`)
    assert.equal(use.video, "off", `${name} must not record video`)
  }
  // Policy guards with no behavioural equivalent without the live stack: the live acceptance
  // must reach the real stack (no route, websocket or request mocking) and must not leave
  // console diagnostics that could carry account data.
  const spec = await readFile(specUrl, "utf8")
  const documentSpec = await readFile(ssrDocumentSpecUrl, "utf8")
  assert.doesNotMatch(documentSpec, /\b(?:test|describe)\.(?:skip|fixme)\s*\(/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|page\.request/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|warn|error)/u)
})

test("the SSR CSP composition executes on an HTML response and binds the nonce", () => {
  const nonce = "AAAAAAAAAAAAAAAAAAAAAA=="
  const html = applyNodeCspToHtmlResponse(
    new globalThis.Response("<!doctype html><html></html>", {
      headers: { "content-type": "text/html; charset=utf-8", etag: '"stale"' },
    }),
    nonce
  )
  assert.ok(html.headers.get("content-security-policy")?.includes(`'nonce-${nonce}'`))
  assert.ok(html.headers.get("content-security-policy-report-only")?.includes(`'nonce-${nonce}'`))
  assert.equal(html.headers.get("cache-control"), "no-store, private, max-age=0")
  assert.equal(html.headers.get("etag"), null)
  assert.equal(html.headers.get("last-modified"), null)

  const json = applyNodeCspToHtmlResponse(
    new globalThis.Response("{}", {
      headers: { "content-type": "application/json" },
    }),
    nonce
  )
  assert.equal(json.headers.get("content-security-policy"), null)
})

test("executable locale probes accept the requested catalog text and reject the other locale", async () => {
  const [enDashboard, ruDashboard, enNews, ruNews, enCommon, ruCommon] = await Promise.all([
    readJson(dashboardCatalogUrls.en),
    readJson(dashboardCatalogUrls.ru),
    readJson(newsCatalogUrls.en),
    readJson(newsCatalogUrls.ru),
    readJson(commonCatalogUrls.en),
    readJson(commonCatalogUrls.ru),
  ])
  const catalogs = {
    dashboard: { en: enDashboard, ru: ruDashboard },
    news: { en: enNews, ru: ruNews },
    common: { en: enCommon, ru: ruCommon },
  }
  const skipMarkup = (text) =>
    `<div id="root"><a class="skip-link" href="#main-content">${text}</a></div>`
  const placeholderMarkup = (text) =>
    `<div id="root"><div class="news-theme"><header><input placeholder="${text}" aria-label="${text}"></header></div></div>`

  for (const language of ["en", "ru"]) {
    const other = language === "en" ? "ru" : "en"
    const requested = catalogs.common[language].skipToMain
    const fallback = catalogs.common[other].skipToMain
    assert.notEqual(requested, fallback, "the locales must differ to prove the probe")
    assert.equal(matchesMainSkipLinkLocale(skipMarkup(requested), requested), true)
    assert.equal(matchesMainSkipLinkLocale(skipMarkup(fallback), requested), false)

    const newsText = catalogs.news[language].search.placeholder
    assert.equal(matchesNewsSearchLocale(placeholderMarkup(newsText), newsText), true)
    assert.equal(
      matchesNewsSearchLocale(placeholderMarkup(catalogs.news[other].search.placeholder), newsText),
      false
    )

    for (const landmark of ["dashboard", "news"]) {
      const title = catalogs[landmark][language].pageTitle
      const titles = {
        en: { pageTitle: catalogs[landmark].en.pageTitle },
        ru: { pageTitle: catalogs[landmark].ru.pageTitle },
      }
      assert.equal(
        matchesRequestedCatalogTitle(language, titles, `${title} | University Ecosystem`),
        true,
        `${landmark} title must match ${language}`
      )
      assert.equal(
        matchesRequestedCatalogTitle(
          language,
          titles,
          `${catalogs[landmark][other].pageTitle} | University Ecosystem`
        ),
        false,
        `${landmark} fallback title must not match ${language}`
      )
    }
  }
})

const i18nConfigUrl = new URL("../../src/i18n/config.ts", import.meta.url)
const i18nMetadataUrl = new URL("../../src/i18n/metadata.ts", import.meta.url)

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
    <meta property="og:image" content="/icon-512.png">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="University Ecosystem">
    <meta name="twitter:description" content="University services">
    <meta name="twitter:image" content="/icon-512.png">
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
    ogImage: "/icon-512.png",
    twitterCard: "summary_large_image",
    twitterTitle: "University Ecosystem",
    twitterDescription: "University services",
    twitterImage: "/icon-512.png",
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

test("static shell social images reference a decodable public PNG", async () => {
  const markup = await readFile(new URL("../../index.html", import.meta.url), "utf8")
  const metadata = extractSeoMetadata(markup)

  assert.equal(metadata.ogImage, "/icon-512.png")
  assert.equal(metadata.twitterImage, "/icon-512.png")
  assert.equal(metadata.seoMetaCounts['meta[property="og:image"]'], 1)
  assert.equal(metadata.seoMetaCounts['meta[name="twitter:image"]'], 1)

  const imageBytes = await readFile(new URL("../../public/icon-512.png", import.meta.url))
  const image = sharp(imageBytes)
  const { format, width, height } = await image.metadata()
  assert.deepEqual({ format, width, height }, { format: "png", width: 512, height: 512 })
  assert.ok((await image.raw().toBuffer()).length > 0)
})

test("SSR locale probe catches ordinary fallback that raw-key scanning misses", async () => {
  const [enNews, ruNews, i18nConfig, i18nMetadata] = await Promise.all([
    readJson(newsCatalogUrls.en),
    readJson(newsCatalogUrls.ru),
    readFile(i18nConfigUrl, "utf8"),
    readFile(i18nMetadataUrl, "utf8"),
  ])
  assert.match(i18nConfig, /fallbackLng,/u)
  assert.match(i18nMetadata, /fallbackLng.*"ru"/u)

  const catalogs = { en: enNews, ru: ruNews }
  const missingEnglishPlaceholder = globalThis.structuredClone(catalogs)
  delete missingEnglishPlaceholder.en.search.placeholder
  const fallbackInstance = createInstance()
  await fallbackInstance.init({
    lng: "en",
    fallbackLng: "ru",
    supportedLngs: ["en", "ru"],
    load: "currentOnly",
    resources: {
      en: { news: missingEnglishPlaceholder.en },
      ru: { news: missingEnglishPlaceholder.ru },
    },
    ns: ["news"],
    defaultNS: "common",
    initAsync: false,
    returnNull: false,
    interpolation: { escapeValue: false },
  })

  const fallbackPlaceholder = fallbackInstance.t("news:search.placeholder")
  assert.equal(fallbackPlaceholder, ruNews.search.placeholder)
  assert.equal(fallbackPlaceholder.includes(":"), false)
  assert.notEqual(fallbackPlaceholder, enNews.search.placeholder)
})

test("production document suite is collected without skips and rejects preview or unmanaged servers", () => {
  const cwd = fileURLToPath(new URL("../../", import.meta.url))
  const cli = fileURLToPath(new URL("../../node_modules/@playwright/test/cli.js", import.meta.url))
  const collect = (production, unmanaged) =>
    spawnSync(
      process.execPath,
      [cli, "test", "--config=playwright.ssr.config.ts", "--project=chromium", "--list"],
      {
        cwd,
        env: {
          ...process.env,
          PRODUCTION_SERVER_E2E: production,
          SKIP_WEBSERVER: unmanaged,
        },
        encoding: "utf8",
        timeout: 30_000,
      }
    )
  const preview = collect("false", "false")
  assert.notEqual(preview.status, 0)
  assert.match(preview.stderr + preview.stdout, /require PRODUCTION_SERVER_E2E=true/u)
  const unmanaged = collect("true", "true")
  assert.notEqual(unmanaged.status, 0)
  assert.match(unmanaged.stderr + unmanaged.stdout, /require the managed production server/u)
  const production = collect("true", "false")
  assert.equal(production.error, undefined)
  assert.equal(production.status, 0)
  assert.match(production.stdout, /Total: 5 tests in 1 file/u)
})
