/**
 * unauthenticated-routes-smoke.mjs — public-route SSR visual smoke
 *
 * Visual smoke for the 4 PUBLIC unauthenticated routes through real Caddy →
 * Node SSR → backend chain. Mirrors the authenticated visual-audit structure minus
 * the auth chokepoint (CSRF dance + login POST + JWKS pre-check + JWT
 * decode/validation) since unauthenticated visitors never traverse those
 * code paths.
 *
 * Routes covered:
 *   - /login              (login form)
 *   - /register           (registration form)
 *   - /forgot-password    (password-reset request form)
 *   - /reset-password     (no $token — shows "missing token" error UI OR
 *                          redirects to /forgot-password depending on route
 *                          guard; either is acceptable for SSR-shell smoke)
 *
 * Three-layer theme initialization:
 * Apply Cookie + localStorage(via addInitScript) + emulateMedia BEFORE
 * page.goto so both SSR initial render AND client hydration converge on
 * the same theme. Default theme = "light" (unauth visitors typically don't
 * have a stored preference yet). Dark theme runs are gated by THEME env.
 *
 * ## Usage
 *
 *   node ./scripts/unauthenticated-routes-smoke.mjs
 *
 *   # Override target origin / output dir / theme:
 *   ORIGIN=http://localhost \
 *     THEME=dark \
 *     OUT_DIR=.screenshots/unauthenticated-routes-smoke-dark \
 *     node ./scripts/unauthenticated-routes-smoke.mjs
 *
 * ## Exit codes
 *
 *   0: all 4 routes return HTTP 200 + 0 hydration errors
 *   1: 1+ routes returned non-200 status OR navigation error
 *   2: 1+ routes had hydration errors detected (React #418-#427 family OR
 *      "hydrat" / "Hydration" / "did not match" substring match)
 */

import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

import {
  classifySmokeFailures,
  requestFailureRecord,
  responseRecord,
} from "./visual-smoke-contract.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

const ORIGIN = process.env.ORIGIN ?? "http://localhost"
const THEME = process.env.THEME ?? "light"
const OUT_DIR = path.resolve(
  PROJECT_ROOT,
  process.env.OUT_DIR ?? ".screenshots/unauthenticated-routes-smoke"
)

const PUBLIC_ROUTES = [
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

async function smokePublicRoute(page, routePath, theme, outDir) {
  const consoleMessages = []
  const networkResponses = []
  const networkFailures = []

  const consoleHandler = (msg) => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    })
  }
  const pageErrorHandler = (err) => {
    consoleMessages.push({ type: "pageerror", text: err.message })
  }
  const responseHandler = (res) => {
    networkResponses.push(responseRecord(res))
  }
  const requestFailedHandler = (request) => {
    networkFailures.push(requestFailureRecord(request))
  }

  page.on("console", consoleHandler)
  page.on("pageerror", pageErrorHandler)
  page.on("response", responseHandler)
  page.on("requestfailed", requestFailedHandler)

  // Initialize all three theme sources before page.goto so both
  // SSR initial render AND client hydration converge on the correct theme.
  // A cookie drives SSR, localStorage drives client state, and emulateMedia
  // covers system-preference reads. A single source cannot guarantee parity.
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
    // Give hydration, motion, and the initial paint a deterministic settle window.
    await page.waitForTimeout(1500)

    // Screenshot capture is optional and non-fatal; the JSON sidecar remains
    // the authoritative result when a browser cannot produce a snapshot.
    if (process.env.UNAUTHENTICATED_SMOKE_CAPTURE_SCREENSHOTS === "true") {
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
  page.off("response", responseHandler)
  page.off("requestfailed", requestFailedHandler)

  const { consoleErrors, hydrationErrors, nonSuccessfulResponses } = classifySmokeFailures({
    consoleMessages,
    networkResponses,
    networkFailures,
    allowUnauthenticatedProfileProbe: true,
  })

  // Persist one JSON sidecar per route for CI artifact inspection.
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
        networkResponseCount: networkResponses.length,
        networkResponses,
        nonSuccessfulResponses,
        networkFailures,
      },
      null,
      2
    )
  )

  return {
    path: routePath,
    theme,
    httpStatus,
    finalUrl,
    consoleErrorCount: consoleErrors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkErrorCount: nonSuccessfulResponses.length + networkFailures.length,
    networkResponseCount: networkResponses.length,
    sampleErrors: consoleErrors.slice(0, 3).map((e) => e.text),
    sampleNetworkErrors: nonSuccessfulResponses.slice(0, 3),
    sampleNetworkFailures: networkFailures.slice(0, 3),
    navError: navError?.message ?? null,
  }
}

function printSummary(summaries, theme) {
  const padR = (s, n) => String(s).padEnd(n, " ")
  console.log("")
  console.log("=".repeat(120))
  console.log(`Unauthenticated routes smoke (4 public routes, theme=${theme})`)
  console.log("=".repeat(120))
  console.log(
    `${padR("Path", 20)}${padR("HTTP", 8)}${padR("Console err", 14)}${padR(
      "Hydr err",
      12
    )}${padR("Net err", 10)}${padR("Net resp", 10)}Final URL`
  )
  console.log("-".repeat(120))
  for (const s of summaries) {
    console.log(
      `${padR(s.path, 20)}${padR(s.httpStatus ?? "-", 8)}${padR(
        s.consoleErrorCount,
        14
      )}${padR(s.hydrationErrorCount, 12)}${padR(s.networkErrorCount, 10)}${padR(
        s.networkResponseCount,
        10
      )}${s.finalUrl ?? "n/a"}`
    )
  }
  console.log("=".repeat(120))
}

async function main() {
  console.log(`Unauthenticated routes smoke through the real Caddy chain`)
  console.log(`  Origin: ${ORIGIN}`)
  console.log(`  Theme: ${THEME}`)
  console.log(`  Routes: ${PUBLIC_ROUTES.length}`)
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

  // Isolate service workers, IndexedDB, cookies, and storage per route so
  // route lifecycle defects cannot contaminate or hide another route's result.
  const summaries = []
  for (const route of PUBLIC_ROUTES) {
    console.log(`→ ${route}`)
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    const routePage = await context.newPage()
    routePage.setDefaultTimeout(30_000)
    routePage.setDefaultNavigationTimeout(30_000)
    const result = await smokePublicRoute(routePage, route, THEME, OUT_DIR)
    await routePage.close()
    await context.close()
    summaries.push(result)
    const glyph = result.httpStatus === 200 ? "✓" : "✗"
    console.log(
      `  ${glyph} http=${result.httpStatus} final=${result.finalUrl ? new URL(result.finalUrl).pathname : "n/a"} console_err=${result.consoleErrorCount} hydr_err=${result.hydrationErrorCount} net_err=${result.networkErrorCount} net_resp=${result.networkResponseCount}`
    )
  }

  await browser.close()

  printSummary(summaries, THEME)

  const failed = summaries.filter((s) => s.httpStatus !== 200)
  const hydrationIssues = summaries.filter((s) => s.hydrationErrorCount > 0)
  const runtimeIssues = summaries.filter((s) => s.consoleErrorCount > 0 || s.networkErrorCount > 0)

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
  if (runtimeIssues.length > 0) {
    console.error(
      `\n✗ ${runtimeIssues.length}/${summaries.length} routes had console/page/network errors`
    )
    process.exit(3)
  }
  console.log(
    `\n✓ All ${summaries.length} unauthed routes returned 200 + 0 hydration errors through Caddy → Node SSR → backend chain (theme=${THEME})`
  )
  console.log(`✓ Unauthenticated route smoke completed successfully`)
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
