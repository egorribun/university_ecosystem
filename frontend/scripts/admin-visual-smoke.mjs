/**
 * Authenticates through the browser context, loads /dashboard to let the
 * client resolve the authoritative /users/me profile, then navigates to each
 * admin route through the app's own links. A screenshot is written only after
 * the URL, main landmark, admin-theme scope, and route-specific localized
 * heading prove that the intended admin page is rendered.
 *
 * The smoke keeps one hydrated page and uses the client router: a cold
 * full-document navigation can run route guards before the profile request
 * settles. This checks the real admin UI without changing auth behavior.
 *
 * Routes: /admin/audit, /admin/feature-flags, /admin/notifications,
 * /admin/stories, and /admin/users in English and Russian, each in light and
 * dark themes.
 *
 * Usage: node ./scripts/admin-visual-smoke.mjs
 * Prerequisites: a healthy local stack, RSA JWKS, and the seeded admin account.
 */
import { Buffer } from "node:buffer"
import { appendFile, mkdir, mkdtemp, realpath, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

import { loginBrowserContext } from "./visual-smoke-auth.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")
const CHECKOUT_ROOT = path.resolve(PROJECT_ROOT, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const TEST_EMAIL = process.env.TEST_EMAIL ?? "admin@university.dev"

export function getAdminSmokeCredentials(environment = process.env) {
  //  pragma: allowlist nextline secret
  const candidate = environment.TEST_PASSWORD
  if (typeof candidate !== "string" || candidate.trim().length === 0) {
    throw new Error("TEST_PASSWORD must be set to a non-empty password")
  }
  return {
    email: environment.TEST_EMAIL ?? "admin@university.dev",
    password: candidate,
  }
}
const OUT_DIR = path.resolve(PROJECT_ROOT, process.env.OUT_DIR ?? ".screenshots/admin-visual-smoke")

const ADMIN_ROUTES = [
  "/admin/audit",
  "/admin/feature-flags",
  "/admin/notifications",
  "/admin/stories",
  "/admin/users",
]

const THEMES = ["light", "dark"]
const LOCALES = ["en", "ru"]

function parseMatrixList(value, fallback, name, supportedValues) {
  const raw = typeof value === "string" && value.trim() ? value : fallback
  const values = raw.split(",").map((item) => item.trim())
  if (
    values.length === 0 ||
    values.some((item) => !item) ||
    new Set(values).size !== values.length ||
    values.some((item) => !supportedValues.includes(item))
  ) {
    throw new Error(`${name} must be a comma-separated list of supported, unique values`)
  }
  return values
}

function parseMatrixWidths(value) {
  const raw = typeof value === "string" && value.trim() ? value : "390,768,1440"
  const values = raw.split(",").map((item) => item.trim())
  if (values.length === 0 || values.length > 8 || values.some((item) => !/^\d+$/u.test(item))) {
    throw new Error("VISUAL_WIDTHS must contain one to eight integer CSS-pixel widths")
  }
  const widths = values.map(Number)
  if (
    new Set(widths).size !== widths.length ||
    widths.some((width) => width < 320 || width > 2560)
  ) {
    throw new Error("VISUAL_WIDTHS must contain unique widths from 320 through 2560")
  }
  return widths
}

function isOutsideCheckout(checkoutRoot, candidate) {
  const relativePath = path.relative(path.resolve(checkoutRoot), path.resolve(candidate))
  return (
    relativePath === ".." ||
    relativePath.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativePath)
  )
}

async function assertPrivateOutputDirectory(outputDirectory) {
  const resolvedOutput = path.resolve(outputDirectory)
  let ancestor = resolvedOutput
  const missingParts = []
  let realOutput
  for (;;) {
    try {
      const realAncestor = await realpath(ancestor)
      realOutput = path.resolve(realAncestor, ...missingParts)
      break
    } catch (error) {
      if (error.code !== "ENOENT") throw error
      const parent = path.dirname(ancestor)
      if (parent === ancestor) throw error
      missingParts.unshift(path.basename(ancestor))
      ancestor = parent
    }
  }
  const realCheckout = await realpath(CHECKOUT_ROOT)
  if (!isOutsideCheckout(realCheckout, realOutput)) {
    throw new Error("Matrix capture OUT_DIR must resolve outside the checkout")
  }
}

export function parseAdminVisualCaptureMatrix(
  environment = process.env,
  { checkoutRoot = CHECKOUT_ROOT } = {}
) {
  const enabled = environment.VISUAL_CAPTURE_MATRIX
  if (enabled === undefined || enabled === "" || enabled === "0") return null
  if (enabled !== "1") throw new Error("VISUAL_CAPTURE_MATRIX must be 1 when enabled")

  let origin
  try {
    origin = new URL(environment.ORIGIN ?? "http://localhost")
  } catch {
    throw new Error("ORIGIN must be a valid HTTP(S) origin for matrix capture")
  }
  if (
    !["http:", "https:"].includes(origin.protocol) ||
    origin.username ||
    origin.password ||
    origin.pathname !== "/" ||
    origin.search ||
    origin.hash
  ) {
    throw new Error("ORIGIN must be a clean HTTP(S) origin without credentials or path")
  }

  if (typeof environment.OUT_DIR !== "string" || !path.isAbsolute(environment.OUT_DIR)) {
    throw new Error("Matrix capture requires an absolute caller-selected OUT_DIR")
  }
  const outputDir = path.resolve(environment.OUT_DIR)
  if (!isOutsideCheckout(checkoutRoot, outputDir)) {
    throw new Error("Matrix capture OUT_DIR must be outside the checkout")
  }
  if (environment.GITHUB_OUTPUT) {
    throw new Error("Matrix capture must not publish its private output as a CI artifact")
  }

  const sourceSha = environment.SOURCE_SHA ?? environment.GITHUB_SHA
  if (typeof sourceSha !== "string" || !/^[0-9a-f]{40}$/iu.test(sourceSha)) {
    throw new Error("Matrix capture requires a 40-character SOURCE_SHA or GITHUB_SHA")
  }
  if (typeof environment.TEST_EMAIL !== "string" || !environment.TEST_EMAIL.trim()) {
    throw new Error("Matrix capture requires an explicit synthetic admin TEST_EMAIL")
  }
  if (typeof environment.TEST_PASSWORD !== "string" || !environment.TEST_PASSWORD.trim()) {
    throw new Error("Matrix capture requires an explicit synthetic admin TEST_PASSWORD")
  }

  const locales = parseMatrixList(environment.VISUAL_LOCALES, "en,ru", "VISUAL_LOCALES", LOCALES)
  const themes = parseMatrixList(environment.VISUAL_THEMES, "light,dark", "VISUAL_THEMES", THEMES)
  const widths = parseMatrixWidths(environment.VISUAL_WIDTHS)
  const heightValue = environment.VISUAL_HEIGHT ?? "800"
  if (!/^\d+$/u.test(heightValue)) {
    throw new Error("VISUAL_HEIGHT must be an integer CSS-pixel height")
  }
  const height = Number(heightValue)
  if (height < 600 || height > 1600) {
    throw new Error("VISUAL_HEIGHT must be from 600 through 1600")
  }

  return {
    mode: "admin-live-visual-matrix",
    evidenceKind: "real-browser-no-route-mocks",
    origin: origin.origin,
    outputDir,
    sourceSha: sourceSha.toLowerCase(),
    locales,
    themes,
    widths,
    height,
  }
}

export function buildAdminCaptureBasename(routePath, locale, theme, captureConfig = null) {
  const base = `${safeFilename(routePath)}_${locale}_${theme}`
  return captureConfig ? `${base}_w${captureConfig.width}` : base
}

const ADMIN_ROUTE_HEADINGS = {
  "/admin/audit": { en: "Secure Audit Logs", ru: "Защищённый аудит" },
  "/admin/feature-flags": {
    en: "Feature Flag Diagnostics",
    ru: "Диагностика флагов функций",
  },
  "/admin/notifications": { en: "Notification queue", ru: "Очередь уведомлений" },
  "/admin/stories": { en: "Stories management", ru: "Управление сторис" },
  "/admin/users": { en: "Users", ru: "Пользователи" },
}

function normalizeHeading(value) {
  return typeof value === "string" ? value.replace(/\s+/gu, " ").trim().toLowerCase() : ""
}

export function classifyAdminPageSnapshot({
  routePath,
  finalUrl,
  hasMainLandmark,
  hasAdminTheme,
  locale,
  documentLanguage,
  headingText,
  expectedOrigin = ORIGIN,
}) {
  const routeMatches = (() => {
    try {
      const final = new URL(finalUrl)
      return final.origin === new URL(expectedOrigin).origin && final.pathname === routePath
    } catch {
      return false
    }
  })()

  const expectedHeading = ADMIN_ROUTE_HEADINGS[routePath]?.[locale]
  const heading = normalizeHeading(headingText)
  const hasExpectedHeading =
    typeof expectedHeading === "string" && normalizeHeading(expectedHeading) === heading
  const localeMatches = documentLanguage === locale

  return {
    ready:
      routeMatches &&
      Boolean(hasMainLandmark) &&
      Boolean(hasAdminTheme) &&
      localeMatches &&
      hasExpectedHeading,
    routeMatches,
    hasMainLandmark: Boolean(hasMainLandmark),
    hasAdminTheme: Boolean(hasAdminTheme),
    localeMatches,
    hasExpectedHeading,
  }
}

export async function createAdminSmokeRunDirectory(outputRoot) {
  await mkdir(outputRoot, { recursive: true })
  return mkdtemp(path.join(outputRoot, "run-"))
}

export function isAdminCaptureSuccessful(capture) {
  return (
    LOCALES.includes(capture?.locale) &&
    capture?.bootstrapPath === "/dashboard" &&
    capture?.bootstrapHttpStatus === 200 &&
    capture?.adminRoleConfirmed === true &&
    !capture.redirectedToLogin &&
    capture.pageReadiness?.ready === true &&
    capture.pageReadiness?.themeMatches !== false &&
    capture.pageReadiness?.viewportMatches !== false &&
    typeof capture.screenshotPath === "string" &&
    capture.screenshotPath.trim() !== "" &&
    (capture.width === undefined || (Number.isInteger(capture.width) && capture.width >= 320)) &&
    (capture.height === undefined || (Number.isInteger(capture.height) && capture.height >= 600))
  )
}

function safePathname(value) {
  try {
    return new URL(value).pathname
  } catch {
    return ""
  }
}

function safeRequestUrl(value) {
  try {
    const url = new URL(value)
    return `${url.origin}${url.pathname}`
  } catch {
    return "[invalid-url]"
  }
}

function safeAdminPathname(value) {
  const pathname = safePathname(value)
  return ADMIN_ROUTES.includes(pathname) || pathname === "/login" ? pathname : null
}

export function createAdminSmokeSidecar({
  routePath,
  locale,
  theme,
  bootstrapPath,
  bootstrapHttpStatus,
  finalUrl,
  documentLanguage,
  redirectedToLogin,
  adminRoleConfirmed,
  pageReadiness,
  screenshotPath,
  consoleErrorCount,
  hydrationErrorCount,
  networkRequestCount,
  navigationError,
  width = 1280,
  height = 800,
  sourceSha = null,
  captureMode = "admin-live-default",
}) {
  const readiness = pageReadiness ?? {}
  const screenshotFilename = typeof screenshotPath === "string" ? path.basename(screenshotPath) : ""
  const safeScreenshotPath = /^[a-z0-9_-]+\.png$/iu.test(screenshotFilename)
    ? screenshotFilename
    : null
  return {
    path: ADMIN_ROUTES.includes(routePath) ? routePath : null,
    locale: LOCALES.includes(locale) ? locale : null,
    theme: THEMES.includes(theme) ? theme : null,
    bootstrapPath: bootstrapPath === "/dashboard" ? "/dashboard" : null,
    bootstrapHttpStatus,
    finalPath: safeAdminPathname(finalUrl),
    documentLanguage: LOCALES.includes(documentLanguage) ? documentLanguage : null,
    redirectedToLogin: Boolean(redirectedToLogin),
    adminRoleConfirmed: Boolean(adminRoleConfirmed),
    pageReadiness: {
      ready: readiness.ready === true,
      routeMatches: readiness.routeMatches === true,
      hasMainLandmark: readiness.hasMainLandmark === true,
      hasAdminTheme: readiness.hasAdminTheme === true,
      localeMatches: readiness.localeMatches === true,
      hasExpectedHeading: readiness.hasExpectedHeading === true,
      themeMatches: readiness.themeMatches !== false,
      viewportMatches: readiness.viewportMatches !== false,
    },
    screenshotPath: safeScreenshotPath,
    captureMode,
    evidenceKind: "real-browser-no-route-mocks",
    sourceSha:
      typeof sourceSha === "string" && /^[0-9a-f]{40}$/iu.test(sourceSha) ? sourceSha : null,
    viewport: Number.isInteger(width) && Number.isInteger(height) ? { width, height } : null,
    consoleErrorCount,
    hydrationErrorCount,
    networkRequestCount,
    navigationError: navigationError ? "navigation_failed" : null,
  }
}

export async function captureAdminScreenshot(page, pageReadiness, screenshotOptions) {
  if (!pageReadiness?.ready) return null
  await page.screenshot(screenshotOptions)
  return screenshotOptions.path
}

function safeFilename(routePath) {
  if (routePath === "/" || routePath === "") return "root"
  return (
    routePath
      .replace(/^\//, "")
      .replace(/[/?&=:]+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "") || "root"
  )
}

function decodeJwtHeader(token) {
  const parts = token.split(".")
  if (parts.length !== 3) {
    throw new Error("Malformed access token")
  }
  const decode = (b64) =>
    JSON.parse(Buffer.from(b64.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8"))
  return decode(parts[0])
}

async function checkJwksEndpoint() {
  const jwksUrl = new URL("/.well-known/jwks.json", ORIGIN)
  console.log("-> JWKS pre-check: GET /.well-known/jwks.json")
  const resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    throw new Error(`JWKS endpoint unreachable: HTTP ${resp.status}`)
  }
  const jwks = await resp.json()
  if (!jwks.keys || jwks.keys.length === 0) {
    throw new Error(`JWKS endpoint returned 0 keys`)
  }
  // Require kty=RSA + n + e (the public RSA JWKS shape).
  const rsaKeys = jwks.keys.filter(
    (k) => k.kty === "RSA" && typeof k.n === "string" && typeof k.e === "string"
  )
  if (rsaKeys.length === 0) {
    throw new Error(
      `JWKS has ${jwks.keys.length} keys but NONE with kty=RSA + n + e fields. ` +
        `Backend RSA key may not be loaded.`
    )
  }
  console.log(`OK JWKS healthy: ${rsaKeys.length} RSA key(s)`)
  return { rsaKeyCount: rsaKeys.length, totalKeyCount: jwks.keys.length }
}

async function performLogin(context, credentials) {
  console.log("-> API login: POST /api/v1/auth/login/json")
  const { cookies, cookieJar } = await loginBrowserContext({
    context,
    origin: ORIGIN,
    email: credentials.email,
    password: credentials.password,
  })
  const accessTokenValue = cookieJar.get("access_token_v2")

  const jwtHeader = decodeJwtHeader(accessTokenValue)
  console.log(`   JWT signing algorithm: ${jwtHeader.alg ?? "(missing)"}`)
  if (jwtHeader.alg !== "RS256") {
    throw new RS256Error(`JWT signing algorithm ${jwtHeader.alg ?? "(missing)"}; expected RS256`)
  }

  console.log(`OK Login OK; browser context holds ${cookies.length} cookies`)
  return { cookieCount: cookies.length, jwtAlgorithm: jwtHeader.alg }
}

async function setSmokeTheme(page, theme, { beforeNavigation = false } = {}) {
  const cookieDomain = new URL(ORIGIN).hostname
  await page.context().addCookies([
    {
      name: "ue-mode",
      value: theme,
      domain: cookieDomain,
      path: "/",
    },
  ])
  await page.emulateMedia({ colorScheme: theme })

  if (beforeNavigation) {
    await page.addInitScript((themeName) => {
      try {
        localStorage.setItem("ue-mode", themeName)
      } catch {
        // Ignore storage restrictions; the cookie and explicit class remain.
      }
    }, theme)
    return
  }

  await page.evaluate((themeName) => {
    try {
      localStorage.setItem("ue-mode", themeName)
    } catch {
      // Ignore storage restrictions; the cookie and explicit class remain.
    }
    const { document } = globalThis
    for (const element of [document.documentElement, document.body]) {
      element.classList.remove("light", "dark")
      element.classList.add(themeName)
      element.dataset.colorScheme = themeName
    }
  }, theme)
}

async function setSmokeLocale(page, locale, { beforeNavigation = false } = {}) {
  if (!LOCALES.includes(locale)) throw new Error(`Unsupported smoke locale: ${locale}`)
  const origin = new URL(ORIGIN)
  await page.context().addCookies([
    {
      name: "ue:language",
      value: locale,
      domain: origin.hostname,
      path: "/",
      secure: origin.protocol === "https:",
      sameSite: "Lax",
    },
  ])

  if (beforeNavigation) {
    await page.addInitScript(() => {
      try {
        const match = globalThis.document.cookie.match(/(?:^|;\s*)ue:language=(en|ru)(?:;|$)/u)
        if (match) globalThis.localStorage.setItem("ue:language", match[1])
      } catch {
        // The mirrored cookie still selects the SSR document language.
      }
    })
    return
  }

  await page.evaluate((language) => {
    localStorage.setItem("ue:language", language)
  }, locale)
}

function isCurrentUserResponse(response) {
  try {
    const url = new URL(response.url())
    return (
      url.origin === new URL(ORIGIN).origin &&
      url.pathname.endsWith("/api/v1/users/me") &&
      response.request().method() === "GET"
    )
  } catch {
    return false
  }
}

async function bootstrapAdminSession(page, expectedLocale) {
  const profileResponsePromise = page.waitForResponse(isCurrentUserResponse)
  const response = await page.goto(`${ORIGIN}/dashboard`, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  })
  const documentStatus = response?.status() ?? null
  const bootstrapUrl = new URL(page.url())
  if (
    documentStatus !== 200 ||
    bootstrapUrl.origin !== new URL(ORIGIN).origin ||
    bootstrapUrl.pathname !== "/dashboard"
  ) {
    throw new Error(
      `Authenticated app bootstrap failed: HTTP ${documentStatus}, final URL ${bootstrapUrl.pathname}`
    )
  }

  const profileResponse = await profileResponsePromise
  if (profileResponse.status() !== 200) {
    throw new Error(`Admin profile request failed: HTTP ${profileResponse.status()}`)
  }
  const profile = await profileResponse.json()
  if (profile.role !== "admin" || profile.email?.toLowerCase() !== TEST_EMAIL.toLowerCase()) {
    throw new Error(`Expected seeded admin profile; received role=${profile.role ?? "(missing)"}`)
  }

  await page.waitForFunction(
    (language) => globalThis.document.documentElement.getAttribute("lang") === language,
    expectedLocale,
    { timeout: 15_000 }
  )
  const documentLanguage = await page.locator("html").getAttribute("lang")
  if (documentLanguage !== expectedLocale) {
    throw new Error(
      `Requested locale ${expectedLocale} was not active after /dashboard bootstrap (document lang=${documentLanguage ?? "missing"})`
    )
  }

  let adminNavLink = page.locator('nav a[href^="/admin/"]').first()
  if (!(await adminNavLink.isVisible().catch(() => false))) {
    await page.locator('nav button[aria-controls="navbar-overflow-menu"]').click()
    adminNavLink = page.locator('#navbar-overflow-menu a[href^="/admin/"]').first()
  }
  await adminNavLink.waitFor({ state: "visible", timeout: 15_000 })
  return {
    documentPath: bootstrapUrl.pathname,
    documentStatus,
    locale: expectedLocale,
    adminRoleConfirmed: true,
  }
}

async function navigateToAdminRoute(page, routePath) {
  const origin = new URL(ORIGIN).origin
  const currentUrl = new URL(page.url())
  if (currentUrl.origin === origin && currentUrl.pathname === routePath) return

  let routeLink = page.locator(`nav a[href="${routePath}"]`).first()
  if (!(await routeLink.isVisible().catch(() => false))) {
    const overflowMenu = page.locator("#navbar-overflow-menu")
    if (!(await overflowMenu.isVisible().catch(() => false))) {
      await page.locator('nav button[aria-controls="navbar-overflow-menu"]').click()
    }
    routeLink = page.locator(`#navbar-overflow-menu a[href="${routePath}"]`)
  }

  await routeLink.waitFor({ state: "visible", timeout: 10_000 })
  await routeLink.click()
  await page.waitForURL((url) => url.origin === origin && url.pathname === routePath, {
    timeout: 15_000,
  })
}

class RS256Error extends Error {
  constructor(message) {
    super(message)
    this.name = "RS256Error"
  }
}

/**
 * Visit a single admin route in a given theme, capture screenshot + sidecar.
 * Theme switch via document.documentElement.classList.add("dark") works
 * because the app uses Tailwind v4's class-based dark mode (per
 * frontend/src/styles/tokens/admin.css:120 `.dark .admin-theme` selector).
 */
async function smokeAdminRoute(
  page,
  routePath,
  locale,
  theme,
  outDir,
  adminSession,
  captureConfig = null,
  sourceSha = null
) {
  const consoleMessages = []
  const networkRequests = []

  const consoleHandler = (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() })
  }
  const pageErrorHandler = (err) => {
    consoleMessages.push({ type: "pageerror", text: err.message })
  }
  const requestHandler = (req) => {
    networkRequests.push({ method: req.method(), url: safeRequestUrl(req.url()) })
  }
  const responseHandler = (res) => {
    const responseUrl = safeRequestUrl(res.url())
    const idx = networkRequests.findLastIndex((r) => r.url === responseUrl && !("status" in r))
    if (idx >= 0) networkRequests[idx].status = res.status()
  }

  page.on("console", consoleHandler)
  page.on("pageerror", pageErrorHandler)
  page.on("request", requestHandler)
  page.on("response", responseHandler)

  if (captureConfig) {
    await page.setViewportSize({ width: captureConfig.width, height: captureConfig.height })
  }
  await setSmokeTheme(page, theme)
  let finalUrl
  let navError = null
  let screenshotPath = null
  let hasMainLandmark = false
  let hasAdminTheme = false
  let documentLanguage
  let headingText = ""
  let viewportMatches = false
  let themeMatches = false

  try {
    await navigateToAdminRoute(page, routePath)
    const main = page.locator("main#main-content")
    await main.waitFor({ state: "visible", timeout: 15_000 })
    await main.locator("h1").first().waitFor({ state: "visible", timeout: 15_000 })
    await page.waitForTimeout(1500)

    const viewportState = await page.evaluate(() => {
      const documentTheme = globalThis.document.documentElement.dataset.colorScheme
      return {
        width: globalThis.innerWidth,
        height: globalThis.innerHeight,
        theme: documentTheme,
        hasThemeClass: documentTheme
          ? globalThis.document.documentElement.classList.contains(documentTheme)
          : false,
      }
    })
    viewportMatches =
      viewportState.width === (captureConfig?.width ?? 1280) &&
      viewportState.height === (captureConfig?.height ?? 800)
    themeMatches = viewportState.theme === theme && viewportState.hasThemeClass

    hasMainLandmark = (await main.count()) > 0
    hasAdminTheme = (await page.locator(".admin-theme").count()) > 0
    documentLanguage = (await page.locator("html").getAttribute("lang")) ?? ""
    headingText =
      (await main.locator("h1").first().textContent())?.replace(/\s+/gu, " ").trim() ?? ""
    finalUrl = page.url()
    const baseReadiness = classifyAdminPageSnapshot({
      routePath,
      finalUrl,
      hasMainLandmark,
      hasAdminTheme,
      locale,
      documentLanguage,
      headingText,
    })
    const pageReadiness = {
      ...baseReadiness,
      viewportMatches,
      themeMatches,
      ready: baseReadiness.ready && viewportMatches && themeMatches,
    }

    const filename = `${buildAdminCaptureBasename(routePath, locale, theme, captureConfig)}.png`
    const fullPath = path.join(outDir, filename)
    try {
      screenshotPath = await captureAdminScreenshot(page, pageReadiness, {
        path: fullPath,
        fullPage: false,
        timeout: 10_000,
      })
    } catch {
      console.warn(`   screenshot failed for ${routePath}/${locale}/${theme}`)
    }
  } catch (error) {
    navError = error
    finalUrl = page.url()
    documentLanguage =
      (await page
        .locator("html")
        .getAttribute("lang")
        .catch(() => "")) ?? ""
  }

  const pageReadiness = classifyAdminPageSnapshot({
    routePath,
    finalUrl,
    hasMainLandmark,
    hasAdminTheme,
    locale,
    documentLanguage,
    headingText,
  })
  const verifiedPageReadiness = {
    ...pageReadiness,
    viewportMatches,
    themeMatches,
    ready: pageReadiness.ready && viewportMatches && themeMatches,
  }
  const finalPath = safeAdminPathname(finalUrl) ?? "unrecognized"
  const redirectedToLogin = finalPath === "/login"

  page.off("console", consoleHandler)
  page.off("pageerror", pageErrorHandler)
  page.off("request", requestHandler)
  page.off("response", responseHandler)

  const errors = consoleMessages.filter(
    (message) => message.type === "error" || message.type === "pageerror"
  )
  const hydrationErrors = consoleMessages.filter((message) => {
    const text = message.text.toLowerCase()
    return (
      text.includes("hydrat") ||
      text.includes("did not match") ||
      /minified react error #\d+/u.test(text)
    )
  })
  const publicScreenshotPath = screenshotPath ? path.basename(screenshotPath) : null
  const sidecar = createAdminSmokeSidecar({
    routePath,
    locale,
    theme,
    bootstrapPath: adminSession.documentPath,
    bootstrapHttpStatus: adminSession.documentStatus,
    finalUrl,
    documentLanguage,
    redirectedToLogin,
    adminRoleConfirmed: adminSession.adminRoleConfirmed,
    pageReadiness: verifiedPageReadiness,
    screenshotPath: publicScreenshotPath,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    navigationError: navError,
    width: captureConfig?.width ?? 1280,
    height: captureConfig?.height ?? 800,
    sourceSha,
    captureMode: captureConfig ? "admin-live-visual-matrix" : "admin-live-default",
  })
  const sidecarPath = path.join(
    outDir,
    `${buildAdminCaptureBasename(routePath, locale, theme, captureConfig)}.json`
  )
  await writeFile(sidecarPath, JSON.stringify(sidecar, null, 2))

  return {
    path: routePath,
    locale,
    theme,
    width: captureConfig?.width ?? 1280,
    height: captureConfig?.height ?? 800,
    bootstrapPath: adminSession.documentPath,
    bootstrapHttpStatus: adminSession.documentStatus,
    adminRoleConfirmed: adminSession.adminRoleConfirmed,
    finalPath,
    redirectedToLogin,
    pageReadiness: verifiedPageReadiness,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    screenshotPath: publicScreenshotPath,
    navigationError: sidecar.navigationError,
  }
}

function printSummary(summaries) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(160))
  console.log("Admin visual smoke (5 verified routes x 2 locales x 2 themes = 20 captures)")
  console.log("=".repeat(160))
  console.log(
    `${padR("Path", 22)}${padR("Locale", 8)}${padR("Theme", 8)}${padR("Bootstrap /dashboard HTTP", 28)}${padR("Auth", 10)}${padR("Page", 8)}${padR("Console err", 14)}${padR("Hydr err", 11)}${padR("Net req", 10)}Screenshot`
  )
  console.log("-".repeat(160))
  for (const s of summaries) {
    const auth = s.redirectedToLogin ? "REDIRECT" : "AUTHED"
    const page = s.pageReadiness.ready ? "READY" : "FAIL"
    const ss = s.screenshotPath ? path.basename(s.screenshotPath) : "(none)"
    console.log(
      `${padR(s.path, 22)}${padR(s.locale, 8)}${padR(s.theme, 8)}${padR(s.bootstrapHttpStatus ?? "-", 28)}${padR(auth, 10)}${padR(page, 8)}${padR(s.consoleErrorCount, 14)}${padR(s.hydrationErrorCount, 11)}${padR(s.networkRequestCount, 10)}${ss}`
    )
  }
  console.log("=".repeat(160))
}

async function publishCurrentRunPath(runDirectory) {
  const outputFile = process.env.GITHUB_OUTPUT
  if (!outputFile) return

  const workspaceRoot = path.resolve(PROJECT_ROOT, "..")
  const relativeDirectory = path.relative(workspaceRoot, runDirectory)
  if (
    relativeDirectory === "" ||
    path.isAbsolute(relativeDirectory) ||
    relativeDirectory === ".." ||
    relativeDirectory.startsWith(`..${path.sep}`) ||
    /[\r\n]/u.test(relativeDirectory)
  ) {
    throw new Error("Admin smoke run output must be inside the workspace for artifact upload")
  }
  await appendFile(
    outputFile,
    `artifact_dir=${relativeDirectory.split(path.sep).join("/")}\n`,
    "utf8"
  )
}

async function main() {
  // Validate matrix options before output creation, network activity, or a
  // browser launch. Default scheduled/manual smoke behavior remains unchanged.
  const captureMatrix = parseAdminVisualCaptureMatrix()
  const credentials = getAdminSmokeCredentials()
  delete process.env.TEST_PASSWORD
  const locales = captureMatrix?.locales ?? LOCALES
  const themes = captureMatrix?.themes ?? THEMES
  const widths = captureMatrix?.widths ?? [1280]
  const captureHeight = captureMatrix?.height ?? 800
  const expectedCaptureCount = ADMIN_ROUTES.length * locales.length * themes.length * widths.length
  const outputRoot = captureMatrix?.outputDir ?? OUT_DIR
  if (captureMatrix) await assertPrivateOutputDirectory(outputRoot)
  const runDir = await createAdminSmokeRunDirectory(outputRoot)
  const metaDir = path.join(runDir, "metadata")
  await mkdir(metaDir, { recursive: true })
  if (!captureMatrix) await publishCurrentRunPath(runDir)
  const sourceShaCandidate =
    captureMatrix?.sourceSha ?? process.env.SOURCE_SHA ?? process.env.GITHUB_SHA
  const sourceSha =
    typeof sourceShaCandidate === "string" && /^[0-9a-f]{40}$/iu.test(sourceShaCandidate)
      ? sourceShaCandidate.toLowerCase()
      : null

  if (captureMatrix) {
    await writeFile(
      path.join(metaDir, "run.json"),
      JSON.stringify(
        {
          evidenceKind: captureMatrix.evidenceKind,
          sourceSha: captureMatrix.sourceSha,
          origin: captureMatrix.origin,
          routes: ADMIN_ROUTES,
          locales,
          themes,
          widths,
          height: captureHeight,
          captureMode: captureMatrix.mode,
        },
        null,
        2
      )
    )
  }

  console.log(
    captureMatrix
      ? "Admin visual matrix (real authenticated browser pages; no route mocks)"
      : "Admin visual smoke (verified localized client pages via Playwright)"
  )
  console.log(`  Origin: ${new URL(ORIGIN).origin}`)
  console.log(
    captureMatrix
      ? `  Routes/locales/themes/widths: ${ADMIN_ROUTES.length} x ${locales.length} x ${themes.length} x ${widths.length} = ${expectedCaptureCount} captures`
      : `  Routes/locales/themes: ${ADMIN_ROUTES.length} x ${locales.length} x ${themes.length} = ${expectedCaptureCount} captures`
  )
  console.log(
    captureMatrix
      ? "  Current run output: caller-selected private directory outside the checkout"
      : `  Current run output: ${path.relative(PROJECT_ROOT, runDir)}`
  )
  console.log("")

  let jwks
  try {
    jwks = await checkJwksEndpoint()
    await writeFile(
      path.join(metaDir, "jwks.json"),
      JSON.stringify(
        {
          endpointPath: "/.well-known/jwks.json",
          ...jwks,
        },
        null,
        2
      )
    )
  } catch (err) {
    credentials.password = ""
    console.error(`X JWKS PRE-CHECK FAILED: ${err.message}`)
    process.exit(4)
  }

  let browser
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true })
    console.log(`-> Browser: real Chrome (channel=chrome) headless`)
  } catch (err) {
    console.warn(`Real Chrome failed (${err.message}); falling back to bundled Chromium.`)
    browser = await chromium.launch({ headless: true })
  }

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  })
  const page = await context.newPage()
  page.setDefaultTimeout(30_000)
  page.setDefaultNavigationTimeout(30_000)

  let loginResult
  try {
    loginResult = await performLogin(context, credentials)
  } catch (err) {
    credentials.password = ""
    if (err instanceof RS256Error) {
      console.error(`X RS256 ASSERTION FAILED: ${err.message}`)
      await context.close()
      await browser.close()
      process.exit(3)
    }
    console.error(`X LOGIN FAILED: ${err.message}`)
    await context.close()
    await browser.close()
    process.exit(1)
  }
  credentials.password = ""

  await writeFile(
    path.join(metaDir, "login.json"),
    JSON.stringify(
      {
        loginVerified: true,
        cookieCount: loginResult.cookieCount,
        jwtAlgorithm: loginResult.jwtAlgorithm,
      },
      null,
      2
    )
  )

  const summaries = []
  for (const locale of locales) {
    console.log(`-> locale ${locale}: set ue:language cookie + localStorage; reload /dashboard`)
    const beforeNavigation = page.url() === "about:blank"
    await setSmokeLocale(page, locale, { beforeNavigation })
    let adminSession
    try {
      adminSession = await bootstrapAdminSession(page, locale)
    } catch (error) {
      console.error(`X ADMIN SESSION BOOTSTRAP FAILED for locale ${locale}: ${error.name}`)
      await context.close()
      await browser.close()
      process.exit(1)
    }
    for (const route of ADMIN_ROUTES) {
      for (const theme of themes) {
        for (const width of widths) {
          const captureConfig = captureMatrix
            ? { mode: captureMatrix.mode, locale, theme, width, height: captureHeight }
            : null
          console.log(`-> ${route} [${locale}/${theme}/${width}x${captureHeight}]`)
          const result = await smokeAdminRoute(
            page,
            route,
            locale,
            theme,
            runDir,
            adminSession,
            captureConfig,
            sourceSha
          )
          summaries.push(result)
          const glyph = isAdminCaptureSuccessful(result) ? "OK" : "X"
          console.log(
            `   ${glyph} bootstrap_http=${result.bootstrapHttpStatus} final=${result.finalPath || "n/a"} page=${result.pageReadiness.ready ? "verified" : "invalid"} ss=${result.screenshotPath ? "yes" : "no"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount}`
          )
        }
      }
    }
  }

  await context.close()
  await browser.close()

  printSummary(summaries)

  const failed = summaries.filter((summary) => !isAdminCaptureSuccessful(summary))
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)
  const screenshotsCaptured = summaries.filter((s) => s.screenshotPath).length

  if (failed.length > 0 || summaries.length !== expectedCaptureCount) {
    console.error(
      `\nX ${failed.length} failed capture(s); completed ${summaries.length}/${expectedCaptureCount} expected locale/route/theme combinations`
    )
    process.exit(1)
  }
  if (hydrationIssues.length > 0) {
    console.error(`\nX ${hydrationIssues.length}/${summaries.length} captures had hydration errors`)
    process.exit(2)
  }
  console.log(
    `\nOK All ${summaries.length} admin captures verified /dashboard bootstrap, requested URL, locale, main landmark, admin theme, and route heading`
  )
  console.log(
    captureMatrix
      ? `OK Screenshots: ${screenshotsCaptured}/${summaries.length} captured (${captureMatrix.sourceSha}) to private output`
      : `OK Screenshots: ${screenshotsCaptured}/${summaries.length} captured to ${path.relative(PROJECT_ROOT, runDir)}/`
  )
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error("Fatal error:", err)
    process.exit(1)
  })
}
