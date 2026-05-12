/**
 * wave138-visual-audit.mjs — first per-page visual audit feasible since
 * the SSR migration arc started in W125.
 *
 * Built on the foundation of W137 SW4 wave137-authed-smoke.mjs (which
 * proved 8 SSR routes 200 + AUTHED + 0 hydration errors through real
 * Caddy → Node SSR → gateway → backend chain). This script extends that
 * authed smoke with axe-core a11y assertions per route. /dashboard is
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
 *   node ./scripts/wave138-visual-audit.mjs
 *
 *   # Subset of routes:
 *   ROUTES=/dashboard,/events node ./scripts/wave138-visual-audit.mjs
 *
 *   # Override origin / credentials:
 *   ORIGIN=http://localhost \
 *     TEST_EMAIL=test@university.dev \
 *     TEST_PASSWORD=TestPass@2024x \
 *     node ./scripts/wave138-visual-audit.mjs
 *
 * ## Exit codes
 *
 *   0: all routes scanned cleanly (HTTP 200, no critical/serious axe violations)
 *   1: JWKS pre-check failed OR login failed OR a route returned non-200
 *   2: hydration errors detected
 *   3: JWT alg !== "RS256" (W137 SW1 backend RS256 enablement broken)
 *   4: JWKS returned 0 keys (backend RSA key not loaded)
 *   5: critical or serious axe violations found
 */

import { Buffer } from "node:buffer"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

// W143 SW1 — Path A mini-axe injection via CDN script tag (W115 SW3 pattern).
// Replaces `@axe-core/playwright` AxeBuilder block to bypass dual-injection
// finishRun chunking. See `auditRoute` body for full rationale + composition
// with preserved W142 SW1 Path C + Path B scaffolding.
const AXE_CDN_URL = "https://cdn.jsdelivr.net/npm/axe-core@4.11.2/axe.min.js"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const TEST_EMAIL = process.env.TEST_EMAIL ?? "test@university.dev"
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? "TestPass@2024x"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/wave138-visual-audit"
)

const DEFAULT_ROUTES = [
  "/dashboard",
  "/events",
  "/news",
  "/schedule",
  "/profile",
  "/settings",
  "/map",
  "/activity",
]

// Normalize each route — accept both "/dashboard" and "dashboard" forms.
// MSYS path conversion on Windows Git Bash mangles leading-slash env values
// ("ROUTES=/dashboard" becomes "C:/Program Files/Git/dashboard"), so callers
// can pass without leading slash and we re-add it here. (Same workaround as
// lhci-windows-fallback.mjs `normalizePath` from W120 SW1.)
function normalizeRoute(p) {
  const trimmed = p.trim()
  if (!trimmed) return null
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`
}
// W140 SW4 iter7 fix: env ROUTES="" (workflow_dispatch with empty input)
// must fall through to DEFAULT_ROUTES. `??` treats "" as a real value
// (not nullish), so we explicitly check for trimmed-empty too. Same
// concern as W120 SW5 MSYS empty-string handling in run-lhci.mjs.
const routesEnv = process.env.ROUTES?.trim()
const ROUTES = (routesEnv ? routesEnv : DEFAULT_ROUTES.join(","))
  .split(",")
  .map(normalizeRoute)
  .filter(Boolean)

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
  const jwksUrl = `${ORIGIN}/api/v1/.well-known/jwks.json`
  console.log(`→ JWKS pre-check: GET ${jwksUrl}`)
  let resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    const altUrl = `${ORIGIN}/.well-known/jwks.json`
    console.log(`  fallback: GET ${altUrl}`)
    resp = await fetch(altUrl)
  }
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
  console.log(`✓ JWKS healthy: ${rs256Keys.length} RS256 key(s)`)
  return jwks
}

async function performLogin(context) {
  console.log(`→ API login: POST ${ORIGIN}/api/v1/auth/login/json as ${TEST_EMAIL}`)
  const origin = new URL(ORIGIN)
  const isHttps = origin.protocol === "https:"
  const cookieDomain = origin.hostname

  const csrfResp = await fetch(`${ORIGIN}/api/v1/auth/csrf`)
  const csrfCookieHeader =
    csrfResp.headers.getSetCookie?.() ?? csrfResp.headers.raw?.()?.["set-cookie"] ?? []
  let csrfToken
  for (const setCookie of csrfCookieHeader) {
    const match = setCookie.match(/csrf_token=([^;]+)/)
    if (match) {
      csrfToken = match[1]
      break
    }
  }
  if (!csrfToken) {
    throw new Error(`CSRF token cookie not received`)
  }

  const loginResp = await fetch(`${ORIGIN}/api/v1/auth/login/json`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      Cookie: `csrf_token=${csrfToken}`,
    },
    body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
  })
  if (loginResp.status !== 200) {
    const body = await loginResp.text()
    throw new Error(`Login failed: HTTP ${loginResp.status} — ${body.slice(0, 200)}`)
  }

  const loginCookieHeader =
    loginResp.headers.getSetCookie?.() ?? loginResp.headers.raw?.()?.["set-cookie"] ?? []
  const cookies = []
  let accessTokenValue = null
  for (const setCookie of loginCookieHeader) {
    for (const name of ["access_token_v2", "csrf_token"]) {
      const re = new RegExp(`${name}=([^;]+)`)
      const match = setCookie.match(re)
      if (match) {
        cookies.push({
          name,
          value: match[1],
          domain: cookieDomain,
          path: "/",
          httpOnly: name === "access_token_v2",
          secure: isHttps,
          sameSite: "Lax",
        })
        if (name === "access_token_v2") {
          accessTokenValue = match[1]
        }
      }
    }
  }
  if (!accessTokenValue) {
    throw new Error("access_token_v2 cookie not in login response")
  }

  const { header, payload } = decodeJwtUnverified(accessTokenValue)
  if (header.alg !== "RS256") {
    throw new RS256Error(`JWT alg=${header.alg}, expected "RS256".`)
  }
  if (payload.aud !== "university-ecosystem-api") {
    throw new Error(`JWT aud=${payload.aud}, expected "university-ecosystem-api".`)
  }

  await context.addCookies(cookies)
  console.log(`✓ Login OK; injected ${cookies.length} cookies`)
  return { cookies, jwtHeader: header, jwtPayload: payload }
}

/**
 * Per-route audit: navigate + console capture + axe-core scan.
 *
 * Mirrors wave137-authed-smoke.mjs `smokeRoute()` shape, then layers
 * axe-core on top after settle. Returns enhanced result that includes
 * `axeViolations` + `axeViolationCount`.
 */
async function auditRoute(page, routePath, outDir) {
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

  const targetUrl = `${ORIGIN}${routePath}`
  let httpStatus = null
  let finalUrl = null
  let navError = null
  let axeViolations = []
  let axeError = null

  // emulateMedia + reducedMotion settles Framer Motion at end-state for
  // axe-core sampling (W113 SW1 + W114 SW2b + W115 SW1 pattern).
  await page.emulateMedia({ reducedMotion: "reduce" })

  try {
    const resp = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()

    // 1500ms hydration + Framer Motion + React Query observers settle.
    // Same buffer wave137 uses; axe-core needs final-state DOM.
    await page.waitForTimeout(1500)

    // W143 SW1 — Path A mini-axe injection via CDN script tag.
    //
    // W142 SW1 iter 1 (Path C: Dashboard.tsx VITE_E2E_MODE content
    // reduction) + iter 2 (Path B: AxeBuilder.include("main") +
    // .disableRules × 12) BOTH disproved at CI level via runs 25701743572
    // + 25702079799 — /dashboard still axeError "axe-analyze-timeout-60s".
    // Root cause per Agent 1 Phase 1 finding: @axe-core/playwright's
    // AxeBuilder.analyze() does dual page injection + finishRun result
    // chunking (heavy serialization across browser↔Node boundary) which
    // pushes heavy-DOM authed routes past the 60s timeout even with
    // engine optimization + content reduction.
    //
    // Path A bypasses the chunking layer entirely via the proven W115 SW3
    // `a11y-cdn-axe.spec.ts` pattern: load axe.min.js@4.11.2 from CDN once
    // per page via `addScriptTag`, then invoke `axe.run()` directly inside
    // `page.evaluate()`. Single injection, no chunking, no Playwright
    // serialization. Composes ON TOP of W142 SW1 Path C content gates
    // (Dashboard.tsx VITE_E2E_MODE) + Path B-equivalent rule disabling
    // (translated to axe.run() options.rules shape) + scope narrowing
    // (translated from AxeBuilder .include() to context arg).
    //
    // Scope arg: axe.run() takes context as the 1st positional argument.
    // We pass `document.querySelector("#main-content")` to scope the DOM
    // walk to MainLayout's <main id="main-content"> element (line 57-58
    // of MainLayout.tsx). The id is stable across both prod AND E2E_MODE
    // builds — VITE_E2E_MODE only swaps Navbar/Footer/etc to landmark
    // stubs, NOT the main element. Defensive fallback to `document` if
    // the element is missing (unexpected; would indicate routing or layout
    // bug, surfaced via violations rather than crash).
    //
    // Rule disabling: AxeBuilder `.disableRules([])` translates to
    // `axe.run()` options.rules: { ruleId: { enabled: false } } map.
    // Identical rule list as W142 SW1 iter 2 Path B (same rationale per
    // rule — see W142 SW1 commit 48d13a061 for details).
    //
    // Promise.race 60s timeout preserved as defense-in-depth. Path A's
    // lighter memory profile should bring authed-route analyze() under
    // 60s, but the timeout protects against runaway in case any (z)
    // discovery surfaces during CI verification (e.g., heavy /map maplibre
    // canvas + WeatherParticles + 4 orbs may still exceed 60s).
    try {
      await page.addScriptTag({ url: AXE_CDN_URL })

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

      const results = await Promise.race([
        page.evaluate(async (options) => {
          // `window.axe` is the CDN-injected global from addScriptTag.
          // Evaluated inside browser context; ESLint Node-side `no-undef`
          // doesn't apply because Playwright stringifies + ships this fn.
          // eslint-disable-next-line no-undef
          const mainEl = document.querySelector("#main-content")
          // eslint-disable-next-line no-undef
          const scopeContext = mainEl ?? document
          // eslint-disable-next-line no-undef
          return await window.axe.run(scopeContext, options)
        }, axeRunOptions),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("axe-analyze-timeout-60s")), 60_000)
        ),
      ])
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

  // Sidecar JSON
  const sidecarPath = path.join(outDir, `${safeFilename(routePath)}.json`)
  await writeFile(
    sidecarPath,
    JSON.stringify(
      {
        path: routePath,
        targetUrl,
        finalUrl,
        httpStatus,
        navigationError: navError?.message ?? null,
        consoleMessages,
        networkRequestCount: networkRequests.length,
        networkRequests: networkRequests.slice(0, 50),
        axeError,
        axeViolationCount: axeViolations.length,
        axeViolations: axeViolations.map((v) => ({
          id: v.id,
          impact: v.impact,
          description: v.description,
          help: v.help,
          helpUrl: v.helpUrl,
          tags: v.tags,
          nodeCount: v.nodes.length,
          nodes: v.nodes.slice(0, 5).map((n) => ({
            html: n.html.slice(0, 300),
            target: n.target,
            failureSummary: n.failureSummary?.slice(0, 500),
          })),
        })),
      },
      null,
      2
    )
  )

  const errors = consoleMessages.filter((m) => m.type === "error" || m.type === "pageerror")
  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") || m.text.includes("Hydration") || m.text.includes("did not match")
  )
  const redirectedToLogin =
    finalUrl && (finalUrl.endsWith("/login") || finalUrl.includes("/login?"))

  return {
    path: routePath,
    httpStatus,
    finalUrl,
    redirectedToLogin,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    axeError,
    axeViolationCount: axeViolations.length,
    sampleErrors: errors.slice(0, 3).map((e) => e.text),
    navError: navError?.message ?? null,
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
  console.log(`Wave 138 SW3 — visual audit (authed Docker chain + axe-core)`)
  console.log(`  Origin: ${ORIGIN}`)
  console.log(`  Routes: ${ROUTES.length} (${ROUTES.join(", ")})`)
  console.log(`  Output: ${OUT_DIR}`)
  console.log("")

  await mkdir(OUT_DIR, { recursive: true })

  let jwks
  try {
    jwks = await checkJwksEndpoint()
    await writeFile(
      path.join(OUT_DIR, "jwks.json"),
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
    viewport: { width: 1280, height: 800 },
  })
  const page = await context.newPage()
  page.setDefaultTimeout(30_000)
  page.setDefaultNavigationTimeout(30_000)

  let loginResult
  try {
    loginResult = await performLogin(context)
  } catch (err) {
    if (err instanceof RS256Error) {
      console.error(`✗ RS256 ASSERTION FAILED: ${err.message}`)
      await context.close()
      await browser.close()
      process.exit(3)
    }
    console.error(`✗ LOGIN FAILED: ${err.message}`)
    await context.close()
    await browser.close()
    process.exit(1)
  }

  await writeFile(
    path.join(OUT_DIR, "login.json"),
    JSON.stringify(
      {
        injectedCookieCount: loginResult.cookies.length,
        cookieNames: loginResult.cookies.map((c) => c.name),
        jwtHeader: loginResult.jwtHeader,
        jwtPayloadSummary: {
          sub: loginResult.jwtPayload.sub,
          aud: loginResult.jwtPayload.aud,
          is_active: loginResult.jwtPayload.is_active,
          exp: loginResult.jwtPayload.exp,
          jti: loginResult.jwtPayload.jti,
        },
      },
      null,
      2
    )
  )

  await page.close()

  const summaries = []
  for (const route of ROUTES) {
    console.log(`→ ${route}`)
    const routePage = await context.newPage()
    routePage.setDefaultTimeout(45_000)
    routePage.setDefaultNavigationTimeout(45_000)
    const result = await auditRoute(routePage, route, OUT_DIR)
    await routePage.close()
    summaries.push(result)
    const glyph =
      result.httpStatus === 200 && !result.redirectedToLogin && result.axeViolationCount === 0
        ? "✓"
        : "✗"
    console.log(
      `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} axe_viol=${result.axeViolationCount}`
    )
  }

  await context.close()
  await browser.close()

  printSummary(summaries)

  const failed = summaries.filter((s) => s.httpStatus !== 200 || s.redirectedToLogin)
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)
  const axeIssues = summaries.filter((s) => s.axeViolationCount > 0)

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
  if (axeIssues.length > 0) {
    console.error(
      `\n✗ ${axeIssues.length}/${summaries.length} routes had critical/serious axe violations`
    )
    console.error(`  See sidecar JSON in ${OUT_DIR} for full details.`)
    process.exit(5)
  }
  console.log(
    `\n✓ All ${summaries.length} routes passed: HTTP 200 + 0 hydration errors + 0 axe critical/serious violations`
  )
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
