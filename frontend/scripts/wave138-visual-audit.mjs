/**
 * wave138-visual-audit.mjs — first per-page visual audit feasible since
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
import { mkdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

// W144 SW1 iter 2 — Path A2 npm-bundled axe-core + page.evaluate(eval(source)).
//
// Replaces the W143 SW1 / W142 SW1 Path A CDN script tag (`page.addScriptTag`
// + `https://cdn.jsdelivr.net/npm/axe-core@4.11.2/axe.min.js`) which hung
// structurally in CI under production CSP `script-src 'self' 'strict-dynamic'`.
//
// Source verification (W141 anti-pattern #3 — verified refs > hypothesis):
//   - app/core/policies/csp.py:39 — prod CSP includes 'strict-dynamic'
//   - app/core/security_headers.py:76 — per-request nonce gen
//   - frontend/scripts/post-build-shell.mjs:67-79 — nonce placeholder injection
//   - Playwright's `addScriptTag` cannot pass a CSP nonce → CDN script silently
//     blocked → no load/error event → indefinite wait
//
// W144 SW1 iter 1 (commit b2c3036a5) added a `page.on("requestfailed")`
// diagnostic listener to confirm the CSP-block hypothesis empirically. The
// iter 1 CI run was invalidated by a Windows-side MSYS path-mangle of the
// `gh -f routes=/login` input (W120 SW1 known issue resurfaced; the
// `gh` CLI arg is mangled BEFORE submission, distinct from the ROUTES
// env-var path which `normalizeRoute()` already workarounds). The hang
// pattern reproduced regardless (9.5 min on a mangled route URL), but
// REQUEST-BLOCKED never logged — suggesting CSP violations may not propagate
// to Playwright's `requestfailed` event at all (browser drops the script at
// HTML-parser level silently, no network-layer signal).
//
// Either way A2 is structurally CSP-agnostic — no <script> tag is created.
// `page.evaluate(eval(source))` executes axe-core directly inside the page's
// trusted JS context, bypassing all script-src restrictions. Source is read
// once at module load (axe.min.js is ~550 KB at version 4.11.2) and reused
// across all routes.
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../node_modules/axe-core/axe.min.js"
)
const AXE_SOURCE = await readFile(AXE_SOURCE_PATH, "utf-8")

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

// W145 SW3 — added /messenger + /messenger/placeholder-chat-id for messenger
// × 2 polish arc baseline coverage. Both routes are `ssr: false` (W128 SW2
// opt-down — chat is WebSocket-driven; SSR brings no LCP benefit). Empty-state
// DOM (no real chat data without ws-hub) is still good a11y scope target.
//
// Per SW1 Outcome A (CI run 25747112501 axeError=axe-inject-timeout-30s),
// these routes will deterministically hit the same fast-fail at 30s.
// Sidecar JSON captures HTTP 200 + AUTHED + 0 hydration errors as structural
// verification baseline. Full axe coverage pending W146+ injection strategy
// pivot (page.addInitScript() / chunked / different bundle).
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
  "/messenger/placeholder-chat-id",
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
  // W143 SW1 follow-up — CI sidecar (run 25732174008) revealed the script was
  // preferring the WRONG endpoint. Two JWKS endpoints exist in the backend:
  //   - GET /.well-known/jwks.json — app/api/well_known.py (proper RSA JWKS
  //     with kty=RSA + n + e fields per RFC 7517 / 7518; this is what Temporal
  //     Server fetches via TEMPORAL_JWT_KEY_SOURCE1 per W142 SW3 v2)
  //   - GET /api/v1/.well-known/jwks.json — app/api/internal/jwks.py (HMAC
  //     metadata stub with kty=oct, NO key material; for ws-hub legacy rotation
  //     polling per its own docstring)
  //
  // Pre-W143 the script preferred /api/v1/ first, which in CI returned the
  // stub (kty=oct, no n+e) and passed the alg-only RS256 filter at line 151
  // (the stub still has alg=RS256). This gave misleading "JWKS healthy"
  // confirmation while masking the structural endpoint shape mismatch.
  // W143 SW1 follow-up: prefer the ROOT URL first (Temporal's actual fetch
  // target per docker-compose TEMPORAL_JWT_KEY_SOURCE1), keep /api/v1/ as
  // fallback for ws-hub-routed deployments. Also tightens the validation
  // to require key material (n + e for RSA keys) so a stub-shape response
  // can no longer false-pass.
  const jwksUrl = `${ORIGIN}/.well-known/jwks.json`
  console.log(`→ JWKS pre-check: GET ${jwksUrl}`)
  let resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    const altUrl = `${ORIGIN}/api/v1/.well-known/jwks.json`
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
  // W143 SW1 follow-up: require RSA key material (kty + n + e) so the
  // internal stub endpoint (kty=oct, no n+e) can't false-pass this check.
  const rsaWithMaterial = rs256Keys.filter(
    (k) => k.kty === "RSA" && typeof k.n === "string" && typeof k.e === "string"
  )
  if (rsaWithMaterial.length === 0) {
    throw new Error(
      `JWKS has ${rs256Keys.length} RS256 key(s) but NONE include n+e material ` +
        `(likely hitting the internal stub at /api/v1/.well-known/jwks.json instead ` +
        `of the proper /. .well-known/jwks.json endpoint).`
    )
  }
  console.log(`✓ JWKS healthy: ${rsaWithMaterial.length} RS256 key(s) with n+e material`)
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
 * Runs the authenticated smoke shape, then layers axe-core on top after
 * settle. Returns an enhanced result that includes
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
    // W145 SW1 — per-step console.log markers (with route prefix) around
    // each blocking step. Captured in workflow stdout via Playwright's
    // process stdout. Diagnostic for (z) #21 — the 24-min CI hang in W144
    // SW1 iter 2 CI run 25739831369 on /login. The marker that DOESN'T
    // log identifies the exact unbounded-wait step.
    console.log(`[${routePath}] before-goto`)
    const resp = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()
    console.log(`[${routePath}] after-goto status=${httpStatus} url=${finalUrl}`)

    // 1500ms hydration + Framer Motion + React Query observers settle.
    // Same buffer wave137 uses; axe-core needs final-state DOM.
    console.log(`[${routePath}] before-waitTimeout`)
    await page.waitForTimeout(1500)
    console.log(`[${routePath}] after-waitTimeout`)

    // W144 SW1 iter 2 — Path A2 npm-bundled axe-core + page.evaluate(eval(src)).
    //
    // Composes ON TOP of W142 SW1 Path C content gates (Dashboard.tsx
    // VITE_E2E_MODE — preserved) + Path B-equivalent rule disabling
    // (axe.run() options.rules shape, same list as W142 SW1 iter 2) + scope
    // narrowing via context arg (`document.querySelector("#main-content")`).
    //
    // Pattern:
    //   1. `page.evaluate((src) => { eval(src) }, AXE_SOURCE)` injects
    //      window.axe global into the page's JS sandbox via eval. No <script>
    //      tag is created → CSP `script-src 'self' 'strict-dynamic'` is not
    //      evaluated against this code path → no silent block possible.
    //   2. `page.evaluate(async (options) => window.axe.run(...))` invokes
    //      the in-page axe global. Single Playwright↔browser round-trip
    //      (the axe.run promise is awaited in-page, only the final result
    //      structure crosses the boundary).
    //
    // Scope arg: scope to MainLayout's <main id="main-content"> element
    // (MainLayout.tsx line 57-58). The id is stable across both prod AND
    // VITE_E2E_MODE builds — E2E mode only swaps Navbar/Footer/BackToTop/
    // MobileBottomNav to landmark stubs, NOT the main element. Defensive
    // fallback to `document` if missing (would indicate a routing or
    // layout bug, surfaced via violations rather than crash).
    //
    // Timeout: 60s for compact routes (/login, /404, /events, /news,
    // /schedule, /profile, /settings), 90s for heavy routes (/dashboard,
    // /map, /activity) which carry larger SSR-rendered DOM + canvas
    // backdrops. Per W144 Phase 1 Agent 1 risk #5: even with E2E-reduced
    // chrome + scope narrowing, heavy routes may need extra budget.
    const HEAVY_ROUTES = new Set(["/dashboard", "/map", "/activity"])
    const axeTimeoutMs = HEAVY_ROUTES.has(routePath) ? 90_000 : 60_000

    try {
      // Inject window.axe via eval — no <script> tag, no CSP path.
      // Source is the bundled axe-core@4.11.2 minified (~270 KB), audited
      // npm dep at frontend/node_modules/axe-core/axe.min.js, read once at
      // module load.
      //
      // W145 SW1 — Promise.race wrapper added to bound this injection step.
      // W144 SW1 iter 2 CI run 25739831369 HUNG 24 min on /login at this
      // step (no timeout was wrapping page.evaluate). Most plausible root
      // cause per source analysis: 550 KB AXE_SOURCE Playwright IPC
      // serialization cost OR eval() under headless Chromium memory
      // pressure. Either way, 30s ceiling closes the unbounded-wait
      // failure mode structurally — mirrors axe.run() Promise.race
      // pattern at lines ~440-460 below.
      const INJECT_TIMEOUT_MS = 30_000
      console.log(
        `[${routePath}] before-evalInject src-bytes=${AXE_SOURCE.length} timeout-ms=${INJECT_TIMEOUT_MS}`
      )
      await Promise.race([
        page.evaluate((src) => {
          // Inject window.axe global via eval — no <script> tag → CSP-agnostic.
          // The eslint no-eval rule is not enabled for this script's lint scope
          // (eval inside browser-context page.evaluate is intentional + audited
          // — source is npm-pinned axe-core@4.11.2 .min.js, not user input).
          eval(src)
        }, AXE_SOURCE),
        new Promise((_, reject) =>
          setTimeout(
            () => reject(new Error(`axe-inject-timeout-${INJECT_TIMEOUT_MS / 1000}s`)),
            INJECT_TIMEOUT_MS
          )
        ),
      ])
      console.log(`[${routePath}] after-evalInject`)

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
      const results = await Promise.race([
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
        new Promise((_, reject) =>
          setTimeout(
            () => reject(new Error(`axe-analyze-timeout-${axeTimeoutMs / 1000}s`)),
            axeTimeoutMs
          )
        ),
      ])
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
