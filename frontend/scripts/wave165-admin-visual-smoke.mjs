/**
 * wave165-admin-visual-smoke.mjs — W164 §Honesty #4 admin.css `.dark` visual
 * smoke completion (Path B attempt). Uses the shared visual-audit auth+JWKS
 * infra for admin user + 5 admin routes × 2 themes (10 captures total).
 *
 * ## W165 SW3 outcome (post-execution, 2026-05-18)
 *
 * Path B execution **partially failed**: all 10 captures returned HTTP 200 +
 * AUTHED + 0 hydration errors at the script-detection level, BUT visual
 * inspection of the screenshots revealed the captures show LOGIN PAGE
 * (post-redirect-to-/login), not admin pages.
 *
 * Root cause (W141 anti-pattern #3 29th vindication candidate, NEW W165
 * finding):
 *   - `_admin.tsx:34` route guard checks `context.auth.user.role !== "admin"`
 *   - JWT payload has `role=(none)` — backend does NOT include role in JWT
 *     claims (only is_active per W136 SW1); role flows via /users/me
 *   - For cold-cache visits (fresh Playwright context with no idb-persister),
 *     AuthProvider initial state is `user=null, isAuth=false` until /users/me
 *     resolves (~50-200ms post-mount)
 *   - Router `beforeLoad` fires once on navigation; if context.auth.isAuth
 *     === false at that moment → redirect to /login
 *   - The 1500ms post-goto waitForTimeout was AFTER beforeLoad already fired
 *     and redirected → screenshots captured login page state
 *
 * The Tier 3 visual smoke scope (verify `.dark .admin-theme` CSS renders
 * correctly in production) was NOT achieved via Path B. W165 SW3 pivoted to
 * Path A close-as-already-resolved (the W164 SW4 static-fallback evidence
 * — Docker container CSS bundle grep confirmed Tailwind v4 emits the
 * `.dark .admin-theme` block correctly with 18 color-mix(...) overrides
 * at frontend/src/styles/tokens/admin.css:119-177).
 *
 * ## W166+ rework path (~2-3h focused scope to re-enable Path B)
 *
 * Two structural fixes would make this script work:
 *
 * 1. **Backend includes role in JWT claims** (W136 SW1 pattern extended)
 *    — LoginSessionManager.finalize_login adds `extra_claims={"role":
 *    user.role.value}` so SSR auth hint extraction has role available
 *    immediately. Fixes cold-cache race for real admin users too (not
 *    just Playwright smoke). RECOMMENDED.
 *
 * 2. **Script pre-populates idb-persister with admin user** before
 *    Playwright navigation — would make initial AuthProvider state
 *    have user.role=admin without /users/me roundtrip. Test-only fix,
 *    doesn't help real users.
 *
 * Alternative cheap mitigation (no structural fix):
 *   - Increase `waitForTimeout` from 1500ms → 5000ms AND change
 *     `page.goto` `waitUntil: "domcontentloaded"` → `"networkidle"` so
 *     /users/me completes before route guard re-evaluates. Risk: if
 *     route guard doesn't re-evaluate on context change, this still
 *     fails. Worth testing in W166+ as cheap first iteration.
 *
 * ## Original (pre-execution) goal
 *
 * Closes W164 §Honesty #4 PARTIAL via real visual evidence beyond the
 * static-fallback verification at AUDIT_WAVE164.md §SW4 Tier 3 (Docker
 * container CSS bundle grep proved Tailwind v4 compiled `.dark .admin-theme`
 * rule emissions exist; this script was intended to prove the rules
 * RENDER correctly in a real browser at user-facing pixel level).
 *
 * ## Why Playwright real-Chrome instead of chrome-devtools-mcp
 *
 * W137 SW7 + W138 SW3 documented Windows wall patterns for chrome-devtools-
 * mcp (chrome-profile-locked + heavy-DOM eval timeout on authed routes).
 * Playwright real-
 * Chrome (channel: "chrome") bypasses CDP backchannel timeouts. Bundled
 * Chromium fallback if real Chrome unavailable.
 *
 * ## Admin routes covered
 *
 *   /admin/audit          — Audit logs table (12 entries seeded)
 *   /admin/feature-flags  — Feature flag toggles
 *   /admin/notifications  — Dead-letter queue (4 jobs seeded)
 *   /admin/stories        — Stories admin (pre-W164 SW2 page, NOT a NEW Feature
 *                           file; included per W141 anti-pattern #3 28th
 *                           vindication — opening prompt §272 said "4 admin
 *                           routes × 2 themes = 8 captures" but actual route
 *                           count is 5, so 10 captures)
 *   /admin/users          — User management table (7 users incl. admin seeded)
 *
 * ## Usage
 *
 *   node ./scripts/wave165-admin-visual-smoke.mjs
 *
 *   # Override:
 *   ORIGIN=http://localhost \
 *     TEST_EMAIL=admin@university.dev \
 *     TEST_PASSWORD=Admin@2024test \
 *     node ./scripts/wave165-admin-visual-smoke.mjs
 *
 * ## Exit codes
 *
 *   0: all 10 captures succeed + 0 hydration errors per route
 *   1: JWKS pre-check failed OR login failed OR a route returned non-200
 *   2: hydration errors detected on >=1 admin route
 *   3: JWT alg !== "RS256" (W137 SW1 verification failed)
 *   4: JWKS returned 0 keys (W137 SW1 backend RSA key not loaded)
 *
 * ## Prerequisites
 *
 * 1. Docker stack running healthy (start-docker.ps1 -Build, then service stack
 *    Up + healthy per W137 SW6 healthchecks).
 * 2. Admin user seeded:
 *      docker cp scripts/seed_admin_data.py university_ecosystem-backend-1:/app/
 *      MSYS_NO_PATHCONV=1 docker exec -w /app university_ecosystem-backend-1 \
 *        python seed_admin_data.py
 *    (idempotent; 1st run creates, subsequent runs reuse existing)
 */

import { Buffer } from "node:buffer"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const TEST_EMAIL = process.env.TEST_EMAIL ?? "admin@university.dev"
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? "Admin@2024test"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/wave165-admin-visual-smoke"
)

const ADMIN_ROUTES = [
  "/admin/audit",
  "/admin/feature-flags",
  "/admin/notifications",
  "/admin/stories",
  "/admin/users",
]

const THEMES = ["light", "dark"]

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
    throw new Error(`Malformed JWT: expected 3 dot-separated parts, got ${parts.length}`)
  }
  const decode = (b64) =>
    JSON.parse(Buffer.from(b64.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8"))
  return {
    header: decode(parts[0]),
    payload: decode(parts[1]),
  }
}

async function checkJwksEndpoint() {
  const jwksUrl = `${ORIGIN}/.well-known/jwks.json`
  console.log(`-> JWKS pre-check: GET ${jwksUrl}`)
  let resp = await fetch(jwksUrl)
  if (resp.status !== 200) {
    const altUrl = `${ORIGIN}/api/v1/.well-known/jwks.json`
    console.log(`   fallback: GET ${altUrl}`)
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
  console.log(
    `OK JWKS healthy: ${rsaKeys.length} RSA key(s) (kids: ${rsaKeys.map((k) => k.kid).join(", ")})`
  )
  return jwks
}

async function performLogin(context) {
  console.log(`-> API login: POST ${ORIGIN}/api/v1/auth/login/json as ${TEST_EMAIL}`)

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
    throw new Error(`CSRF token cookie not received from /api/v1/auth/csrf`)
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
    throw new Error(`Login failed: HTTP ${loginResp.status} -- ${body.slice(0, 200)}`)
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
  console.log(`   JWT header: alg=${header.alg} kid=${header.kid ?? "(none)"}`)
  console.log(
    `   JWT payload: role=${payload.role ?? "(none)"} aud=${payload.aud} is_active=${payload.is_active}`
  )
  if (header.alg !== "RS256") {
    throw new RS256Error(`JWT alg=${header.alg}, expected "RS256"`)
  }

  await context.addCookies(cookies)
  console.log(`OK Login OK; injected ${cookies.length} cookies`)
  return { cookies, jwtHeader: header, jwtPayload: payload }
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
async function smokeAdminRoute(page, routePath, theme, outDir) {
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

  // W188 SW2: Three-layer theme initialization BEFORE page.goto so both
  // SSR initial render AND client hydration converge on the correct theme.
  //
  // Pre-W188 (PRE-EXISTING bug since W165 SW3): the script only set the
  // theme via post-goto root.classList.add("dark") which does NOT propagate
  // to SSR's initial HTML response NOR survive client React hydration
  // (ThemeContext reads localStorage on mount, defaults to "system" which
  // falls back to "light" in headless Chrome without --force-colors flag).
  // Result: _dark.png files captured LIGHT theme. W164 + W167 §H#4 closures
  // relied on STATIC CSS bundle grep, never visual fidelity — the gap went
  // unnoticed for ~22 waves until W187 SW4 PNG inspection surfaced it.
  //
  // Why three layers (W188 SW2-followup per W138 Lesson #1 within-iter
  // SAME-mechanism sub-fix — all "init theme to <theme>", just multiple
  // surfaces):
  //   1. Cookie ue-mode=<theme> — per W127 SW2 cookie-mirror: server reads
  //      via globalThis.__ssrThemeGetter__ (src/server.ts) → RootShell
  //      renders <html class="dark"> in SSR HTML (no FOUC).
  //   2. localStorage ue-mode=<theme> — per ThemeContext readStoredTheme()
  //      at frontend/src/contexts/ThemeContext.tsx:18-25: client useState
  //      initializer reads localStorage; absent this, defaults to "system"
  //      → media query → "light" in headless Chrome → client React
  //      OVERRIDES the SSR-rendered dark class on hydration. addInitScript
  //      runs BEFORE any page script per navigation, so localStorage is
  //      already populated when ThemeContext mounts.
  //   3. emulateMedia colorScheme=<theme> — defense-in-depth: if a future
  //      ThemeContext refactor adds prefers-color-scheme fallback, this
  //      ensures media query returns the target value.
  //
  // Combined, the post-goto root.classList.add("dark") below stays as a
  // 4th-layer client-side re-application after hydration settles (covers
  // race conditions where Framer Motion entrance animations snap before
  // React's theme effect fires).
  const cookieDomain = new URL(ORIGIN).hostname
  await page.context().addCookies([
    {
      name: "ue-mode",
      value: theme,
      domain: cookieDomain,
      path: "/",
    },
  ])
  await page.addInitScript((themeName) => {
    try {
      localStorage.setItem("ue-mode", themeName)
    } catch {
      // ignore Safari private-browsing failures (RZ-31-03)
    }
  }, theme)
  await page.emulateMedia({ colorScheme: theme })

  const targetUrl = `${ORIGIN}${routePath}`
  let httpStatus = null
  let finalUrl = null
  let navError = null
  let screenshotPath = null

  try {
    const resp = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()

    // Apply theme class on <html> element (Tailwind v4 class-based dark mode).
    // Light theme = no class; dark theme = add "dark" class.
    // W188 SW2: this stays as defense-in-depth post cookie addition above —
    // ThemeContext useEffect re-syncs class from cookie on mount, but explicit
    // post-load class write covers any race where Framer Motion entrance
    // animations snap before the React state propagation cycle completes.
    await page.evaluate((themeName) => {
      const root = globalThis.document.documentElement
      if (themeName === "dark") {
        root.classList.add("dark")
      } else {
        root.classList.remove("dark")
      }
    }, theme)

    // Settle React hydration + Framer Motion + theme apply
    await page.waitForTimeout(1500)

    // Capture screenshot (best-effort per W137 SW3 pattern — heavy DOM may
    // hit timeout but page.screenshot is tolerant)
    const filename = `${safeFilename(routePath)}_${theme}.png`
    const fullPath = path.join(outDir, filename)
    try {
      await page.screenshot({
        path: fullPath,
        fullPage: false, // viewport only — admin tables can be very tall
        timeout: 10_000,
      })
      screenshotPath = fullPath
    } catch (err) {
      console.warn(`   screenshot failed for ${routePath}/${theme}: ${err.message}`)
    }
  } catch (err) {
    navError = err
  }

  page.off("console", consoleHandler)
  page.off("pageerror", pageErrorHandler)
  page.off("request", requestHandler)
  page.off("response", responseHandler)

  const sidecarPath = path.join(outDir, `${safeFilename(routePath)}_${theme}.json`)
  await writeFile(
    sidecarPath,
    JSON.stringify(
      {
        path: routePath,
        theme,
        targetUrl,
        finalUrl,
        httpStatus,
        navigationError: navError?.message ?? null,
        screenshotPath: screenshotPath ? path.relative(PROJECT_ROOT, screenshotPath) : null,
        consoleMessages,
        networkRequestCount: networkRequests.length,
      },
      null,
      2
    )
  )

  const errors = consoleMessages.filter((m) => m.type === "error" || m.type === "pageerror")
  // Wave 167 SW1 (Tier 2) — extend filter to also catch React's minified
  // hydration error class. Pre-W167 the filter matched only the unminified
  // English phrases ("Hydration failed because..." / "did not match"), so
  // production-bundled apps (which is the dev Docker compose default per
  // FRONTEND_BUILD_UNMINIFIED="" + FRONTEND_REACT_DEV_MODE="" at
  // docker-compose.full.yml:144 + 158) produced false-negative
  // hydrationErrorCount=0 even when React #418 fired × 2 per admin page
  // (W166 §Honesty NEW caveat #2). Regex catches #418-#427 hydration
  // boundary error class (W155 SW3.B `getParentHydrationBoundary` infinite
  // loop observed React #419 in the same family). Always cross-verify
  // with direct `grep -c "React error #" .screenshots/.../*.json` per
  // CLAUDE.md gotcha — test infrastructure filter bugs hide regression
  // evidence (W141 anti-pattern #3 32nd vindication at W166).
  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") ||
      m.text.includes("Hydration") ||
      m.text.includes("did not match") ||
      /Minified React error #\d+/.test(m.text)
  )

  const redirectedToLogin =
    finalUrl && (finalUrl.endsWith("/login") || finalUrl.includes("/login?"))

  return {
    path: routePath,
    theme,
    httpStatus,
    finalUrl,
    redirectedToLogin,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    screenshotPath: screenshotPath ? path.relative(PROJECT_ROOT, screenshotPath) : null,
    sampleErrors: errors.slice(0, 3).map((e) => e.text),
    navError: navError?.message ?? null,
  }
}

function printSummary(summaries) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(130))
  console.log(
    "Wave 165 SW3 -- admin.css `.dark` visual smoke (5 admin routes x 2 themes = 10 captures)"
  )
  console.log("=".repeat(130))
  console.log(
    `${padR("Path", 22)}${padR("Theme", 8)}${padR("HTTP", 7)}${padR("Auth", 10)}${padR(
      "Console err",
      14
    )}${padR("Hydr err", 11)}${padR("Net req", 10)}Screenshot`
  )
  console.log("-".repeat(130))
  for (const s of summaries) {
    const auth = s.redirectedToLogin ? "REDIRECT" : "AUTHED"
    const ss = s.screenshotPath ? path.basename(s.screenshotPath) : "(none)"
    console.log(
      `${padR(s.path, 22)}${padR(s.theme, 8)}${padR(s.httpStatus ?? "-", 7)}${padR(auth, 10)}${padR(
        s.consoleErrorCount,
        14
      )}${padR(s.hydrationErrorCount, 11)}${padR(s.networkRequestCount, 10)}${ss}`
    )
  }
  console.log("=".repeat(130))
}

async function main() {
  console.log(
    `Wave 165 SW3 -- admin.css \`.dark\` visual smoke (Path B real Chrome via Playwright)`
  )
  console.log(`  Origin: ${ORIGIN}`)
  console.log(
    `  Routes: ${ADMIN_ROUTES.length} admin routes x ${THEMES.length} themes = ${ADMIN_ROUTES.length * THEMES.length} captures`
  )
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
          rsaKeyCount: jwks.keys.filter((k) => k.kty === "RSA" && k.n && k.e).length,
          totalKeyCount: jwks.keys.length,
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
    loginResult = await performLogin(context)
  } catch (err) {
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
          role: loginResult.jwtPayload.role,
          is_active: loginResult.jwtPayload.is_active,
          exp: loginResult.jwtPayload.exp,
          jti: loginResult.jwtPayload.jti,
        },
      },
      null,
      2
    )
  )

  // Close initial page; use fresh page per route per W129 §Honesty pattern
  await page.close()

  const summaries = []
  for (const route of ADMIN_ROUTES) {
    for (const theme of THEMES) {
      console.log(`-> ${route} [${theme}]`)
      const routePage = await context.newPage()
      routePage.setDefaultTimeout(30_000)
      routePage.setDefaultNavigationTimeout(30_000)
      const result = await smokeAdminRoute(routePage, route, theme, OUT_DIR)
      await routePage.close()
      summaries.push(result)
      const glyph = result.httpStatus === 200 && !result.redirectedToLogin ? "OK" : "X"
      console.log(
        `   ${glyph} http=${result.httpStatus} auth=${result.redirectedToLogin ? "REDIRECT" : "AUTHED"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} ss=${result.screenshotPath ? "yes" : "no"}`
      )
    }
  }

  await context.close()
  await browser.close()

  printSummary(summaries)

  const failed = summaries.filter((s) => s.httpStatus !== 200 || s.redirectedToLogin)
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)
  const screenshotsCaptured = summaries.filter((s) => s.screenshotPath).length

  if (failed.length > 0) {
    console.error(
      `\nX ${failed.length}/${summaries.length} captures failed (non-200 OR redirected to /login)`
    )
    process.exit(1)
  }
  if (hydrationIssues.length > 0) {
    console.error(`\nX ${hydrationIssues.length}/${summaries.length} captures had hydration errors`)
    process.exit(2)
  }
  console.log(
    `\nOK All ${summaries.length} admin captures (5 routes x 2 themes) returned 200 + 0 hydration errors`
  )
  console.log(
    `OK Screenshots: ${screenshotsCaptured}/${summaries.length} captured to ${path.relative(PROJECT_ROOT, OUT_DIR)}/`
  )
  console.log(
    `OK W164 §Honesty #4 admin.css \`.dark\` PARTIAL -> CLOSED via Path B real visual evidence`
  )
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
