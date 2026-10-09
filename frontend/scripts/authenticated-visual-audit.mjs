/**
 * authenticated-visual-audit.mjs — authenticated per-page visual audit
 * the SSR migration arc started in W125.
 *
 * Verifies authenticated SSR routes through the real Caddy → Node SSR →
 * gateway → backend chain, then adds axe-core a11y assertions per route.
 * /dashboard is
 * the first target (highest traffic; W128 SSR enabled it).
 *
 * Per-route flow:
 *   1. JWKS pre-check (RS256 keys must exist) — same as wave137.
 *   2. API login + JWT validation (alg=RS256 + payload claims) — same as wave137.
 *   3. Open fresh page per route (W129 §Honesty `new_page` workaround).
 *   4. Navigate + wait for domcontentloaded + 1500ms hydration settle.
 *   5. Run axe-core scan (legacy mode for WebKit safety; WCAG 2.0/2.1/2.2 AA).
 *   6. Filter violations to critical+serious.
 *   7. Capture enhanced sidecar JSON: HTTP status + console + axe violations.
 *
 * LHCI numerical perf measurement is intentionally NOT in this script —
 * `npm run lhci:windows` (W120 SW1) already does that against VITE_LHCI=true
 * dist via vite preview at 4174. The two environments are different by
 * design:
 *   - This script: authed Docker chain (Caddy → SSR → backend) — real prod path
 *   - lhci-windows-fallback: VITE_LHCI bypass build, vite preview — perf gates
 * Audit doc combines findings from both into a unified per-page report.
 *
 * ## Usage
 *
 *   node ./scripts/authenticated-visual-audit.mjs
 *
 *   # Subset of routes:
 *   ROUTES=/dashboard,/events node ./scripts/authenticated-visual-audit.mjs
 *
 *   # Override origin / credentials:
 *   ORIGIN=http://localhost \
 *     TEST_EMAIL=test@university.dev \
 *     TEST_PASSWORD=TestPass@2024x \
 *     node ./scripts/authenticated-visual-audit.mjs
 *
 * ## Exit codes
 *
 *   0: all routes scanned cleanly (HTTP 200, no runtime errors, no critical/serious axe violations)
 *   1: JWKS pre-check failed OR login failed OR a route returned non-200
 *   2: hydration errors detected
 *   3: JWT alg !== "RS256" (W137 SW1 backend RS256 enablement broken)
 *   4: JWKS returned 0 keys (backend RSA key not loaded)
 *   5: critical or serious axe violations found
 *   6: console/page errors or failed subresource/API requests detected
 */

import { Buffer } from "node:buffer"
import { mkdir, mkdtemp, realpath, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

import { loginBrowserContext } from "./visual-smoke-auth.mjs"
import {
  classifyAuthenticatedAuditSummaries,
  requestFailureRecord,
} from "./visual-smoke-contract.mjs"

// Inject the audited, locally installed axe-core bundle as an init script.
// Playwright evaluates init scripts before page code and independently of the
// document CSP, avoiding both remote CDN trust and runtime eval().
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../node_modules/axe-core/axe.min.js"
)

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")
const CHECKOUT_ROOT = path.resolve(PROJECT_ROOT, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const TEST_EMAIL = process.env.TEST_EMAIL ?? "test@university.dev"
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? "TestPass@2024x"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/authenticated-visual-audit"
)

// The default messenger audit covers the real empty/list state. A detail route
// must be supplied with ROUTES only when a valid seeded chat ID is available;
// deliberately invalid placeholder IDs would turn expected 422 responses into
// false-positive runtime noise.
const DEFAULT_ROUTES = [
  "/dashboard",
  "/events",
  "/news",
  "/schedule",
  "/profile",
  "/settings",
  "/map",
  "/activity",
  "/messenger",
]
const DEFAULT_ROUTE_SET = new Set(DEFAULT_ROUTES)
const SEEDED_CHAT_DETAIL_ROUTE =
  /^\/messenger\/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu

// Normalize each route — accept both "/dashboard" and "dashboard" forms.
// MSYS path conversion on Windows Git Bash mangles leading-slash env values
// ("ROUTES=/dashboard" becomes "C:/Program Files/Git/dashboard"), so callers
// can pass without leading slash and we re-add it here. (Same workaround as
// lhci-windows-fallback.mjs `normalizePath` from W120 SW1.)
function normalizeRoute(p) {
  if (typeof p !== "string") return null
  const trimmed = p.trim()
  if (!trimmed) return null
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`
}

export function parseAuthenticatedVisualRoutes(environment = process.env) {
  const configuredRoutes = environment.ROUTES
  if (configuredRoutes !== undefined && typeof configuredRoutes !== "string") {
    throw new Error("ROUTES contains an unsupported application path")
  }

  // W140 SW4 iter7 fix: an empty workflow_dispatch value falls through to the
  // original defaults. MSYS callers may omit leading slashes; normalize those
  // before matching against the exact route allowlist.
  const routesEnv = configuredRoutes?.trim()
  const routes = routesEnv ? routesEnv.split(",").map(normalizeRoute) : [...DEFAULT_ROUTES]

  if (
    routes.length === 0 ||
    routes.some(
      (route) =>
        route === null || (!DEFAULT_ROUTE_SET.has(route) && !SEEDED_CHAT_DETAIL_ROUTE.test(route))
    )
  ) {
    throw new Error("ROUTES contains an unsupported application path")
  }

  return routes
}

const SUPPORTED_LOCALES = ["en", "ru"]
const SUPPORTED_THEMES = ["light", "dark"]

function parseList(value, fallback, name, allowedValues) {
  const raw = typeof value === "string" && value.trim() ? value : fallback
  const values = raw.split(",").map((item) => item.trim())
  if (
    values.length === 0 ||
    values.some((item) => !item) ||
    new Set(values).size !== values.length ||
    values.some((item) => !allowedValues.includes(item))
  ) {
    throw new Error(`${name} must be a comma-separated list of supported, unique values`)
  }
  return values
}

function parseWidths(value, fallback = "390,768,1440") {
  const raw = typeof value === "string" && value.trim() ? value : fallback
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

function isOutsideDirectory(directory, candidate) {
  const relativePath = path.relative(path.resolve(directory), path.resolve(candidate))
  return (
    relativePath === ".." ||
    relativePath.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativePath)
  )
}

async function assertPrivateOutputDirectory(outputDirectory, checkoutRoot = CHECKOUT_ROOT) {
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
  const realCheckout = await realpath(checkoutRoot)
  if (!isOutsideDirectory(realCheckout, realOutput)) {
    throw new Error("Matrix capture OUT_DIR must resolve outside the checkout")
  }
}

export function parseAuthenticatedVisualCaptureMatrix(
  environment = process.env,
  { checkoutRoot = CHECKOUT_ROOT } = {}
) {
  // Validate requested routes in legacy and matrix modes alike. This helper is
  // intentionally environment-parameterized so contract tests exercise the
  // caller's exact ROUTES value without opening a browser or making a request.
  parseAuthenticatedVisualRoutes(environment)
  const enabled = environment.VISUAL_CAPTURE_MATRIX
  if (enabled === undefined || enabled === "" || enabled === "0") return null
  if (enabled !== "1") throw new Error("VISUAL_CAPTURE_MATRIX must be 1 when enabled")

  const originValue = environment.ORIGIN ?? "http://localhost"
  let origin
  try {
    origin = new URL(originValue)
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

  const outputValue = environment.OUT_DIR
  if (typeof outputValue !== "string" || !path.isAbsolute(outputValue)) {
    throw new Error("Matrix capture requires an absolute caller-selected OUT_DIR")
  }
  const outputDir = path.resolve(outputValue)
  if (!isOutsideDirectory(checkoutRoot, outputDir)) {
    throw new Error("Matrix capture OUT_DIR must be outside the checkout")
  }

  const sourceSha = environment.SOURCE_SHA ?? environment.GITHUB_SHA
  if (typeof sourceSha !== "string" || !/^[0-9a-f]{40}$/iu.test(sourceSha)) {
    throw new Error("Matrix capture requires a 40-character SOURCE_SHA or GITHUB_SHA")
  }
  if (typeof environment.TEST_EMAIL !== "string" || !environment.TEST_EMAIL.trim()) {
    throw new Error("Matrix capture requires an explicit synthetic TEST_EMAIL")
  }
  if (typeof environment.TEST_PASSWORD !== "string" || !environment.TEST_PASSWORD.trim()) {
    throw new Error("Matrix capture requires an explicit synthetic TEST_PASSWORD")
  }

  const locales = parseList(
    environment.VISUAL_LOCALES,
    "en,ru",
    "VISUAL_LOCALES",
    SUPPORTED_LOCALES
  )
  const themes = parseList(
    environment.VISUAL_THEMES,
    "light,dark",
    "VISUAL_THEMES",
    SUPPORTED_THEMES
  )
  const widths = parseWidths(environment.VISUAL_WIDTHS)
  const heightValue = environment.VISUAL_HEIGHT ?? "800"
  if (!/^\d+$/u.test(heightValue)) {
    throw new Error("VISUAL_HEIGHT must be an integer CSS-pixel height")
  }
  const height = Number(heightValue)
  if (height < 600 || height > 1600) {
    throw new Error("VISUAL_HEIGHT must be from 600 through 1600")
  }
  return {
    mode: "authenticated-visual-matrix",
    origin: origin.origin,
    outputDir,
    sourceSha: sourceSha.toLowerCase(),
    locales,
    themes,
    widths,
    height,
  }
}

export function buildAuthenticatedCaptureBasename(routePath, captureConfig = null) {
  const route = safeFilename(routePath)
  if (!captureConfig) return route
  return `${route}_${captureConfig.locale}_${captureConfig.theme}_w${captureConfig.width}`
}

export function createAuthenticatedLoginSidecar(loginResult) {
  return {
    loginVerified: true,
    injectedCookieCount: loginResult.cookies.length,
    cookieNames: loginResult.cookies.map((cookie) => cookie.name),
    jwtAlgorithm: loginResult.jwtAlgorithm,
  }
}

export function createAuthenticatedCaptureMetadata(
  captureConfig = null,
  {
    sourceSha = null,
    visualConfigurationMatches = null,
    visualConfigurationError = null,
    screenshotPath = null,
  } = {}
) {
  return {
    captureMode: captureConfig ? "authenticated-live-matrix" : "authenticated-axe-audit",
    sourceSha,
    locale: captureConfig?.locale ?? null,
    theme: captureConfig?.theme ?? null,
    viewport: captureConfig
      ? { width: captureConfig.width, height: captureConfig.height }
      : { width: 1280, height: 800 },
    visualConfigurationMatches,
    visualConfigurationError,
    screenshotPath: screenshotPath ? path.basename(screenshotPath) : null,
  }
}

export async function createAuthenticatedCaptureRunDirectory(outputRoot) {
  await mkdir(outputRoot, { recursive: true })
  return mkdtemp(path.join(outputRoot, "run-"))
}

function safeAuditUrl(value) {
  try {
    const parsed = new URL(value, ORIGIN)
    return `${parsed.origin}${parsed.pathname}`
  } catch {
    return "[invalid-url]"
  }
}

function redactDiagnostic(value) {
  if (typeof value !== "string") return value
  return value
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/giu, "[redacted-email]")
    .replace(/\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\b/gu, "[redacted-token]")
    .replace(/https?:\/\/[^\s"'<>]+/giu, (url) => safeAuditUrl(url))
    .replace(
      /\b(sub|jti|password|access_token|refresh_token)\s*[:=]\s*("[^"]*"|'[^']*'|[^\s,}]+)/giu,
      "$1=[redacted]"
    )
}

async function setStudentCapturePreferences(context, captureConfig) {
  const origin = new URL(ORIGIN)
  await context.addCookies(
    [
      { name: "ue:language", value: captureConfig.locale },
      { name: "ue-mode", value: captureConfig.theme },
    ].map(({ name, value }) => ({
      name,
      value,
      domain: origin.hostname,
      path: "/",
      secure: origin.protocol === "https:",
      sameSite: "Lax",
    }))
  )
}

async function verifySyntheticStudent(context) {
  const response = await context.request.get(new URL("/api/v1/users/me", ORIGIN).toString())
  if (response.status() !== 200) {
    throw new Error(`Matrix account profile check failed: HTTP ${response.status()}`)
  }
  const profile = await response.json()
  if (
    profile.role !== "student" ||
    typeof profile.email !== "string" ||
    profile.email.toLowerCase() !== TEST_EMAIL.toLowerCase()
  ) {
    throw new Error("Matrix account must resolve to the explicitly configured student profile")
  }
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

function decodeJwtUnverified(token) {
  const parts = token.split(".")
  if (parts.length !== 3) {
    throw new Error(`Malformed JWT: expected 3 parts, got ${parts.length}`)
  }
  const decode = (b64) =>
    JSON.parse(Buffer.from(b64.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8"))
  return { header: decode(parts[0]), payload: decode(parts[1]) }
}

class RS256Error extends Error {
  constructor(message) {
    super(message)
    this.name = "RS256Error"
  }
}

async function checkJwksEndpoint() {
  // The backend publishes one RSA JWKS at /.well-known/jwks.json
  // (app/api/well_known.py). Temporal fetches it via TEMPORAL_JWT_KEY_SOURCE1
  // and the gateway, ws-hub and file-processor verify tokens against it.
  const jwksUrl = `${ORIGIN}/.well-known/jwks.json`
  console.log("→ JWKS pre-check: GET /.well-known/jwks.json")
  const resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    throw new Error(`JWKS endpoint unreachable: HTTP ${resp.status}.`)
  }
  const jwks = await resp.json()
  if (!jwks.keys || jwks.keys.length === 0) {
    throw new Error(`JWKS endpoint returned 0 keys.`)
  }
  const rs256Keys = jwks.keys.filter((k) => k.alg === "RS256")
  if (rs256Keys.length === 0) {
    throw new Error(`JWKS has ${jwks.keys.length} keys but NONE with alg=RS256.`)
  }
  // Require RSA key material (kty + n + e) so a key-less response cannot
  // false-pass this check.
  const rsaWithMaterial = rs256Keys.filter(
    (k) => k.kty === "RSA" && typeof k.n === "string" && typeof k.e === "string"
  )
  if (rsaWithMaterial.length === 0) {
    throw new Error(
      `JWKS has ${rs256Keys.length} RS256 key(s) but NONE include n+e material ` +
        `(is the backend RSA key loaded?).`
    )
  }
  console.log(`✓ JWKS healthy: ${rsaWithMaterial.length} RS256 key(s) with n+e material`)
  return jwks
}

async function performLogin(context) {
  console.log("→ API login: POST /api/v1/auth/login/json")
  const { cookies, cookieJar } = await loginBrowserContext({
    context,
    origin: ORIGIN,
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  })
  const accessTokenValue = cookieJar.get("access_token_v2")

  const { header, payload } = decodeJwtUnverified(accessTokenValue)
  if (header.alg !== "RS256") {
    throw new RS256Error(`JWT alg=${header.alg}, expected "RS256".`)
  }
  if (payload.aud !== "university-ecosystem-api") {
    throw new Error(
      `JWT audience ${redactDiagnostic(String(payload.aud))} did not match the expected API audience.`
    )
  }

  console.log(`✓ Login OK; browser context holds ${cookies.length} cookies`)
  return {
    cookies,
    jwtAlgorithm: header.alg,
  }
}

/**
 * Per-route audit: navigate + console capture + axe-core scan.
 *
 * Runs the authenticated smoke shape, then layers axe-core on top after
 * settle. Returns an enhanced result that includes
 * `axeViolations` + `axeViolationCount`.
 */
async function auditRoute(page, routePath, outDir, captureConfig = null, sourceSha = null) {
  const consoleMessages = []
  const networkRequests = []
  const networkFailures = []

  const consoleHandler = (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() })
  }
  const pageErrorHandler = (err) => {
    consoleMessages.push({ type: "pageerror", text: err.message })
  }
  const requestHandler = (req) => {
    networkRequests.push({ method: req.method(), url: safeAuditUrl(req.url()) })
  }
  const responseHandler = (res) => {
    const responseUrl = safeAuditUrl(res.url())
    const idx = networkRequests.findLastIndex((r) => r.url === responseUrl && !("status" in r))
    if (idx >= 0) networkRequests[idx].status = res.status()
  }
  const requestFailedHandler = (request) => {
    const failure = requestFailureRecord(request)
    networkFailures.push({
      ...failure,
      url: safeAuditUrl(failure.url),
      errorText: redactDiagnostic(failure.errorText),
    })
  }

  page.on("console", consoleHandler)
  page.on("pageerror", pageErrorHandler)
  page.on("request", requestHandler)
  page.on("response", responseHandler)
  page.on("requestfailed", requestFailedHandler)

  const targetUrl = new URL(routePath, ORIGIN).toString()
  let httpStatus = null
  let finalUrl = null
  let navError = null
  let axeViolations = []
  let axeError = null
  let visualConfigurationMatches = captureConfig ? false : null
  let visualConfigurationError = null
  let screenshotPath = null

  // emulateMedia + reducedMotion settles Framer Motion at end-state for
  // axe-core sampling (W113 SW1 + W114 SW2b + W115 SW1 pattern).
  await page.emulateMedia({
    reducedMotion: "reduce",
    ...(captureConfig ? { colorScheme: captureConfig.theme } : {}),
  })
  if (captureConfig) {
    await page.setViewportSize({ width: captureConfig.width, height: captureConfig.height })
    await page.addInitScript((preferences) => {
      try {
        localStorage.setItem("ue:language", preferences.locale)
        localStorage.setItem("ue-mode", preferences.theme)
      } catch {
        // The SSR preference cookies remain authoritative for this navigation.
      }
    }, captureConfig)
  }
  await page.addInitScript({ path: AXE_SOURCE_PATH })

  try {
    // W145 SW1 — per-step console.log markers (with route prefix) around
    // each blocking step. Captured in workflow stdout via Playwright's
    // process stdout. Diagnostic for (z) #21 — the 24-min CI hang in W144
    // SW1 iter 2 CI run 25739831369 on /login. The marker that DOESN'T
    // log identifies the exact unbounded-wait step.
    console.log(`[${routePath}] before-goto`)
    const resp = await page.goto(new URL(routePath, ORIGIN).toString(), {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()
    console.log(`[${routePath}] after-goto status=${httpStatus} path=${safeAuditUrl(finalUrl)}`)

    // 1500ms hydration + Framer Motion + React Query observers settle.
    // Same buffer wave137 uses; axe-core needs final-state DOM.
    console.log(`[${routePath}] before-waitTimeout`)
    await page.waitForTimeout(1500)
    console.log(`[${routePath}] after-waitTimeout`)

    if (captureConfig) {
      const browserState = await page.evaluate(() => ({
        locale: globalThis.document.documentElement.getAttribute("lang"),
        theme: globalThis.document.documentElement.dataset.colorScheme,
        width: globalThis.innerWidth,
        height: globalThis.innerHeight,
      }))
      visualConfigurationMatches =
        browserState.locale === captureConfig.locale &&
        browserState.theme === captureConfig.theme &&
        browserState.width === captureConfig.width &&
        browserState.height === captureConfig.height
      if (!visualConfigurationMatches) {
        visualConfigurationError = "requested_locale_theme_or_viewport_not_active"
      }
    }

    // Scope axe to the stable main landmark; heavy routes get a larger bound.
    const HEAVY_ROUTES = new Set(["/dashboard", "/map", "/activity"])
    const axeTimeoutMs = HEAVY_ROUTES.has(routePath) ? 90_000 : 60_000

    try {
      const INJECT_TIMEOUT_MS = 30_000
      console.log(`[${routePath}] before-axe-ready timeout-ms=${INJECT_TIMEOUT_MS}`)
      await page.waitForFunction(() => typeof globalThis.axe?.run === "function", undefined, {
        timeout: INJECT_TIMEOUT_MS,
      })
      console.log(`[${routePath}] after-axe-ready`)

      const axeRunOptions = {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
        },
        rules: {
          "color-contrast": { enabled: false },
          "color-contrast-enhanced": { enabled: false },
          region: { enabled: false },
          "landmark-one-main": { enabled: false },
          "landmark-no-duplicate-banner": { enabled: false },
          "landmark-no-duplicate-contentinfo": { enabled: false },
          "landmark-no-duplicate-main": { enabled: false },
          "landmark-unique": { enabled: false },
          "page-has-heading-one": { enabled: false },
          "frame-title": { enabled: false },
          "frame-tested": { enabled: false },
          "scrollable-region-focusable": { enabled: false },
        },
      }

      console.log(`[${routePath}] before-axeRun timeout-ms=${axeTimeoutMs}`)
      let axeTimeout
      let results
      try {
        results = await Promise.race([
          page.evaluate(async (options) => {
            // `window.axe` is the eval-injected global from the page.evaluate
            // above. Evaluated inside browser context; ESLint Node-side
            // `no-undef` doesn't apply because Playwright stringifies + ships
            // this fn to the page.
            // eslint-disable-next-line no-undef
            const mainEl = document.querySelector("#main-content")
            // eslint-disable-next-line no-undef
            const scopeContext = mainEl ?? document
            // eslint-disable-next-line no-undef
            return await window.axe.run(scopeContext, options)
          }, axeRunOptions),
          new Promise((_, reject) => {
            axeTimeout = setTimeout(
              () => reject(new Error(`axe-analyze-timeout-${axeTimeoutMs / 1000}s`)),
              axeTimeoutMs
            )
          }),
        ])
      } finally {
        if (axeTimeout) clearTimeout(axeTimeout)
      }
      console.log(`[${routePath}] after-axeRun violations=${results?.violations?.length ?? 0}`)
      axeViolations = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious"
      )
    } catch (err) {
      axeError = err.message
    }
  } catch (err) {
    navError = err
  }

  page.off("console", consoleHandler)
  page.off("pageerror", pageErrorHandler)
  page.off("request", requestHandler)
  page.off("response", responseHandler)
  page.off("requestfailed", requestFailedHandler)

  const errors = consoleMessages.filter((m) => m.type === "error" || m.type === "pageerror")
  const failedNetworkRequests = networkRequests.filter(
    (request) => typeof request.status === "number" && request.status >= 400
  )

  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") || m.text.includes("Hydration") || m.text.includes("did not match")
  )
  const redirectedToLogin =
    finalUrl && (finalUrl.endsWith("/login") || finalUrl.includes("/login?"))

  if (
    captureConfig &&
    visualConfigurationMatches &&
    httpStatus === 200 &&
    !redirectedToLogin &&
    finalUrl &&
    new URL(finalUrl).pathname === routePath
  ) {
    const filename = `${buildAuthenticatedCaptureBasename(routePath, captureConfig)}.png`
    screenshotPath = path.join(outDir, filename)
    try {
      await page.screenshot({ path: screenshotPath, fullPage: false, timeout: 10_000 })
    } catch (error) {
      screenshotPath = null
      visualConfigurationError = `screenshot_failed:${redactDiagnostic(error.message)}`
    }
  }

  const basename = buildAuthenticatedCaptureBasename(routePath, captureConfig)
  const sidecarPath = path.join(outDir, `${basename}.json`)
  await writeFile(
    sidecarPath,
    JSON.stringify(
      {
        path: routePath,
        targetUrl: safeAuditUrl(targetUrl),
        finalUrl: finalUrl ? safeAuditUrl(finalUrl) : null,
        httpStatus,
        navigationError: navError ? redactDiagnostic(navError.message) : null,
        consoleMessages: consoleMessages.map((message) => ({
          type: message.type,
          text: redactDiagnostic(message.text),
        })),
        networkRequestCount: networkRequests.length,
        networkRequests: networkRequests.slice(0, 50),
        networkFailures,
        failedNetworkRequests,
        axeError: redactDiagnostic(axeError),
        axeViolationCount: axeViolations.length,
        axeViolations: axeViolations.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          description: violation.description,
          help: violation.help,
          helpUrl: violation.helpUrl,
          tags: violation.tags,
          nodeCount: violation.nodes.length,
          nodes: violation.nodes.slice(0, 5).map((node) => ({
            html: redactDiagnostic(node.html.slice(0, 300)),
            target: node.target,
            failureSummary: redactDiagnostic(node.failureSummary?.slice(0, 500) ?? ""),
          })),
        })),
        ...createAuthenticatedCaptureMetadata(captureConfig, {
          sourceSha,
          visualConfigurationMatches,
          visualConfigurationError,
          screenshotPath,
        }),
      },
      null,
      2
    )
  )

  return {
    path: routePath,
    httpStatus,
    finalUrl: finalUrl ? safeAuditUrl(finalUrl) : null,
    redirectedToLogin,
    consoleErrorCount: errors.length,
    failedNetworkRequestCount: failedNetworkRequests.length + networkFailures.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    axeError,
    axeViolationCount: axeViolations.length,
    sampleErrors: errors.slice(0, 3).map((e) => redactDiagnostic(e.text)),
    failedNetworkRequests: [...failedNetworkRequests, ...networkFailures],
    navError: navError ? redactDiagnostic(navError.message) : null,
    captureConfigMatches: visualConfigurationMatches,
    captureConfigError: visualConfigurationError,
    screenshotPath: screenshotPath ? path.basename(screenshotPath) : null,
  }
}

function printSummary(summaries) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(120))
  console.log("Wave 138 SW3 — visual audit (authed Docker chain + axe-core a11y)")
  console.log("=".repeat(120))
  console.log(
    `${padR("Path", 14)}${padR("HTTP", 8)}${padR("Auth", 10)}${padR("Console err", 14)}${padR(
      "Hydr err",
      12
    )}${padR("Axe viol", 12)}${padR("Net req", 10)}Final URL`
  )
  console.log("-".repeat(120))
  for (const s of summaries) {
    const auth = s.redirectedToLogin ? "REDIRECT" : "AUTHED"
    console.log(
      `${padR(s.path, 14)}${padR(s.httpStatus ?? "-", 8)}${padR(auth, 10)}${padR(
        s.consoleErrorCount,
        14
      )}${padR(s.hydrationErrorCount, 12)}${padR(s.axeViolationCount, 12)}${padR(
        s.networkRequestCount,
        10
      )}${s.finalUrl ?? "n/a"}`
    )
  }
  console.log("=".repeat(120))
}

async function main() {
  const routes = parseAuthenticatedVisualRoutes(process.env)
  // Validate the complete optional matrix before creating output, making a
  // network request, or launching Chromium. The legacy run remains unchanged.
  const captureMatrix = parseAuthenticatedVisualCaptureMatrix()
  const outputRoot = captureMatrix?.outputDir ?? OUT_DIR
  let outputDir = outputRoot
  const sourceShaCandidate = process.env.SOURCE_SHA ?? process.env.GITHUB_SHA ?? null
  const sourceSha =
    typeof sourceShaCandidate === "string" && /^[0-9a-f]{40}$/iu.test(sourceShaCandidate)
      ? sourceShaCandidate.toLowerCase()
      : null

  console.log(`Wave 138 SW3 — visual audit (authed Docker chain + axe-core)`)
  console.log(`  Origin: ${new URL(ORIGIN).origin}`)
  console.log(`  Routes: ${routes.length} (${routes.join(", ")})`)
  if (captureMatrix) {
    const captureCount =
      routes.length *
      captureMatrix.locales.length *
      captureMatrix.themes.length *
      captureMatrix.widths.length
    console.log(
      `  Matrix: ${captureCount} authenticated captures (${captureMatrix.locales.join(",")}; ${captureMatrix.themes.join(",")}; ${captureMatrix.widths.join(",")}px x ${captureMatrix.height}px)`
    )
    console.log("  Output: caller-selected private directory outside the checkout")
  } else {
    console.log(`  Output: ${outputDir}`)
  }
  console.log("")

  if (captureMatrix) {
    await assertPrivateOutputDirectory(outputRoot)
    outputDir = await createAuthenticatedCaptureRunDirectory(outputRoot)
  } else {
    await mkdir(outputDir, { recursive: true })
  }

  let jwks
  try {
    jwks = await checkJwksEndpoint()
    await writeFile(
      path.join(outputDir, "jwks.json"),
      JSON.stringify(
        {
          jwks,
          rs256KeyCount: jwks.keys.filter((k) => k.alg === "RS256").length,
          totalKeyCount: jwks.keys.length,
        },
        null,
        2
      )
    )
  } catch (err) {
    console.error(`✗ JWKS PRE-CHECK FAILED: ${err.message}`)
    process.exit(4)
  }

  // Wave 138 SW3 — use BUNDLED CHROMIUM instead of real Chrome (channel:
  // "chrome"). AxeBuilder.analyze() injects axe-core via page.evaluate(),
  // which hits the W137 Windows heavy-DOM eval wall when run against
  // /dashboard/etc. in real Chrome (Playwright + channel: "chrome" path).
  // Bundled chromium does NOT have this wall — same fix as a11y-public.spec.ts
  // (which uses Playwright's default chromium fixture, not channel: "chrome").
  // Trade-off: dist sw.js precache assumes "chrome" rendering but bundled
  // chromium is close enough for axe a11y purposes (axe scans the DOM
  // structure, not browser-specific quirks).
  const browser = await chromium.launch({ headless: true })

  const context = await browser.newContext({
    viewport: {
      width: captureMatrix?.widths[0] ?? 1280,
      height: captureMatrix?.height ?? 800,
    },
  })
  const page = await context.newPage()
  page.setDefaultTimeout(30_000)
  page.setDefaultNavigationTimeout(30_000)

  let loginResult
  try {
    loginResult = await performLogin(context)
    if (captureMatrix) await verifySyntheticStudent(context)
  } catch (err) {
    if (err instanceof RS256Error) {
      console.error(`✗ RS256 ASSERTION FAILED: ${err.message}`)
      await context.close()
      await browser.close()
      process.exit(3)
    }
    console.error(`✗ LOGIN FAILED: ${redactDiagnostic(err.message)}`)
    await context.close()
    await browser.close()
    process.exit(1)
  }

  await writeFile(
    path.join(outputDir, "login.json"),
    JSON.stringify(createAuthenticatedLoginSidecar(loginResult), null, 2)
  )

  if (captureMatrix) {
    await writeFile(
      path.join(outputDir, "matrix.json"),
      JSON.stringify(
        {
          evidenceKind: "real-authenticated-browser-no-route-mocks",
          sourceSha: captureMatrix.sourceSha,
          origin: captureMatrix.origin,
          routes,
          locales: captureMatrix.locales,
          themes: captureMatrix.themes,
          widths: captureMatrix.widths,
          height: captureMatrix.height,
          screenshots: true,
        },
        null,
        2
      )
    )
  }

  await page.close()

  const summaries = []
  const configurations = captureMatrix
    ? captureMatrix.locales.flatMap((locale) =>
        captureMatrix.themes.flatMap((theme) =>
          captureMatrix.widths.map((width) => ({
            mode: captureMatrix.mode,
            locale,
            theme,
            width,
            height: captureMatrix.height,
          }))
        )
      )
    : [null]
  for (const captureConfig of configurations) {
    if (captureConfig) await setStudentCapturePreferences(context, captureConfig)
    for (const route of routes) {
      console.log(
        `→ ${route}${captureConfig ? ` [${captureConfig.locale}/${captureConfig.theme}/${captureConfig.width}x${captureConfig.height}]` : ""}`
      )
      const routePage = await context.newPage()
      routePage.setDefaultTimeout(45_000)
      routePage.setDefaultNavigationTimeout(45_000)
      const result = await auditRoute(
        routePage,
        route,
        outputDir,
        captureConfig,
        captureMatrix?.sourceSha ?? sourceSha
      )
      await routePage.close()
      summaries.push(result)
      const glyph =
        result.httpStatus === 200 &&
        !result.redirectedToLogin &&
        !result.axeError &&
        result.axeViolationCount === 0 &&
        result.captureConfigMatches !== false &&
        (!captureConfig || Boolean(result.screenshotPath))
          ? "✓"
          : "✗"
      console.log(
        `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} axe_viol=${result.axeViolationCount}${captureConfig ? ` config=${result.captureConfigMatches ? "verified" : "failed"} screenshot=${result.screenshotPath ? "yes" : "no"}` : ""}`
      )
    }
  }

  await context.close()
  await browser.close()

  printSummary(summaries)

  const {
    failedRoutes: failed,
    hydrationIssues,
    axeErrors,
    axeIssues,
    runtimeIssues,
  } = classifyAuthenticatedAuditSummaries(summaries)
  const visualConfigurationIssues = summaries.filter(
    (summary) =>
      summary.captureConfigMatches === false || (captureMatrix && !summary.screenshotPath)
  )

  if (failed.length > 0) {
    console.error(
      `\n✗ ${failed.length}/${summaries.length} routes failed (non-200 OR redirected to /login)`
    )
    process.exit(1)
  }
  if (hydrationIssues.length > 0) {
    console.error(`\n✗ ${hydrationIssues.length}/${summaries.length} routes had hydration errors`)
    process.exit(2)
  }
  if (axeErrors.length > 0) {
    console.error(
      `\n✗ ${axeErrors.length}/${summaries.length} routes did not complete axe analysis`
    )
    console.error("  See sidecar JSON in the selected output directory for the exact axe errors.")
    process.exit(5)
  }
  if (axeIssues.length > 0) {
    console.error(
      `\n✗ ${axeIssues.length}/${summaries.length} routes had critical/serious axe violations`
    )
    console.error("  See sidecar JSON in the selected output directory for full details.")
    process.exit(5)
  }
  if (runtimeIssues.length > 0) {
    console.error(
      `\n✗ ${runtimeIssues.length}/${summaries.length} routes had console/page errors or failed network requests`
    )
    console.error("  See sidecar JSON in the selected output directory for route details.")
    process.exit(6)
  }
  if (visualConfigurationIssues.length > 0) {
    console.error(
      `\n✗ ${visualConfigurationIssues.length}/${summaries.length} captures failed requested locale/theme/viewport verification or screenshot capture`
    )
    console.error("  See private sidecar JSON in the selected output directory for details.")
    process.exit(7)
  }
  console.log(
    captureMatrix
      ? `\n✓ All ${summaries.length} authenticated matrix captures passed on source ${captureMatrix.sourceSha}`
      : `\n✓ All ${summaries.length} routes passed: HTTP 200 + 0 hydration errors + 0 axe critical/serious violations`
  )
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error("Fatal error:", redactDiagnostic(err.message))
    process.exit(1)
  })
}
