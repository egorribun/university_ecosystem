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
 *   5. Require dashboard card content to be loaded and visually settled before capture.
 *   6. Run axe-core scan (legacy mode for WebKit safety; WCAG 2.0/2.1/2.2 AA).
 *   7. Filter violations to critical+serious.
 *   8. Capture enhanced sidecar JSON: HTTP status + console + axe violations.
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
 *   8: dashboard loaded content did not become visible and settled
 *   9: News heading, default filter, or loaded article list did not settle
 */

import { Buffer } from "node:buffer"
import { mkdir, mkdtemp, realpath, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

import { loginBrowserContext, withOwnedSessionCleanup } from "./visual-smoke-auth.mjs"
import {
  classifyAuthenticatedAuditSummaries,
  requestFailureRecord,
} from "./visual-smoke-contract.mjs"

// Inject the audited, locally installed axe-core bundle as an init script.
// Playwright evaluates init scripts before page code and independently of the
// document CSP, avoiding both remote CDN trust and runtime eval().
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repositoryRootValue = process.env.REPO_ROOT
if (
  repositoryRootValue !== undefined &&
  (!path.isAbsolute(repositoryRootValue) ||
    path.resolve(repositoryRootValue) !== repositoryRootValue)
) {
  throw new Error("REPO_ROOT must be an absolute canonical path")
}
const CHECKOUT_ROOT =
  repositoryRootValue === undefined ? path.resolve(__dirname, "..", "..") : repositoryRootValue
const PROJECT_ROOT = path.join(CHECKOUT_ROOT, "frontend")
const requireFromProject = createRequire(path.join(PROJECT_ROOT, "package.json"))
const { chromium } = requireFromProject("playwright")
const AXE_SOURCE_PATH = path.join(PROJECT_ROOT, "node_modules", "axe-core", "axe.min.js")

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

const SELECTED_VISUAL_ROUTES = new Set(["/news", "/events", "/schedule"])

export function parseAuthenticatedSelectedVisualRoute(environment = process.env) {
  const selectedRoute = environment.VISUAL_SELECTED_ROUTE
  if (selectedRoute === undefined) return null
  const routes = parseAuthenticatedVisualRoutes(environment)
  if (
    typeof selectedRoute !== "string" ||
    !SELECTED_VISUAL_ROUTES.has(selectedRoute) ||
    routes.length !== 1 ||
    routes[0] !== selectedRoute
  ) {
    throw new Error("VISUAL_SELECTED_ROUTE must match one supported single ROUTES entry")
  }
  return selectedRoute
}

export function parseAuthenticatedVisualCaptureMatrix(
  environment = process.env,
  { checkoutRoot = CHECKOUT_ROOT } = {}
) {
  // Validate requested routes in legacy and matrix modes alike. This helper is
  // intentionally environment-parameterized so contract tests exercise the
  // caller's exact ROUTES value without opening a browser or making a request.
  parseAuthenticatedVisualRoutes(environment)
  const selectedRoute = parseAuthenticatedSelectedVisualRoute(environment)
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
    ...(selectedRoute === null ? {} : { selectedRoute }),
  }
}

export function parseAuthenticatedRemoteBrowserConnection(environment = process.env) {
  const required = environment.VISUAL_REMOTE_CHROMIUM_REQUIRED
  if (required !== undefined && required !== "0" && required !== "1") {
    throw new Error("VISUAL_REMOTE_CHROMIUM_REQUIRED must be 0 or 1")
  }

  const endpointValue = environment.VISUAL_REMOTE_CHROMIUM_WS_ENDPOINT
  if (typeof endpointValue !== "string" || endpointValue.length === 0) {
    if (required === "1") {
      throw new Error("Required remote Chromium endpoint is missing")
    }
    return null
  }
  if (endpointValue !== endpointValue.trim()) {
    throw new Error("Remote Chromium endpoint is invalid")
  }

  let endpoint
  try {
    endpoint = new URL(endpointValue)
  } catch {
    throw new Error("Remote Chromium endpoint is invalid")
  }
  const endpointPath = endpoint.pathname.endsWith("/")
    ? endpoint.pathname.slice(0, -1)
    : endpoint.pathname
  const endpointSegments = endpointPath.split("/").slice(1)
  if (
    endpoint.protocol !== "ws:" ||
    endpoint.hostname !== "127.0.0.1" ||
    !endpoint.port ||
    endpoint.username !== "" ||
    endpoint.password !== "" ||
    endpoint.search !== "" ||
    endpoint.hash !== "" ||
    endpoint.pathname === "/" ||
    endpoint.pathname.length > 512 ||
    endpoint.pathname.includes("%") ||
    endpoint.pathname.includes("\\") ||
    endpointSegments.some((segment) => segment === "" || segment === "." || segment === "..") ||
    !/^\/[A-Za-z0-9._~-]+(?:\/[A-Za-z0-9._~-]+)*\/?$/u.test(endpoint.pathname) ||
    endpointValue !== endpoint.href
  ) {
    throw new Error("Remote Chromium endpoint is invalid")
  }

  const originValue = environment.ORIGIN ?? "http://localhost"
  let origin
  try {
    origin = new URL(originValue)
  } catch {
    throw new Error("Remote Chromium origin is invalid")
  }
  if (
    !["http:", "https:"].includes(origin.protocol) ||
    origin.hostname.toLowerCase() !== "localhost" ||
    !origin.port ||
    origin.username !== "" ||
    origin.password !== "" ||
    origin.pathname !== "/" ||
    origin.search !== "" ||
    origin.hash !== "" ||
    origin.origin !== originValue
  ) {
    throw new Error("Remote Chromium origin is invalid")
  }

  return {
    endpoint: endpoint.href,
    exposeNetwork: `localhost:${origin.port}`,
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

function setVisualExitCode(error, code) {
  Object.defineProperty(error, "visualExitCode", { value: code, configurable: true })
  return error
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

async function performLogin(context, ownSession) {
  console.log("→ API login: POST /api/v1/auth/login/json")
  const { cookies, cookieJar, ownedSession } = await loginBrowserContext({
    context,
    origin: ORIGIN,
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  })
  ownSession(ownedSession)
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

function authenticatedNewsStateInPage(locale) {
  const normalize = (value) => (value ?? "").replace(/\s+/gu, " ").trim()
  const isVisible = (element) => {
    if (!element) return false
    const style = globalThis.window.getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    return (
      style.display !== "none" &&
      style.visibility === "visible" &&
      Number.parseFloat(style.opacity) >= 0.999 &&
      rect.width > 0 &&
      rect.height > 0
    )
  }
  const opacityMotionActive = (element) => {
    if (!element || typeof element.getAnimations !== "function") return true
    try {
      return element.getAnimations().some((animation) => {
        if (!["pending", "running", "paused"].includes(animation.playState)) return false
        const keyframes = animation.effect?.getKeyframes?.()
        if (!Array.isArray(keyframes)) return true
        return keyframes.some((frame) => Object.hasOwn(frame, "opacity"))
      })
    } catch {
      return true
    }
  }
  const opacityPermille = (element) => {
    if (!element) return null
    const opacity = Number.parseFloat(globalThis.window.getComputedStyle(element).opacity)
    if (!Number.isFinite(opacity)) return null
    return Math.min(1000, Math.max(0, Math.round(opacity * 1000)))
  }
  const paintFailureCategory = (element) => {
    if (!element) return "missing"
    const style = globalThis.window.getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    if (style.display === "none") return "display_none"
    if (style.visibility !== "visible") return "visibility_hidden"
    if (!(rect.width > 0 && rect.height > 0)) return "zero_geometry"
    const opacity = Number.parseFloat(style.opacity)
    if (!(Number.isFinite(opacity) && opacity >= 0.999)) return "low_opacity"
    if (opacityMotionActive(element)) return "opacity_animation"
    return "none"
  }
  const activeOpacityAnimationCounts = (element) => {
    if (!element || typeof element.getAnimations !== "function") {
      return { available: false, count: null, capped: false }
    }
    try {
      const animations = element.getAnimations()
      if (!Array.isArray(animations)) {
        return { available: false, count: null, capped: false }
      }
      let count = 0
      for (const animation of animations) {
        if (!["pending", "running", "paused"].includes(animation.playState)) continue
        const keyframes = animation.effect?.getKeyframes?.()
        if (!Array.isArray(keyframes)) {
          return { available: false, count: null, capped: false }
        }
        if (keyframes.some((frame) => Object.hasOwn(frame, "opacity"))) {
          count += 1
          if (count > 9999) return { available: true, count: 9999, capped: true }
        }
      }
      return { available: true, count, capped: false }
    } catch {
      return { available: false, count: null, capped: false }
    }
  }
  const opaqueThroughLayout = (element, layout) => {
    let current = element
    while (current) {
      const style = globalThis.window.getComputedStyle(current)
      if (
        style.display === "none" ||
        style.visibility !== "visible" ||
        !(Number.parseFloat(style.opacity) >= 0.999) ||
        opacityMotionActive(current)
      ) {
        return false
      }
      if (current === layout) return true
      current = current.parentElement
    }
    return false
  }

  const heading = globalThis.document.querySelector("h1")
  const headingPattern =
    locale === "ru" ? /^Новости университета\s*\d*$/u : /^University news\s*\d*$/u
  const headingMatches = isVisible(heading) && headingPattern.test(normalize(heading.innerText))
  const headingBucket = !heading
    ? "missing"
    : !isVisible(heading)
      ? "not_visible"
      : headingPattern.test(normalize(heading.innerText))
        ? "expected"
        : "unexpected"
  const toolbar = globalThis.document.querySelector('[role="toolbar"]')
  const activeFilters = toolbar
    ? Array.from(toolbar.querySelectorAll('button[aria-current="page"]'))
    : []
  const expectedAllLabel = locale === "ru" ? "Все" : "All"
  const activeFilterAll =
    activeFilters.length === 1 && normalize(activeFilters[0].innerText) === expectedAllLabel
  const query = new URLSearchParams(globalThis.location.search)
  const defaultFilterUrl =
    !query.has("cat") && !query.has("q") && (!query.has("sort") || query.get("sort") === "newest")

  const layout = globalThis.document.querySelector("[data-scroll-root]")
  const layoutPaintReady = isVisible(layout) && opaqueThroughLayout(layout, layout)
  const layoutFailure = paintFailureCategory(layout)
  const section = globalThis.document.querySelector("section[aria-label]")
  const cards = section
    ? Array.from(section.querySelectorAll('article[data-testid="news-card"]'))
    : []
  const cardPainted = (card) => {
    const link = card.querySelector('h2 a[href^="/news/"]')
    return (
      isVisible(card) &&
      isVisible(link) &&
      normalize(link?.textContent).length > 0 &&
      opaqueThroughLayout(card, layout)
    )
  }
  const articlePaintReady = layoutPaintReady && cards.length > 0 && cards.every(cardPainted)
  const visibleArticleCount = cards.filter(cardPainted).length
  const diagnosticArticleFailureCategory = (card) => {
    if (!layout) return "layout_missing"
    const cardVisibilityFailure = paintFailureCategory(card)
    if (cardVisibilityFailure !== "none") return `article_${cardVisibilityFailure}`
    const link = card.querySelector('h2 a[href^="/news/"]')
    if (!link) return "article_link_missing"
    const linkVisibilityFailure = paintFailureCategory(link)
    if (linkVisibilityFailure !== "none") return `article_link_${linkVisibilityFailure}`
    if (normalize(link.textContent).length === 0) return "article_heading_empty"
    let current = card
    let isArticle = true
    let ancestorCount = 0
    while (current) {
      const failure = paintFailureCategory(current)
      if (failure !== "none") {
        return `${isArticle ? "article" : "ancestor"}_${failure}`
      }
      if (current === globalThis.document.documentElement) return "none"
      current = current.parentElement
      isArticle = false
      ancestorCount += 1
      if (ancestorCount > 128) return "ancestor_depth_limit"
    }
    return "layout_or_root_not_ancestor"
  }
  const diagnosticCountLimit = 9999
  const diagnosticCards = cards.slice(0, diagnosticCountLimit)
  const diagnosticArticleFailureCategories = diagnosticCards.map(diagnosticArticleFailureCategory)
  const firstArticleAncestorFailureCategory =
    diagnosticArticleFailureCategories[0] ?? (layout ? "no_articles" : "layout_missing")
  const diagnosticPaintedArticleCount = diagnosticArticleFailureCategories.filter(
    (category) => category === "none"
  ).length
  const layoutAnimations = activeOpacityAnimationCounts(layout)
  const layoutRect = layout?.getBoundingClientRect()
  const paintDiagnostics = {
    schema: 1,
    status: "available",
    rootHydrated: globalThis.window.__APP_HYDRATED === true,
    headingBucket,
    layoutPresent: layout !== null,
    layoutGeometryVisible: Boolean(layoutRect && layoutRect.width > 0 && layoutRect.height > 0),
    layoutOpacityPermille: opacityPermille(layout),
    layoutFailureCategory: layout === null ? "missing" : layoutFailure,
    layoutOpacityAnimationProbeAvailable: layoutAnimations.available,
    layoutActiveOpacityAnimations: layoutAnimations.count,
    layoutActiveOpacityAnimationsCapped: layoutAnimations.capped,
    domArticleCount: Math.min(cards.length, diagnosticCountLimit),
    domArticleCountCapped: cards.length > diagnosticCountLimit,
    paintedArticleCount: Math.min(diagnosticPaintedArticleCount, diagnosticCountLimit),
    paintedArticleCountCapped: cards.length > diagnosticCountLimit,
    firstArticleAncestorFailureCategory,
  }
  const hasNextPageSkeleton = Boolean(
    section &&
    Array.from(section.querySelectorAll("article")).some(
      (article) => article.getAttribute("data-testid") !== "news-card"
    )
  )
  const hasRefetchIndicator = Boolean(
    section &&
    Array.from(section.children).some((element) => element.classList.contains("animate-pulse"))
  )

  return {
    pathnameMatches: globalThis.location.pathname === "/news",
    headingMatches,
    toolbarVisible: isVisible(toolbar),
    activeFilterCount: activeFilters.length,
    activeFilterAll,
    defaultFilterUrl,
    layoutPaintReady,
    articlePaintReady,
    visibleArticleCount,
    paintDiagnostics,
    hasNextPageSkeleton,
    hasRefetchIndicator,
  }
}
export function isAuthenticatedNewsCaptureReady(state) {
  return Boolean(
    state &&
    state.pathnameMatches === true &&
    state.headingMatches === true &&
    state.toolbarVisible === true &&
    state.activeFilterCount === 1 &&
    state.activeFilterAll === true &&
    state.defaultFilterUrl === true &&
    state.layoutPaintReady === true &&
    state.articlePaintReady === true &&
    Number.isInteger(state.visibleArticleCount) &&
    state.visibleArticleCount > 0 &&
    state.hasNextPageSkeleton === false &&
    state.hasRefetchIndicator === false
  )
}

export function unavailableNewsPaintDiagnostics() {
  return {
    schema: 1,
    status: "unavailable",
    rootHydrated: null,
    headingBucket: null,
    layoutPresent: null,
    layoutGeometryVisible: null,
    layoutOpacityPermille: null,
    layoutFailureCategory: null,
    layoutOpacityAnimationProbeAvailable: null,
    layoutActiveOpacityAnimations: null,
    layoutActiveOpacityAnimationsCapped: null,
    domArticleCount: null,
    domArticleCountCapped: null,
    paintedArticleCount: null,
    paintedArticleCountCapped: null,
    firstArticleAncestorFailureCategory: null,
  }
}

async function waitForAuthenticatedNewsReady(page, locale) {
  const deadline = Date.now() + 30_000
  let previousSignature = null
  let stableSamples = 0
  let lastState = null

  while (Date.now() < deadline) {
    const remainingBeforeProbe = Math.max(0, deadline - Date.now())
    if (remainingBeforeProbe === 0) break
    const probeTimeout = "NEWS_READINESS_PROBE_TIMEOUT"
    let timer
    try {
      lastState = await Promise.race([
        page.evaluate(authenticatedNewsStateInPage, locale),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(probeTimeout), remainingBeforeProbe)
        }),
      ])
    } catch (error) {
      if (error === probeTimeout) break
      throw error
    } finally {
      if (timer !== undefined) clearTimeout(timer)
    }
    if (Date.now() >= deadline) break
    if (isAuthenticatedNewsCaptureReady(lastState)) {
      const signature = JSON.stringify([
        lastState.pathnameMatches,
        lastState.headingMatches,
        lastState.activeFilterCount,
        lastState.activeFilterAll,
        lastState.defaultFilterUrl,
        lastState.visibleArticleCount,
        lastState.layoutPaintReady,
        lastState.articlePaintReady,
        lastState.hasNextPageSkeleton,
        lastState.hasRefetchIndicator,
      ])
      stableSamples = signature === previousSignature ? stableSamples + 1 : 1
      previousSignature = signature
      if (stableSamples >= 3) {
        return {
          ready: true,
          articleCount: lastState.visibleArticleCount,
          activeFilterState: "all",
          layoutPaintReady: lastState.layoutPaintReady,
          articlePaintReady: lastState.articlePaintReady,
          paintDiagnostics: lastState.paintDiagnostics ?? unavailableNewsPaintDiagnostics(),
          error: null,
        }
      }
    } else {
      previousSignature = null
      stableSamples = 0
    }
    const remainingAfterProbe = Math.max(0, deadline - Date.now())
    const settleWaitMs = Math.min(250, remainingAfterProbe)
    if (settleWaitMs === 0) break
    await page.waitForTimeout(settleWaitMs)
  }

  return {
    ready: false,
    articleCount: Number.isInteger(lastState?.visibleArticleCount)
      ? lastState.visibleArticleCount
      : 0,
    activeFilterState: lastState?.activeFilterAll ? "all" : "unexpected",
    layoutPaintReady: lastState?.layoutPaintReady === true,
    articlePaintReady: lastState?.articlePaintReady === true,
    paintDiagnostics: lastState?.paintDiagnostics ?? unavailableNewsPaintDiagnostics(),
    error: "news_heading_filter_or_nonempty_list_not_stable",
  }
}

export function findNewsReadinessIssues(summaries) {
  return summaries.filter(
    (summary) =>
      summary.path === "/news" &&
      summary.newsReadinessRequired === true &&
      (summary.newsReady !== true ||
        summary.newsActiveFilterState !== "all" ||
        !Number.isInteger(summary.newsArticleCount) ||
        summary.newsArticleCount < 1)
  )
}

function authenticatedEventsStateInPage(locale) {
  const normalize = (value) => (value ?? "").replace(/\s+/gu, " ").trim()
  const isVisible = (element) => {
    if (!element) return false
    const style = globalThis.window.getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    return (
      style.display !== "none" &&
      style.visibility === "visible" &&
      Number.parseFloat(style.opacity) >= 0.999 &&
      rect.width > 0 &&
      rect.height > 0
    )
  }
  const expectedTitle = locale === "ru" ? "Мероприятия" : "Events"
  const heading = globalThis.document.querySelector("main h1")
  const normalizedHeadingText = heading
    ? Array.from(heading.childNodes)
        .filter((node) => node.nodeType === 3)
        .map((node) => node.textContent ?? "")
        .join("")
        .replace(/\s+/gu, " ")
        .trim()
    : ""
  const panel = globalThis.document.querySelector('#events-tabpanel[role="tabpanel"]')
  const tablist = globalThis.document.querySelector('[role="tablist"][aria-label]')
  const selectedTabs = tablist
    ? Array.from(tablist.querySelectorAll('[role="tab"][aria-selected="true"]'))
    : []
  const labelledBy = panel?.getAttribute("aria-labelledby") ?? ""
  const activeTab = labelledBy ? globalThis.document.getElementById(labelledBy) : null
  const cards = panel ? Array.from(panel.querySelectorAll('article[data-testid="event-card"]')) : []
  const visibleCardCount = cards.filter((card) => {
    const title = card.querySelector("h3")
    return isVisible(card) && isVisible(title) && normalize(title?.textContent).length > 0
  }).length
  const hasRefetchIndicator = Boolean(
    panel &&
    Array.from(panel.children).some((element) => element.classList.contains("animate-pulse"))
  )
  return {
    pathnameMatches: globalThis.location.pathname === "/events",
    headingMatches: isVisible(heading) && normalizedHeadingText === expectedTitle,
    panelVisible: isVisible(panel) && panel.getAttribute("aria-label") === expectedTitle,
    busyCleared: panel?.getAttribute("aria-busy") !== "true",
    activeTabLinked:
      selectedTabs.length === 1 &&
      activeTab === selectedTabs[0] &&
      activeTab?.getAttribute("aria-controls") === "events-tabpanel" &&
      isVisible(activeTab),
    visibleCardCount,
    hasRefetchIndicator,
  }
}

export function isAuthenticatedEventsCaptureReady(state) {
  return Boolean(
    state &&
    state.pathnameMatches === true &&
    state.headingMatches === true &&
    state.panelVisible === true &&
    state.busyCleared === true &&
    state.activeTabLinked === true &&
    Number.isInteger(state.visibleCardCount) &&
    state.visibleCardCount > 0 &&
    state.hasRefetchIndicator === false
  )
}

async function waitForAuthenticatedEventsReady(page, locale) {
  const deadline = Date.now() + 30_000
  let previousSignature = null
  let stableSamples = 0
  let lastState = null
  while (Date.now() < deadline) {
    const remainingBeforeProbe = Math.max(0, deadline - Date.now())
    if (remainingBeforeProbe === 0) break
    const probeTimeout = "EVENTS_READINESS_PROBE_TIMEOUT"
    let timer
    try {
      lastState = await Promise.race([
        page.evaluate(authenticatedEventsStateInPage, locale),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(probeTimeout), remainingBeforeProbe)
        }),
      ])
    } catch (error) {
      if (error === probeTimeout) break
      throw error
    } finally {
      if (timer !== undefined) clearTimeout(timer)
    }
    if (Date.now() >= deadline) break
    if (isAuthenticatedEventsCaptureReady(lastState)) {
      const signature = JSON.stringify([
        lastState.pathnameMatches,
        lastState.headingMatches,
        lastState.panelVisible,
        lastState.busyCleared,
        lastState.activeTabLinked,
        lastState.visibleCardCount,
        lastState.hasRefetchIndicator,
      ])
      stableSamples = signature === previousSignature ? stableSamples + 1 : 1
      previousSignature = signature
      if (stableSamples >= 3) {
        return {
          ready: true,
          cardCount: lastState.visibleCardCount,
          busyCleared: lastState.busyCleared,
          error: null,
        }
      }
    } else {
      previousSignature = null
      stableSamples = 0
    }
    const remainingAfterProbe = Math.max(0, deadline - Date.now())
    const settleWaitMs = Math.min(250, remainingAfterProbe)
    if (settleWaitMs === 0) break
    await page.waitForTimeout(settleWaitMs)
  }
  return {
    ready: false,
    cardCount: Number.isInteger(lastState?.visibleCardCount) ? lastState.visibleCardCount : 0,
    busyCleared: lastState?.busyCleared === true,
    error: "events_tabpanel_or_seeded_cards_not_stable",
  }
}

export function findEventsReadinessIssues(summaries) {
  return summaries.filter(
    (summary) =>
      summary.path === "/events" &&
      summary.eventsReadinessRequired === true &&
      (summary.eventsReady !== true ||
        !Number.isInteger(summary.eventsCardCount) ||
        summary.eventsCardCount < 1 ||
        summary.eventsReadinessError !== null)
  )
}

function authenticatedScheduleStateInPage(locale) {
  const isVisible = (element) => {
    if (!element) return false
    const style = globalThis.window.getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    return (
      style.display !== "none" &&
      style.visibility === "visible" &&
      Number.parseFloat(style.opacity) >= 0.999 &&
      rect.width > 0 &&
      rect.height > 0
    )
  }
  const expectedTitle = locale === "ru" ? "Расписание" : "Schedule"
  const expectedStudentTitle = locale === "ru" ? "Моё расписание" : "My schedule"
  const mainHeading = globalThis.document.querySelector("main h1")
  const normalizedStudentHeading = mainHeading
    ? Array.from(mainHeading.childNodes)
        .filter((node) => node.nodeType === 3)
        .map((node) => node.textContent ?? "")
        .join("")
        .replace(/\s+/gu, " ")
        .trim()
    : ""
  const studentHeadingMatches = normalizedStudentHeading === expectedStudentTitle
  const content = globalThis.document.querySelector('.skeleton-morph-content[data-loaded="true"]')
  const section = globalThis.document.querySelector('section[aria-label="' + expectedTitle + '"]')
  const errorBanner = section?.querySelector('[class*="border-error"]') ?? null
  const desktop = globalThis.innerWidth > 1280
  const grid = globalThis.document.querySelector('[role="grid"][aria-label]')
  const tablist = globalThis.document.querySelector('[role="tablist"][aria-label]')
  const selectedTabs = tablist
    ? Array.from(tablist.querySelectorAll('[role="tab"][aria-selected="true"]'))
    : []
  const selectedTab = selectedTabs.length === 1 ? selectedTabs[0] : null
  const selectedPanelId = selectedTab?.getAttribute("aria-controls") ?? ""
  const selectedPanel = selectedPanelId ? globalThis.document.getElementById(selectedPanelId) : null
  const selectedPanelHeading = selectedPanel?.querySelector("h2") ?? null
  const lessonContentRoot = desktop ? grid : selectedPanel
  const lessonCards = lessonContentRoot
    ? Array.from(lessonContentRoot.querySelectorAll('[id^="lesson-card-"]'))
    : []
  const visibleLessonCardCount = lessonCards.filter(isVisible).length
  return {
    pathnameMatches: globalThis.location.pathname === "/schedule",
    mainHeadingVisible: isVisible(mainHeading),
    studentHeadingMatches: isVisible(mainHeading) && studentHeadingMatches,
    loadedContentVisible: isVisible(content),
    errorBannerVisible: isVisible(errorBanner),
    desktop,
    viewLabelMatches: desktop
      ? isVisible(grid) && grid.getAttribute("aria-label") === expectedTitle
      : isVisible(tablist) && tablist.getAttribute("aria-label") === expectedTitle,
    visibleLessonCardCount,
    selectedDayTabCount: selectedTabs.length,
    selectedDayWeekend: selectedTab?.id === "day-tab-saturday",
    selectedDayPanelVisible:
      !desktop &&
      isVisible(selectedPanel) &&
      selectedPanel?.getAttribute("role") === "tabpanel" &&
      selectedPanel?.getAttribute("aria-labelledby") === selectedTab?.id &&
      isVisible(selectedPanelHeading),
  }
}

export function isAuthenticatedScheduleCaptureReady(state) {
  if (
    !state ||
    state.pathnameMatches !== true ||
    state.mainHeadingVisible !== true ||
    state.studentHeadingMatches !== true ||
    state.loadedContentVisible !== true ||
    state.errorBannerVisible !== false ||
    state.viewLabelMatches !== true
  ) {
    return false
  }
  if (state.desktop === true) {
    return Number.isInteger(state.visibleLessonCardCount) && state.visibleLessonCardCount > 0
  }
  return (
    state.desktop === false &&
    state.selectedDayTabCount === 1 &&
    state.selectedDayPanelVisible === true &&
    Number.isInteger(state.visibleLessonCardCount) &&
    (state.visibleLessonCardCount > 0 || state.selectedDayWeekend === true)
  )
}

async function waitForAuthenticatedScheduleReady(page, locale) {
  const deadline = Date.now() + 30_000
  let previousSignature = null
  let stableSamples = 0
  let lastState = null
  while (Date.now() < deadline) {
    const remainingBeforeProbe = Math.max(0, deadline - Date.now())
    if (remainingBeforeProbe === 0) break
    const probeTimeout = "SCHEDULE_READINESS_PROBE_TIMEOUT"
    let timer
    try {
      lastState = await Promise.race([
        page.evaluate(authenticatedScheduleStateInPage, locale),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(probeTimeout), remainingBeforeProbe)
        }),
      ])
    } catch (error) {
      if (error === probeTimeout) break
      throw error
    } finally {
      if (timer !== undefined) clearTimeout(timer)
    }
    if (Date.now() >= deadline) break
    if (isAuthenticatedScheduleCaptureReady(lastState)) {
      const signature = JSON.stringify([
        lastState.pathnameMatches,
        lastState.mainHeadingVisible,
        lastState.studentHeadingMatches,
        lastState.loadedContentVisible,
        lastState.errorBannerVisible,
        lastState.desktop,
        lastState.viewLabelMatches,
        lastState.visibleLessonCardCount,
        lastState.selectedDayTabCount,
        lastState.selectedDayWeekend,
        lastState.selectedDayPanelVisible,
      ])
      stableSamples = signature === previousSignature ? stableSamples + 1 : 1
      previousSignature = signature
      if (stableSamples >= 3) {
        return {
          ready: true,
          loaded: true,
          headingMatches: lastState.studentHeadingMatches,
          viewMode: lastState.desktop ? "desktop" : "mobile",
          lessonCardCount: lastState.visibleLessonCardCount,
          selectedDayPanelVisible: lastState.selectedDayPanelVisible,
          selectedDayWeekend: lastState.selectedDayWeekend,
          errorVisible: false,
          error: null,
        }
      }
    } else {
      previousSignature = null
      stableSamples = 0
    }
    const remainingAfterProbe = Math.max(0, deadline - Date.now())
    const settleWaitMs = Math.min(250, remainingAfterProbe)
    if (settleWaitMs === 0) break
    await page.waitForTimeout(settleWaitMs)
  }
  return {
    ready: false,
    loaded: lastState?.loadedContentVisible === true,
    headingMatches: lastState?.studentHeadingMatches === true,
    viewMode:
      lastState?.desktop === true ? "desktop" : lastState?.desktop === false ? "mobile" : "unknown",
    lessonCardCount: Number.isInteger(lastState?.visibleLessonCardCount)
      ? lastState.visibleLessonCardCount
      : 0,
    selectedDayPanelVisible: lastState?.selectedDayPanelVisible === true,
    selectedDayWeekend: lastState?.selectedDayWeekend === true,
    errorVisible: lastState?.errorBannerVisible === true,
    error: "schedule_loaded_view_or_content_not_stable",
  }
}

export function findScheduleReadinessIssues(summaries) {
  return summaries.filter((summary) => {
    if (summary.path !== "/schedule" || summary.scheduleReadinessRequired !== true) return false
    const expectedMode = summary.viewportWidth > 1280 ? "desktop" : "mobile"
    return (
      summary.scheduleReady !== true ||
      summary.scheduleLoaded !== true ||
      summary.scheduleHeadingMatches !== true ||
      summary.scheduleViewMode !== expectedMode ||
      !Number.isInteger(summary.scheduleLessonCardCount) ||
      summary.scheduleLessonCardCount < (expectedMode === "desktop" ? 1 : 0) ||
      (expectedMode === "mobile" &&
        summary.scheduleLessonCardCount === 0 &&
        summary.scheduleSelectedDayWeekend !== true) ||
      summary.scheduleErrorVisible !== false ||
      summary.scheduleReadinessError !== null ||
      (expectedMode === "mobile" && summary.scheduleSelectedDayPanelVisible !== true)
    )
  })
}

/**
 * Per-route audit: navigate + console capture + axe-core scan.
 *
 * Runs the authenticated smoke shape, then layers axe-core on top after
 * settle. Returns an enhanced result that includes
 * `axeViolations` + `axeViolationCount`.
 */
function dashboardCardsAreVisible() {
  const selectors = [".vt-dash-schedule", ".vt-dash-news", ".vt-dash-events"]
  const identityTransform = (value) => {
    if (value === "none") return true
    try {
      return new globalThis.DOMMatrixReadOnly(value).isIdentity
    } catch {
      return false
    }
  }

  return selectors.every((selector) => {
    const card = globalThis.document.querySelector(selector)
    const animatedAncestor = card?.parentElement
    const content = card?.querySelector('.skeleton-morph-content[data-loaded="true"]')
    if (!card || !animatedAncestor || !content || content.getAttribute("data-loaded") !== "true") {
      return false
    }

    const cardMotionSettled = [animatedAncestor, card].every((element) => {
      const style = globalThis.window.getComputedStyle(element)
      const opacity = Number.parseFloat(style.opacity)
      return Number.isFinite(opacity) && opacity >= 0.999 && identityTransform(style.transform)
    })
    const contentStyle = globalThis.window.getComputedStyle(content)
    const contentOpacity = Number.parseFloat(contentStyle.opacity)
    const contentVisible =
      Number.isFinite(contentOpacity) &&
      contentOpacity >= 0.999 &&
      contentStyle.display !== "none" &&
      contentStyle.visibility === "visible" &&
      content.getClientRects().length > 0
    return cardMotionSettled && contentVisible
  })
}

export function canCaptureAuthenticatedScreenshot({
  captureConfig,
  visualConfigurationMatches,
  routePath,
  httpStatus,
  redirectedToLogin,
  finalUrl,
  dashboardCardsVisible,
  newsReadinessRequired = false,
  newsReady = null,
  eventsReadinessRequired = false,
  eventsReady = null,
  scheduleReadinessRequired = false,
  scheduleReady = null,
}) {
  return Boolean(
    captureConfig &&
    visualConfigurationMatches &&
    httpStatus === 200 &&
    !redirectedToLogin &&
    finalUrl &&
    new URL(finalUrl).pathname === routePath &&
    (routePath !== "/dashboard" || dashboardCardsVisible === true) &&
    (!newsReadinessRequired || newsReady === true) &&
    (!eventsReadinessRequired || eventsReady === true) &&
    (!scheduleReadinessRequired || scheduleReady === true)
  )
}

export function findDashboardReadinessIssues(summaries) {
  return summaries.filter(
    (summary) => summary.path === "/dashboard" && summary.dashboardCardsVisible !== true
  )
}

const DIAGNOSTIC_COUNT_LIMIT = 9999
const VISUAL_CONSOLE_TYPES = ["error", "warning", "log", "info", "debug", "pageerror", "other"]
const VISUAL_CONSOLE_CLASSES = [
  "react_key_warning",
  "react_hydration",
  "react_minified_error",
  "preload_notice",
  "resource_failure",
  "react_other",
  "other",
]
const VISUAL_REQUEST_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "other"]
const VISUAL_REQUEST_ORIGINS = ["same_origin", "external", "invalid"]
const VISUAL_REQUEST_ENDPOINTS = [
  "avatar_fallback",
  "api",
  "service_worker",
  "document_news",
  "static_asset",
  "other",
]
const VISUAL_REQUEST_REASONS = [
  "aborted",
  "blocked",
  "dns",
  "timeout",
  "tls",
  "connection",
  "other_network",
  "unknown",
]

function createDiagnosticCounts(keys) {
  return Object.fromEntries(keys.map((key) => [key, 0]))
}

function incrementDiagnosticCount(counts, key) {
  if (counts[key] >= DIAGNOSTIC_COUNT_LIMIT) return true
  counts[key] += 1
  return false
}

function classifyVisualConsoleMessage(message) {
  const value = typeof message === "string" ? message.toLowerCase() : ""
  if (/each child in a list should have a unique .?key.? prop/u.test(value)) {
    return "react_key_warning"
  }
  if (/hydration|server rendered html|did not match|didn't match/u.test(value)) {
    return "react_hydration"
  }
  if (/minified react error #\d+/u.test(value)) return "react_minified_error"
  if (/preload|preloaded using link preload/u.test(value)) return "preload_notice"
  if (/failed to load resource|net::err_|resource .*failed|network .*failed/u.test(value)) {
    return "resource_failure"
  }
  if (/react|react-dom|react-router/u.test(value)) return "react_other"
  return "other"
}

function classifyVisualRequestFailure(request, expectedOrigin) {
  const method =
    typeof request?.method === "string" && VISUAL_REQUEST_METHODS.includes(request.method)
      ? request.method
      : "other"
  let parsedUrl
  try {
    parsedUrl = new URL(request?.url)
  } catch {
    return { method, origin: "invalid", endpoint: "other", reason: "unknown" }
  }

  const origin = parsedUrl.origin === expectedOrigin ? "same_origin" : "external"
  const pathname = parsedUrl.pathname
  let endpoint = "other"
  if (pathname === "/fallbacks/default_avatar.png") endpoint = "avatar_fallback"
  else if (pathname.startsWith("/api/v1/")) endpoint = "api"
  else if (pathname === "/sw.js" || pathname === "/service-worker.js") endpoint = "service_worker"
  else if (pathname === "/news") endpoint = "document_news"
  else if (/\.(?:css|html|ico|js|png|svg|webp|woff2?)$/iu.test(pathname)) {
    endpoint = "static_asset"
  }

  const errorText = typeof request?.errorText === "string" ? request.errorText.toLowerCase() : ""
  let reason = "unknown"
  if (/err_aborted|aborted/u.test(errorText)) reason = "aborted"
  else if (/err_blocked|blocked/u.test(errorText)) reason = "blocked"
  else if (/err_name_not_resolved|dns/u.test(errorText)) reason = "dns"
  else if (/err_timed_out|timeout/u.test(errorText)) reason = "timeout"
  else if (/err_cert|tls|ssl/u.test(errorText)) reason = "tls"
  else if (/err_connection|connection refused|connection reset/u.test(errorText)) {
    reason = "connection"
  } else if (errorText) reason = "other_network"
  return { method, origin, endpoint, reason }
}

export function summarizeAuthenticatedVisualDiagnostics({
  consoleMessages = [],
  requestFailures = [],
  httpFailures = [],
  expectedOrigin = new URL(ORIGIN).origin,
} = {}) {
  const consoleTypeCounts = createDiagnosticCounts(VISUAL_CONSOLE_TYPES)
  const consoleClassCounts = createDiagnosticCounts(VISUAL_CONSOLE_CLASSES)
  const requestMethodCounts = createDiagnosticCounts(VISUAL_REQUEST_METHODS)
  const requestOriginCounts = createDiagnosticCounts(VISUAL_REQUEST_ORIGINS)
  const requestEndpointCounts = createDiagnosticCounts(VISUAL_REQUEST_ENDPOINTS)
  const requestReasonCounts = createDiagnosticCounts(VISUAL_REQUEST_REASONS)
  const httpStatusClassCounts = { "4xx": 0, "5xx": 0, other: 0 }
  let capped =
    consoleMessages.length > DIAGNOSTIC_COUNT_LIMIT ||
    requestFailures.length > DIAGNOSTIC_COUNT_LIMIT ||
    httpFailures.length > DIAGNOSTIC_COUNT_LIMIT

  for (const message of consoleMessages) {
    const type = VISUAL_CONSOLE_TYPES.includes(message?.type) ? message.type : "other"
    capped = incrementDiagnosticCount(consoleTypeCounts, type) || capped
    const messageClass = classifyVisualConsoleMessage(message?.text)
    capped = incrementDiagnosticCount(consoleClassCounts, messageClass) || capped
  }
  for (const request of requestFailures) {
    const classified = classifyVisualRequestFailure(request, expectedOrigin)
    capped = incrementDiagnosticCount(requestMethodCounts, classified.method) || capped
    capped = incrementDiagnosticCount(requestOriginCounts, classified.origin) || capped
    capped = incrementDiagnosticCount(requestEndpointCounts, classified.endpoint) || capped
    capped = incrementDiagnosticCount(requestReasonCounts, classified.reason) || capped
  }
  for (const response of httpFailures) {
    const status = Number.isInteger(response?.status) ? response.status : 0
    const statusClass =
      status >= 500 && status <= 599 ? "5xx" : status >= 400 && status <= 499 ? "4xx" : "other"
    capped = incrementDiagnosticCount(httpStatusClassCounts, statusClass) || capped
  }

  return {
    schema: 1,
    capped,
    consoleTypeCounts,
    consoleClassCounts,
    requestFailureCount: Math.min(requestFailures.length, DIAGNOSTIC_COUNT_LIMIT),
    requestMethodCounts,
    requestOriginCounts,
    requestEndpointCounts,
    requestReasonCounts,
    httpFailureCount: Math.min(httpFailures.length, DIAGNOSTIC_COUNT_LIMIT),
    httpStatusClassCounts,
  }
}
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
  let dashboardCardsVisible = routePath === "/dashboard" ? false : null
  let dashboardReadinessError = null
  const newsReadinessRequired = Boolean(captureConfig && routePath === "/news")
  let newsReady = newsReadinessRequired ? false : null
  let newsArticleCount = newsReadinessRequired ? 0 : null
  let newsActiveFilterState = newsReadinessRequired ? "unavailable" : null
  let newsReadinessError = null
  let newsLayoutPaintReady = newsReadinessRequired ? false : null
  let newsArticlePaintReady = newsReadinessRequired ? false : null
  let newsPaintDiagnostics = newsReadinessRequired ? unavailableNewsPaintDiagnostics() : null
  const eventsReadinessRequired = Boolean(captureConfig && routePath === "/events")
  let eventsReady = eventsReadinessRequired ? false : null
  let eventsCardCount = eventsReadinessRequired ? 0 : null
  let eventsBusyCleared = eventsReadinessRequired ? false : null
  let eventsReadinessError = null
  const scheduleReadinessRequired = Boolean(captureConfig && routePath === "/schedule")
  let scheduleReady = scheduleReadinessRequired ? false : null
  let scheduleLoaded = scheduleReadinessRequired ? false : null
  let scheduleHeadingMatches = scheduleReadinessRequired ? false : null
  let scheduleViewMode = scheduleReadinessRequired ? "unavailable" : null
  let scheduleLessonCardCount = scheduleReadinessRequired ? 0 : null
  let scheduleSelectedDayPanelVisible = scheduleReadinessRequired ? false : null
  let scheduleSelectedDayWeekend = scheduleReadinessRequired ? false : null
  let scheduleErrorVisible = scheduleReadinessRequired ? true : null
  let scheduleReadinessError = null
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

    if (routePath === "/dashboard") {
      try {
        await page.waitForFunction(dashboardCardsAreVisible, undefined, { timeout: 30_000 })
        dashboardCardsVisible = true
      } catch {
        dashboardReadinessError = "dashboard_cards_not_visible_or_settled"
      }
    }

    if (newsReadinessRequired) {
      try {
        const readiness = await waitForAuthenticatedNewsReady(page, captureConfig.locale)
        newsReady = readiness.ready
        newsArticleCount = readiness.articleCount
        newsActiveFilterState = readiness.activeFilterState
        newsLayoutPaintReady = readiness.layoutPaintReady
        newsArticlePaintReady = readiness.articlePaintReady
        newsPaintDiagnostics = readiness.paintDiagnostics
        newsReadinessError = readiness.error
      } catch {
        newsReady = false
        newsLayoutPaintReady = false
        newsArticlePaintReady = false
        newsPaintDiagnostics = unavailableNewsPaintDiagnostics()
        newsReadinessError = "news_readiness_probe_failed"
      }
    }

    if (eventsReadinessRequired) {
      try {
        const readiness = await waitForAuthenticatedEventsReady(page, captureConfig.locale)
        eventsReady = readiness.ready
        eventsCardCount = readiness.cardCount
        eventsBusyCleared = readiness.busyCleared
        eventsReadinessError = readiness.error
      } catch {
        eventsReady = false
        eventsReadinessError = "events_readiness_probe_failed"
      }
    }

    if (scheduleReadinessRequired) {
      try {
        const readiness = await waitForAuthenticatedScheduleReady(page, captureConfig.locale)
        scheduleReady = readiness.ready
        scheduleLoaded = readiness.loaded
        scheduleHeadingMatches = readiness.headingMatches
        scheduleViewMode = readiness.viewMode
        scheduleLessonCardCount = readiness.lessonCardCount
        scheduleSelectedDayPanelVisible = readiness.selectedDayPanelVisible
        scheduleSelectedDayWeekend = readiness.selectedDayWeekend
        scheduleErrorVisible = readiness.errorVisible
        scheduleReadinessError = readiness.error
      } catch {
        scheduleReady = false
        scheduleReadinessError = "schedule_readiness_probe_failed"
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

  const visualDiagnostics = summarizeAuthenticatedVisualDiagnostics({
    consoleMessages,
    requestFailures: networkFailures,
    httpFailures: failedNetworkRequests,
  })

  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") || m.text.includes("Hydration") || m.text.includes("did not match")
  )
  const redirectedToLogin =
    finalUrl && (finalUrl.endsWith("/login") || finalUrl.includes("/login?"))

  if (
    canCaptureAuthenticatedScreenshot({
      captureConfig,
      visualConfigurationMatches,
      routePath,
      httpStatus,
      redirectedToLogin,
      finalUrl,
      dashboardCardsVisible,
      newsReadinessRequired,
      newsReady,
      eventsReadinessRequired,
      eventsReady,
      scheduleReadinessRequired,
      scheduleReady,
    })
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
        visualDiagnostics,
        consoleMessages: consoleMessages.map((message) => ({
          type: message.type,
          text: redactDiagnostic(message.text),
        })),
        networkRequestCount: networkRequests.length,
        networkRequests: networkRequests.slice(0, 50),
        networkFailures,
        failedNetworkRequests,
        axeError: redactDiagnostic(axeError),
        dashboardCardsVisible,
        dashboardReadinessError,
        newsReadinessRequired,
        newsReady,
        newsArticleCount,
        newsActiveFilterState,
        newsReadinessError,
        newsLayoutPaintReady,
        newsArticlePaintReady,
        newsPaintDiagnostics,
        eventsReadinessRequired,
        eventsReady,
        eventsCardCount,
        eventsBusyCleared,
        eventsReadinessError,
        scheduleReadinessRequired,
        scheduleReady,
        scheduleLoaded,
        scheduleHeadingMatches,
        scheduleViewMode,
        scheduleLessonCardCount,
        scheduleSelectedDayPanelVisible,
        scheduleSelectedDayWeekend,
        scheduleErrorVisible,
        scheduleReadinessError,
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
    dashboardCardsVisible,
    dashboardReadinessError,
    newsReadinessRequired,
    newsReady,
    newsArticleCount,
    newsActiveFilterState,
    newsReadinessError,
    newsLayoutPaintReady,
    newsArticlePaintReady,
    newsPaintDiagnostics,
    visualDiagnostics,
    eventsReadinessRequired,
    eventsReady,
    eventsCardCount,
    eventsBusyCleared,
    eventsReadinessError,
    scheduleReadinessRequired,
    scheduleReady,
    scheduleLoaded,
    scheduleHeadingMatches,
    scheduleViewMode,
    scheduleLessonCardCount,
    scheduleSelectedDayPanelVisible,
    scheduleSelectedDayWeekend,
    scheduleErrorVisible,
    scheduleReadinessError,
    viewportWidth: captureConfig?.width ?? null,
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

async function connectAuthenticatedRemoteChromium(connection) {
  try {
    return await chromium.connect(connection.endpoint, {
      timeout: 30_000,
      exposeNetwork: connection.exposeNetwork,
    })
  } catch {
    throw new Error("Remote Chromium connection failed")
  }
}

async function main() {
  const routes = parseAuthenticatedVisualRoutes(process.env)
  // Validate the complete optional matrix before creating output, making a
  // network request, or launching Chromium. The legacy run remains unchanged.
  const captureMatrix = parseAuthenticatedVisualCaptureMatrix()
  const remoteBrowserConnection = parseAuthenticatedRemoteBrowserConnection(process.env)
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
  const browser = remoteBrowserConnection
    ? await connectAuthenticatedRemoteChromium(remoteBrowserConnection)
    : await chromium.launch({ headless: true })

  await withOwnedSessionCleanup({
    browser,
    createContext: () =>
      browser.newContext({
        viewport: {
          width: captureMatrix?.widths[0] ?? 1280,
          height: captureMatrix?.height ?? 800,
        },
      }),
    origin: ORIGIN,
    onCleanupFailure: () => console.error("Owned session or browser cleanup failed."),
    run: async ({ context, ownSession }) => {
      const page = await context.newPage()
      page.setDefaultTimeout(30_000)
      page.setDefaultNavigationTimeout(30_000)

      let loginResult
      try {
        loginResult = await performLogin(context, ownSession)
        if (captureMatrix) await verifySyntheticStudent(context)
      } catch (err) {
        if (err instanceof RS256Error) throw setVisualExitCode(err, 3)
        throw setVisualExitCode(err, 1)
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
              browserTransport: remoteBrowserConnection
                ? "playwright-websocket"
                : "local-bundled-chromium",
              remoteBrowserRequired: process.env.VISUAL_REMOTE_CHROMIUM_REQUIRED === "1",
              sourceSha: captureMatrix.sourceSha,
              origin: captureMatrix.origin,
              routes,
              ...(captureMatrix.selectedRoute
                ? { selectedRoute: captureMatrix.selectedRoute }
                : {}),
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
            result.dashboardCardsVisible !== false &&
            (!result.newsReadinessRequired || result.newsReady === true) &&
            (!result.eventsReadinessRequired || result.eventsReady === true) &&
            (!result.scheduleReadinessRequired || result.scheduleReady === true) &&
            (!captureConfig || Boolean(result.screenshotPath))
              ? "✓"
              : "✗"
          console.log(
            `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} axe_viol=${result.axeViolationCount}${captureConfig ? ` config=${result.captureConfigMatches ? "verified" : "failed"} screenshot=${result.screenshotPath ? "yes" : "no"}` : ""}`
          )
        }
      }

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
        throw setVisualExitCode(
          new Error(
            `${failed.length}/${summaries.length} routes failed (non-200 OR redirected to /login)`
          ),
          1
        )
      }
      if (hydrationIssues.length > 0) {
        throw setVisualExitCode(
          new Error(`${hydrationIssues.length}/${summaries.length} routes had hydration errors`),
          2
        )
      }
      const newsReadinessIssues = findNewsReadinessIssues(summaries)
      if (newsReadinessIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            newsReadinessIssues.length +
              "/" +
              summaries.length +
              " News captures did not prove a stable non-empty list and default filter"
          ),
          9
        )
      }
      const eventsReadinessIssues = findEventsReadinessIssues(summaries)
      if (eventsReadinessIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            eventsReadinessIssues.length +
              "/" +
              summaries.length +
              " Events captures did not prove a stable loaded panel and visible seeded cards"
          ),
          10
        )
      }
      const scheduleReadinessIssues = findScheduleReadinessIssues(summaries)
      if (scheduleReadinessIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            scheduleReadinessIssues.length +
              "/" +
              summaries.length +
              " Schedule captures did not prove a loaded responsive view"
          ),
          11
        )
      }
      const dashboardReadinessIssues = findDashboardReadinessIssues(summaries)
      if (dashboardReadinessIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            dashboardReadinessIssues.length +
              "/" +
              summaries.length +
              " dashboard captures did not prove all loaded cards visible and settled"
          ),
          8
        )
      }
      if (axeErrors.length > 0) {
        throw setVisualExitCode(
          new Error(
            `${axeErrors.length}/${summaries.length} routes did not complete axe analysis; inspect private sidecars`
          ),
          5
        )
      }
      if (axeIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            `${axeIssues.length}/${summaries.length} routes had critical/serious axe violations; inspect private sidecars`
          ),
          5
        )
      }
      if (runtimeIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            `${runtimeIssues.length}/${summaries.length} routes had console/page errors or failed network requests; inspect private sidecars`
          ),
          6
        )
      }
      if (visualConfigurationIssues.length > 0) {
        throw setVisualExitCode(
          new Error(
            `${visualConfigurationIssues.length}/${summaries.length} captures failed requested locale/theme/viewport verification or screenshot capture; inspect private sidecars`
          ),
          7
        )
      }
      console.log(
        captureMatrix
          ? `\n✓ All ${summaries.length} authenticated matrix captures passed on source ${captureMatrix.sourceSha}`
          : `\n✓ All ${summaries.length} routes passed: HTTP 200 + 0 hydration errors + 0 axe critical/serious violations`
      )
    },
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error("Fatal error:", redactDiagnostic(err.message))
    process.exitCode = Number.isInteger(err?.visualExitCode) ? err.visualExitCode : 1
  })
}
