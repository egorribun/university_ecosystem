/**
 * playwright-visual-smoke.mjs — Windows-friendly visual smoke alternative.
 *
 * ## Why this exists
 *
 * `chrome-devtools-mcp` reliably hits CDP timeouts on Windows + headless
 * Chrome for `Accessibility.getFullAXTree` and `Runtime.evaluate` when the
 * target page has heavy DOM (e.g. authenticated routes with React
 * hydration + Framer Motion + glass effects). Symptom appeared in W132
 * polish round 2 perf APIs and re-surfaced in W135 SW2 visual smoke through
 * the Caddy chain. The MCP's own `list_network_requests` and
 * `list_console_messages` work fine — the wall is on snapshot/eval surface
 * specifically.
 *
 * Wave 136 SW3 establishes Playwright with **real Chrome**
 * (`channel: "chrome"`) as the standard Windows visual-smoke tool. Playwright
 * with extended timeouts bypasses the chrome-devtools-mcp wall entirely
 * because it doesn't go through the CDP backchannel that times out.
 *
 * ## What it captures
 *
 * - Screenshot (full-page PNG) → `.screenshots/wave136-visual-smoke/<route>.png`
 * - Console messages (info / warning / error) → stdout + JSON sidecar
 * - Network requests (URL + status + size) → stdout + JSON sidecar
 * - React hydration error count (extracted from console messages)
 *
 * ## Usage
 *
 *   # Default sweep (8 SSR routes + /login through Caddy at localhost):
 *   npm run visual:smoke
 *
 *   # Subset:
 *   VISUAL_SMOKE_URLS=login,events npm run visual:smoke
 *
 *   # Custom origin (default http://localhost via Caddy in docker-compose):
 *   VISUAL_SMOKE_ORIGIN=http://localhost:4173 npm run visual:smoke
 *
 *   # Headless (faster, useful for CI):
 *   VISUAL_SMOKE_HEADLESS=1 npm run visual:smoke
 *
 *   # Single route via flag:
 *   node ./scripts/playwright-visual-smoke.mjs --url=http://localhost/login
 *
 * ## Environment honored
 *
 * - `VISUAL_SMOKE_ORIGIN`     — base URL (default `http://localhost`, Caddy)
 * - `VISUAL_SMOKE_URLS`       — comma-separated paths; empty maps to `/`
 * - `VISUAL_SMOKE_HEADLESS`   — if set, run headless (default headed)
 * - `VISUAL_SMOKE_TIMEOUT_MS` — page operation timeout (default 60000)
 * - `VISUAL_SMOKE_OUT_DIR`    — output directory (default `.screenshots/wave136-visual-smoke`)
 *
 * ## CLI flags (override env)
 *
 * - `--url=<full-url>`  — single URL to smoke (overrides ORIGIN+URLS)
 * - `--routes=<csv>`    — comma-separated paths under ORIGIN
 * - `--headless`        — run headless
 *
 * ## Exit codes
 *
 * - 0: all routes captured successfully (any console errors logged but
 *      script doesn't fail unless explicit `--strict` flag set)
 * - 1: Playwright launch failure OR navigation error on any route
 * - 2: `--strict` mode + at least one route had React hydration errors
 *
 * ## Notes
 *
 * - Real Chrome required: `channel: "chrome"`. If Chrome is not installed at
 *   the system path, falls back to bundled Chromium (still bypasses CDP wall
 *   that affects chrome-devtools-mcp because Playwright uses its own
 *   protocol layer).
 * - Backend not required: routes that require auth (e.g. /dashboard) will
 *   redirect to /login — that's still a valid smoke target. To test authed
 *   routes through real Caddy chain, add valid `access_token_v2` cookie via
 *   future enhancement (out of W136 SW3 scope).
 */

import { existsSync } from "node:fs"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

import { chromium } from "playwright"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, "..")

const DEFAULT_ROUTES = [
  "/login",
  "/",
  "/dashboard",
  "/events",
  "/news",
  "/schedule",
  "/profile",
  "/settings",
  "/404",
]

function parseArgs() {
  const args = {
    url: null,
    routes: null,
    headless: false,
    strict: false,
  }
  for (const arg of process.argv.slice(2)) {
    if (arg.startsWith("--url=")) {
      args.url = arg.slice("--url=".length)
    } else if (arg.startsWith("--routes=")) {
      args.routes = arg.slice("--routes=".length)
    } else if (arg === "--headless") {
      args.headless = true
    } else if (arg === "--strict") {
      args.strict = true
    }
  }
  return args
}

function resolveTargets(cliArgs) {
  if (cliArgs.url) {
    return [{ path: new URL(cliArgs.url).pathname, fullUrl: cliArgs.url }]
  }

  const origin = process.env.VISUAL_SMOKE_ORIGIN ?? "http://localhost"
  const rawRoutes = cliArgs.routes ?? process.env.VISUAL_SMOKE_URLS ?? DEFAULT_ROUTES.join(",")

  const routes = rawRoutes
    .split(",")
    .map((p) => p.trim())
    .map((p) => (p === "" ? "/" : p.startsWith("/") ? p : `/${p}`))

  return routes.map((p) => ({
    path: p,
    fullUrl: `${origin.replace(/\/$/, "")}${p}`,
  }))
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

async function smokeRoute({ browser, target, outDir, timeoutMs, strict }) {
  const consoleMessages = []
  const networkRequests = []

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()
  page.setDefaultTimeout(timeoutMs)
  page.setDefaultNavigationTimeout(timeoutMs)

  page.on("console", (msg) => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    })
  })
  page.on("pageerror", (err) => {
    consoleMessages.push({
      type: "pageerror",
      text: err.message,
      stack: err.stack ?? null,
    })
  })

  page.on("request", (req) => {
    networkRequests.push({
      method: req.method(),
      url: req.url(),
      resourceType: req.resourceType(),
    })
  })
  page.on("response", (res) => {
    const reqIdx = networkRequests.findLastIndex((r) => r.url === res.url() && !r.status)
    if (reqIdx >= 0) {
      networkRequests[reqIdx].status = res.status()
    }
  })

  let navigationError = null
  let finalUrl = null
  let httpStatus = null
  let screenshotError = null
  let sidecarError = null

  // Phase 1 — navigation
  // waitUntil: "domcontentloaded" is more reliable than "load" because
  // pages with failing sub-resources (e.g. /api/v1/users/me 500 when
  // backend is down) keep the load event pending.
  try {
    const response = await page.goto(target.fullUrl, {
      waitUntil: "domcontentloaded",
      timeout: timeoutMs,
    })
    finalUrl = page.url()
    httpStatus = response?.status() ?? null
  } catch (err) {
    navigationError = err
  }

  // Phase 2 — settle + screenshot (best-effort; doesn't fail the run)
  if (!navigationError) {
    try {
      await page.waitForTimeout(1500)
      // Best-effort screenshot. Playwright's screenshot stability check can
      // hang on pages with continuous canvas (e.g. ParticleAuthBackground's
      // 1000-particle physics loop on /login) even with animations:disabled.
      // Console errors + network requests + final URL captured in sidecar
      // JSON are the diagnostic VALUE — screenshot is a nice-to-have visual
      // and is allowed to fail without failing the whole smoke.
      const screenshotPath = path.join(outDir, `${safeFilename(target.path)}.png`)
      await page.screenshot({
        path: screenshotPath,
        fullPage: false,
        animations: "disabled",
        timeout: 5_000,
      })
    } catch (err) {
      screenshotError = err
      console.warn(`  screenshot failed for ${target.path}: ${err.message ?? err}`)
    }

    try {
      const sidecarPath = path.join(outDir, `${safeFilename(target.path)}.json`)
      await writeFile(
        sidecarPath,
        JSON.stringify(
          {
            target,
            finalUrl,
            status: httpStatus,
            consoleMessages,
            networkRequestCount: networkRequests.length,
            networkRequests: networkRequests.slice(0, 50),
            timestamp: new Date().toISOString(),
          },
          null,
          2
        )
      )
    } catch (err) {
      sidecarError = err
      console.warn(`  sidecar write failed for ${target.path}: ${err.message ?? err}`)
    }
  }

  await context.close()

  const errors = consoleMessages.filter((m) => m.type === "error" || m.type === "pageerror")
  // W185 SW1: extend filter with W167 SW1 / wave137 regex pattern to catch production-minified
  // "Minified React error #418-427" hydration errors. Pre-W185 the filter only matched unminified
  // substrings ("hydrat" / "Hydration" / "did not match") and missed production React #418 firings
  // emitted by `vendor-react-*.js` — same W166 (z) #2 filter-too-narrow bug class.
  const hydrationErrors = consoleMessages.filter(
    (m) =>
      m.text.includes("hydrat") ||
      m.text.includes("Hydration") ||
      m.text.includes("did not match") ||
      /Minified React error #(418|419|420|421|422|423|424|425|426|427)/.test(m.text)
  )

  const summary = {
    path: target.path,
    fullUrl: target.fullUrl,
    finalUrl,
    httpStatus,
    success: !navigationError,
    navigationError: navigationError?.message ?? null,
    screenshotError: screenshotError?.message ?? null,
    sidecarError: sidecarError?.message ?? null,
    consoleErrorCount: errors.length,
    hydrationErrorCount: hydrationErrors.length,
    networkRequestCount: networkRequests.length,
    consoleErrorSamples: errors.slice(0, 3).map((e) => e.text),
  }

  return {
    ...summary,
    failed: !!navigationError || (strict && hydrationErrors.length > 0),
  }
}

function printSummaryTable(summaries) {
  const padRight = (str, n) => str.padEnd(n, " ")
  console.log("")
  console.log("=".repeat(96))
  console.log("Wave 136 SW3 — Playwright visual smoke summary")
  console.log("=".repeat(96))
  console.log(
    `${padRight("Path", 24)}${padRight("Status", 10)}${padRight(
      "Console err",
      14
    )}${padRight("Hydr err", 12)}${padRight("Net req", 10)}Final URL`
  )
  console.log("-".repeat(96))
  for (const s of summaries) {
    const status = s.success ? "OK" : "FAIL"
    console.log(
      `${padRight(s.path, 24)}${padRight(status, 10)}${padRight(
        String(s.consoleErrorCount),
        14
      )}${padRight(String(s.hydrationErrorCount), 12)}${padRight(
        String(s.networkRequestCount),
        10
      )}${s.finalUrl ?? "n/a"}`
    )
  }
  console.log("=".repeat(96))
}

async function main() {
  const cliArgs = parseArgs()
  const headless = cliArgs.headless || !!process.env.VISUAL_SMOKE_HEADLESS
  const timeoutMs = parseInt(process.env.VISUAL_SMOKE_TIMEOUT_MS ?? "60000", 10)
  const outDir = path.resolve(
    PROJECT_ROOT,
    process.env.VISUAL_SMOKE_OUT_DIR ?? ".screenshots/wave136-visual-smoke"
  )

  const targets = resolveTargets(cliArgs)

  console.log(`Wave 136 SW3 — Playwright visual smoke`)
  console.log(`  Routes: ${targets.length}`)
  console.log(`  Headless: ${headless}`)
  console.log(`  Timeout: ${timeoutMs}ms`)
  console.log(`  Output: ${outDir}`)
  console.log(`  Strict: ${cliArgs.strict}`)
  console.log("")

  if (!existsSync(outDir)) {
    await mkdir(outDir, { recursive: true })
  }

  let browser
  try {
    browser = await chromium.launch({
      channel: "chrome",
      headless,
    })
  } catch (err) {
    console.warn(`Real Chrome launch failed (${err.message}); falling back to bundled Chromium.`)
    browser = await chromium.launch({ headless })
  }

  const summaries = []
  try {
    for (const target of targets) {
      console.log(`→ ${target.path}`)
      const result = await smokeRoute({
        browser,
        target,
        outDir,
        timeoutMs,
        strict: cliArgs.strict,
      })
      summaries.push(result)
      const statusGlyph = result.success ? "✓" : "✗"
      console.log(
        `  ${statusGlyph} status=${result.success ? "OK" : "FAIL"} console_err=${result.consoleErrorCount} hydration_err=${result.hydrationErrorCount}`
      )
    }
  } finally {
    await browser.close()
  }

  printSummaryTable(summaries)

  const anyFailed = summaries.some((s) => s.failed)
  const anyNavError = summaries.some((s) => !s.success)

  if (anyNavError) {
    console.error("\nOne or more routes failed to navigate.")
    process.exit(1)
  }
  if (cliArgs.strict && anyFailed) {
    console.error("\n--strict mode: hydration errors detected.")
    process.exit(2)
  }
  console.log("\nVisual smoke complete.")
}

main().catch((err) => {
  console.error("Visual smoke fatal error:", err)
  process.exit(1)
})
