/**
 * wave189-unauthed-smoke.mjs — W187 §H NEW #2 closure
 *                              (carried through W188).
 *
 * Visual smoke for the 4 PUBLIC unauthenticated routes through real Caddy →
 * Node SSR → backend chain. Mirrors the authenticated visual-audit structure minus
 * the auth chokepoint (CSRF dance + login POST + JWKS pre-check + JWT
 * decode/validation) since unauthenticated visitors never traverse those
 * code paths.
 *
 * Routes covered (W189 SW2 scope):
 *   - /login              (login form)
 *   - /register           (registration form)
 *   - /forgot-password    (password-reset request form)
 *   - /reset-password     (no $token — shows "missing token" error UI OR
 *                          redirects to /forgot-password depending on route
 *                          guard; either is acceptable for SSR-shell smoke)
 *
 * 3-layer theme init pattern (W188 SW2 lesson applied here):
 * Apply Cookie + localStorage(via addInitScript) + emulateMedia BEFORE
 * page.goto so both SSR initial render AND client hydration converge on
 * the same theme. Default theme = "light" (unauth visitors typically don't
 * have a stored preference yet). Dark theme runs are gated by THEME env.
 *
 * ## Usage
 *
 *   node ./scripts/wave189-unauthed-smoke.mjs
 *
 *   # Override target origin / output dir / theme:
 *   ORIGIN=http://localhost \
 *     THEME=dark \
 *     OUT_DIR=.screenshots/wave189-unauthed-smoke-dark \
 *     node ./scripts/wave189-unauthed-smoke.mjs
 *
 * ## Exit codes
 *
 *   0: all 4 routes return HTTP 200 + 0 hydration errors
 *   1: 1+ routes returned non-200 status OR navigation error
 *   2: 1+ routes had hydration errors detected (React #418-#427 family OR
 *      "hydrat" / "Hydration" / "did not match" substring match)
 *
 * Implementation cost: ~ 30 min per Wave 189 plan.
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
const THEME = process.env.THEME ?? "light"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/wave189-unauthed-smoke"
)

const UNAUTHED_ROUTES = [
  "/login",
  "/register",
  "/forgot-password",
  // /reset-password without a $token suffix — TanStack Router renders the
  // _public/reset-password route (no $token capture). The route component
  // likely shows an "Invalid or missing reset link" state OR redirects to
  // /forgot-password depending on route guard. Either outcome is acceptable
  // for the SSR-shell smoke (HTTP 200 + no hydration error).
  "/reset-password",
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

async function smokeRouteUnauthed(page, routePath, theme, outDir) {
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

  // W188 SW2: Three-layer theme initialization BEFORE page.goto so both
  // SSR initial render AND client hydration converge on the correct theme.
  // See `frontend/scripts/wave165-admin-visual-smoke.mjs:289-362` for full
  // rationale (W188 SW2 explains why single-layer cookie or post-goto class
  // manipulation is INSUFFICIENT). The same 3-layer pattern is required here
  // for /login + /register + /forgot-password + /reset-password unauth smoke
  // to ensure consistent theme parity across SSR + client renders.
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

  try {
    const resp = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    httpStatus = resp?.status() ?? null
    finalUrl = page.url()
    // Settle React hydration + Framer Motion + LCP paint.
    // 1500ms matches wave137 settle window (proven sufficient for SSR routes).
    await page.waitForTimeout(1500)

    // Optional best-effort screenshot capture (W189 SW2 opt-in via env).
    // Failure is non-fatal — chrome-devtools Windows snapshot wall (W113 +
    // W138 + W140) family can still bite even on lighter unauth DOM.
    if (process.env.WAVE189_CAPTURE_SCREENSHOTS === "true") {
      try {
        const screenshotPath = path.join(outDir, `${safeFilename(routePath)}_${theme}.png`)
        await page.screenshot({ path: screenshotPath, fullPage: false, timeout: 15_000 })
      } catch (screenshotErr) {
        console.warn(`  screenshot capture failed: ${screenshotErr.message?.slice(0, 100)}`)
      }
    }
  } catch (err) {
    navError = err
  }

  page.off("console", consoleHandler)
  page.off("pageerror", pageErrorHandler)
  page.off("request", requestHandler)
  page.off("response", responseHandler)

  // Sidecar JSON capture (per-route). Format mirrors wave137 minus JWT fields.
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
        consoleMessages,
        networkRequestCount: networkRequests.length,
        networkRequests: networkRequests.slice(0, 50),
      },
      null,
      2
    )
  )

  const errors = consoleMessages.filter((m) => m.type === "error" || m.type === "pageerror")
  // Per W180 polish-v1 hydration filter — catches both legacy substring
  // variants AND minified React #418-#427 family (W166 (z) #2 class bug fix
  // from W167 SW1 applied here too).
  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") ||
      m.text.includes("Hydration") ||
      m.text.includes("did not match") ||
      /Minified React error #(418|419|420|421|422|423|424|425|426|427)/.test(m.text)
  )

  return {
    path: routePath,
    theme,
    httpStatus,
    finalUrl,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    sampleErrors: errors.slice(0, 3).map((e) => e.text),
    navError: navError?.message ?? null,
  }
}

function printSummary(summaries, theme) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(120))
  console.log(`Wave 189 SW2 — unauthed visual smoke (4 public routes, theme=${theme})`)
  console.log("=".repeat(120))
  console.log(
    `${padR("Path", 20)}${padR("HTTP", 8)}${padR("Console err", 14)}${padR(
      "Hydr err",
      12
    )}${padR("Net req", 10)}Final URL`
  )
  console.log("-".repeat(120))
  for (const s of summaries) {
    console.log(
      `${padR(s.path, 20)}${padR(s.httpStatus ?? "-", 8)}${padR(
        s.consoleErrorCount,
        14
      )}${padR(s.hydrationErrorCount, 12)}${padR(s.networkRequestCount, 10)}${s.finalUrl ?? "n/a"}`
    )
  }
  console.log("=".repeat(120))
}

async function main() {
  console.log(`Wave 189 SW2 — unauthed visual smoke through real Caddy chain`)
  console.log(`  Origin: ${ORIGIN}`)
  console.log(`  Theme: ${THEME}`)
  console.log(`  Routes: ${UNAUTHED_ROUTES.length}`)
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

  // Per-route fresh page (W129 §Honesty pattern preserved from wave137).
  // Existing-page navigation has been observed to time out at 30s on
  // subsequent routes under chrome-devtools Windows wall family. Cost:
  // ~500ms slower per route from setup, but every route smokes successfully.
  const summaries = []
  for (const route of UNAUTHED_ROUTES) {
    console.log(`→ ${route}`)
    const routePage = await context.newPage()
    routePage.setDefaultTimeout(30_000)
    routePage.setDefaultNavigationTimeout(30_000)
    const result = await smokeRouteUnauthed(routePage, route, THEME, OUT_DIR)
    await routePage.close()
    summaries.push(result)
    const glyph = result.httpStatus === 200 ? "✓" : "✗"
    console.log(
      `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} net_req=${result.networkRequestCount}`
    )
  }

  await context.close()
  await browser.close()

  printSummary(summaries, THEME)

  const failed = summaries.filter((s) => s.httpStatus !== 200)
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)

  if (failed.length > 0) {
    console.error(
      `\n✗ ${failed.length}/${summaries.length} routes failed (non-200 status OR navigation error)`
    )
    process.exit(1)
  }
  if (hydrationIssues.length > 0) {
    console.error(`\n✗ ${hydrationIssues.length}/${summaries.length} routes had hydration errors`)
    process.exit(2)
  }
  console.log(
    `\n✓ All ${summaries.length} unauthed routes returned 200 + 0 hydration errors through Caddy → Node SSR → backend chain (theme=${THEME})`
  )
  console.log(`✓ W187 §H NEW #2 unauthed visual smoke CLOSED`)
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
