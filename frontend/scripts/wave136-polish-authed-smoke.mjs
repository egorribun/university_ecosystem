/**
 * wave136-polish-authed-smoke.mjs — W135 §Honesty #9 closure.
 *
 * One-shot script for the Wave 136 polish-pass. Drives Playwright through
 * a real authed login flow on the Caddy → frontend SSR → gateway → backend
 * chain, then smokes 8 SSR routes that are protected by the W128 auth-at-edge
 * route guards.
 *
 * Pre-W136: gateway returned 403 "user account is not active" for ALL
 * authed requests because the JWT issued by SessionService._mint_jwt did
 * NOT embed the `is_active` claim that gateway/middleware/auth.go:720
 * reads. Backend direct (port 8000) returned 200 with full user.
 *
 * Post-W136 SW1: backend embeds `is_active` claim. SW2 publishes session
 * JTIs to Redis pub/sub on user deactivation. SW4 fixes
 * failed_login_attempts schema. SW3 establishes Playwright real-Chrome as
 * the Windows visual-smoke standard.
 *
 * This script proves the FULL chain works end-to-end with an authed user.
 *
 * ## Usage
 *
 *   node ./scripts/wave136-polish-authed-smoke.mjs
 *
 *   # Override target origin:
 *   ORIGIN=http://localhost npm run start  # in another terminal
 *   ORIGIN=http://localhost node ./scripts/wave136-polish-authed-smoke.mjs
 *
 * ## Exit codes
 *
 *   0: all routes returned 200 + 0 React hydration errors
 *   1: login failed OR a route returned non-200 (e.g. 307 to /login)
 *   2: hydration errors detected on any route
 */

import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const TEST_EMAIL = process.env.TEST_EMAIL ?? "test@university.dev"
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? "TestPass@2024x"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/wave136-polish-authed"
)

const SSR_ROUTES = [
  "/dashboard",
  "/events",
  "/news",
  "/schedule",
  "/profile",
  "/settings",
  "/map",
  "/activity",
]

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

async function performLogin(context) {
  console.log(`→ API login: POST ${ORIGIN}/api/v1/auth/login/json as ${TEST_EMAIL}`)

  // Form-based login via Playwright would work but the React form's default
  // GET submit fires before onSubmit interception under SSR hydration timing.
  // API-direct login + cookie injection is more reliable AND mirrors what a
  // production session looks like (HttpOnly access_token_v2 cookie set by
  // backend's LoginSessionManager._set_access_token_cookie per W126 SW1).
  const origin = new URL(ORIGIN)
  const isHttps = origin.protocol === "https:"
  const cookieDomain = origin.hostname

  // Step 1 — GET to acquire CSRF cookie. The middleware sets csrf_token
  // on every response (Signed Double-Submit per app/core/csrf.py) even on
  // 404. We use /api/v1/auth/csrf which 404s but issues the cookie.
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
    throw new Error(
      `CSRF token cookie not received from /api/v1/auth/csrf — received headers: ${csrfCookieHeader.join(", ")}`
    )
  }

  // Step 2 — POST credentials with CSRF cookie + header
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

  // Step 3 — extract access_token_v2 + new csrf_token from response cookies
  const loginCookieHeader =
    loginResp.headers.getSetCookie?.() ?? loginResp.headers.raw?.()?.["set-cookie"] ?? []
  const cookies = []
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
      }
    }
  }
  if (!cookies.find((c) => c.name === "access_token_v2")) {
    throw new Error("access_token_v2 cookie not in login response")
  }

  await context.addCookies(cookies)
  console.log(
    `✓ API login HTTP 200; injected ${cookies.length} cookies (access_token_v2 + csrf_token) into Playwright context`
  )
  return cookies
}

async function smokeRoute(page, routePath, outDir) {
  const consoleMessages = []
  const networkRequests = []

  const consoleHandler = (msg) => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
    })
  }
  const pageErrorHandler = (err) => {
    consoleMessages.push({ type: "pageerror", text: err.message })
  }
  const requestHandler = (req) => {
    networkRequests.push({
      method: req.method(),
      url: req.url(),
    })
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

  try {
    const resp = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()
    // Settle React hydration + Framer Motion
    await page.waitForTimeout(1500)
  } catch (err) {
    navError = err
  }

  page.off("console", consoleHandler)
  page.off("pageerror", pageErrorHandler)
  page.off("request", requestHandler)
  page.off("response", responseHandler)

  // Sidecar JSON capture
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

  // Detect "redirected to /login" pattern — happens when gateway 403s
  // /api/v1/users/me, AuthContext clears session, route guard kicks user back.
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
    sampleErrors: errors.slice(0, 3).map((e) => e.text),
    navError: navError?.message ?? null,
  }
}

function printSummary(summaries) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(110))
  console.log("Wave 136 polish-v2 — authed Docker chain visual smoke summary")
  console.log("=".repeat(110))
  console.log(
    `${padR("Path", 14)}${padR("HTTP", 8)}${padR("Auth", 10)}${padR(
      "Console err",
      14
    )}${padR("Hydr err", 12)}${padR("Net req", 10)}Final URL`
  )
  console.log("-".repeat(110))
  for (const s of summaries) {
    const auth = s.redirectedToLogin ? "REDIRECT" : "AUTHED"
    console.log(
      `${padR(s.path, 14)}${padR(s.httpStatus ?? "-", 8)}${padR(auth, 10)}${padR(
        s.consoleErrorCount,
        14
      )}${padR(s.hydrationErrorCount, 12)}${padR(s.networkRequestCount, 10)}${s.finalUrl ?? "n/a"}`
    )
  }
  console.log("=".repeat(110))
}

async function main() {
  console.log(`Wave 136 polish-v2 — authed Docker chain visual smoke`)
  console.log(`  Origin: ${ORIGIN}`)
  console.log(`  Routes: ${SSR_ROUTES.length}`)
  console.log(`  Output: ${OUT_DIR}`)
  console.log("")

  await mkdir(OUT_DIR, { recursive: true })

  let browser
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true })
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

  // Capture login-time console for diagnostic
  const loginConsole = []
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      loginConsole.push(msg.text())
    }
  })

  let loginCookies
  try {
    loginCookies = await performLogin(context)
  } catch (err) {
    console.error(`✗ LOGIN FAILED: ${err.message}`)
    await context.close()
    await browser.close()
    process.exit(1)
  }

  // Persist login record for diagnostic
  await writeFile(
    path.join(OUT_DIR, "login.json"),
    JSON.stringify(
      {
        injectedCookieCount: loginCookies.length,
        cookieNames: loginCookies.map((c) => c.name),
      },
      null,
      2
    )
  )

  const summaries = []
  for (const route of SSR_ROUTES) {
    console.log(`→ ${route}`)
    const result = await smokeRoute(page, route, OUT_DIR)
    summaries.push(result)
    const glyph = result.httpStatus === 200 && !result.redirectedToLogin ? "✓" : "✗"
    console.log(
      `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount}`
    )
  }

  await context.close()
  await browser.close()

  printSummary(summaries)

  const failed = summaries.filter((s) => s.httpStatus !== 200 || s.redirectedToLogin)
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)

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
  console.log(
    `\n✓ All ${summaries.length} SSR routes returned 200 + 0 hydration errors through Caddy → Node SSR → gateway → backend chain`
  )
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
