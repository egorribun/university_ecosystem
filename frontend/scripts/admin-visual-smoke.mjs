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
import { appendFile, mkdir, mkdtemp, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

import { loginBrowserContext } from "./visual-smoke-auth.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

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
    typeof capture.screenshotPath === "string" &&
    capture.screenshotPath.trim() !== ""
  )
}

function safePathname(value) {
  try {
    return new URL(value).pathname
  } catch {
    return ""
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
    },
    screenshotPath: safeScreenshotPath,
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
  let resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    const altUrl = new URL("/api/v1/.well-known/jwks.json", ORIGIN)
    console.log("   fallback: GET /api/v1/.well-known/jwks.json")
    resp = await fetch(altUrl)
  }
  if (resp.status !== 200) {
    throw new Error(`JWKS endpoint unreachable: HTTP ${resp.status}`)
  }
  const jwks = await resp.json()
  if (!jwks.keys || jwks.keys.length === 0) {
    throw new Error(`JWKS endpoint returned 0 keys`)
  }
  // Prefer kty=RSA + n + e per W143 polish-v2 ## Gotchas (proper RSA JWKS
  // shape, not the HMAC metadata stub at /api/v1/.well-known/jwks.json).
  const rsaKeys = jwks.keys.filter(
    (k) => k.kty === "RSA" && typeof k.n === "string" && typeof k.e === "string"
  )
  if (rsaKeys.length === 0) {
    throw new Error(
      `JWKS has ${jwks.keys.length} keys but NONE with kty=RSA + n + e fields. ` +
        `Hit the HMAC metadata stub at /api/v1/.well-known/jwks.json? Backend RSA key may not be loaded.`
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
async function smokeAdminRoute(page, routePath, locale, theme, outDir, adminSession) {
  const consoleMessages = []
  const networkRequests = []

  const consoleHandler = (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() })
  }
  const pageErrorHandler = (err) => {
    consoleMessages.push({ type: "pageerror", text: err.message })
  }
  const requestHandler = (req) => {
    networkRequests.push({ method: req.method(), url: req.url() })
  }
  const responseHandler = (res) => {
    const idx = networkRequests.findLastIndex((r) => r.url === res.url() && !("status" in r))
    if (idx >= 0) networkRequests[idx].status = res.status()
  }

  page.on("console", consoleHandler)
  page.on("pageerror", pageErrorHandler)
  page.on("request", requestHandler)
  page.on("response", responseHandler)

  await setSmokeTheme(page, theme)
  let finalUrl
  let navError = null
  let screenshotPath = null
  let hasMainLandmark = false
  let hasAdminTheme = false
  let documentLanguage
  let headingText = ""

  try {
    await navigateToAdminRoute(page, routePath)
    const main = page.locator("main#main-content")
    await main.waitFor({ state: "visible", timeout: 15_000 })
    await main.locator("h1").first().waitFor({ state: "visible", timeout: 15_000 })
    await page.waitForTimeout(1500)

    hasMainLandmark = (await main.count()) > 0
    hasAdminTheme = (await page.locator(".admin-theme").count()) > 0
    documentLanguage = (await page.locator("html").getAttribute("lang")) ?? ""
    headingText =
      (await main.locator("h1").first().textContent())?.replace(/\s+/gu, " ").trim() ?? ""
    finalUrl = page.url()
    const pageReadiness = classifyAdminPageSnapshot({
      routePath,
      finalUrl,
      hasMainLandmark,
      hasAdminTheme,
      locale,
      documentLanguage,
      headingText,
    })

    const filename = `${safeFilename(routePath)}_${locale}_${theme}.png`
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
    pageReadiness,
    screenshotPath: publicScreenshotPath,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    navigationError: navError,
  })
  const sidecarPath = path.join(outDir, `${safeFilename(routePath)}_${locale}_${theme}.json`)
  await writeFile(sidecarPath, JSON.stringify(sidecar, null, 2))

  return {
    path: routePath,
    locale,
    theme,
    bootstrapPath: adminSession.documentPath,
    bootstrapHttpStatus: adminSession.documentStatus,
    adminRoleConfirmed: adminSession.adminRoleConfirmed,
    finalPath,
    redirectedToLogin,
    pageReadiness,
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
  const credentials = getAdminSmokeCredentials()
  delete process.env.TEST_PASSWORD
  const expectedCaptureCount = ADMIN_ROUTES.length * LOCALES.length * THEMES.length
  const runDir = await createAdminSmokeRunDirectory(OUT_DIR)
  const metaDir = path.join(runDir, "metadata")
  await mkdir(metaDir, { recursive: true })
  await publishCurrentRunPath(runDir)

  console.log("Admin visual smoke (verified localized client pages via Playwright)")
  console.log(`  Origin: ${new URL(ORIGIN).origin}`)
  console.log(
    `  Routes/locales/themes: ${ADMIN_ROUTES.length} x ${LOCALES.length} x ${THEMES.length} = ${expectedCaptureCount} captures`
  )
  console.log(`  Current run output: ${path.relative(PROJECT_ROOT, runDir)}`)
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
  for (const locale of LOCALES) {
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
      for (const theme of THEMES) {
        console.log(`-> ${route} [${locale}/${theme}]`)
        const result = await smokeAdminRoute(page, route, locale, theme, runDir, adminSession)
        summaries.push(result)
        const glyph = isAdminCaptureSuccessful(result) ? "OK" : "X"
        console.log(
          `   ${glyph} bootstrap_http=${result.bootstrapHttpStatus} final=${result.finalPath || "n/a"} page=${result.pageReadiness.ready ? "verified" : "invalid"} ss=${result.screenshotPath ? "yes" : "no"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount}`
        )
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
    `\nOK All ${summaries.length} admin captures (5 routes x 2 locales x 2 themes) verified /dashboard bootstrap, requested URL, locale, main landmark, admin theme, and route heading`
  )
  console.log(
    `OK Screenshots: ${screenshotsCaptured}/${summaries.length} captured to ${path.relative(PROJECT_ROOT, runDir)}/`
  )
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error("Fatal error:", err)
    process.exit(1)
  })
}
