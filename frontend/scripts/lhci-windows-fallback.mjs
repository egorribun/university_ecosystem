/**
 * lhci-windows-fallback.mjs — permanent Windows-friendly LHCI wrapper.
 *
 * ## Why this exists
 *
 * `@lhci/cli` (invoked by `scripts/run-lhci.mjs` via `npx -y @lhci/cli@^0.15.1
 * collect`) reliably hits `EPERM: operation not permitted, rmSync
 * '\\?\C:\Temp\lighthouse.NNNNN'` on Windows. The error fires inside
 * `chrome-launcher.destroyTmp` BEFORE the LHR is written to `.lighthouseci/`,
 * so the entire `collect` phase aborts at the first URL — sub-batches via
 * `LHCI_URLS=p1,p2` don't help (failure is per-URL, not per-batch).
 *
 * ## Origin
 *
 * Wave 119 SW2 (commit `da3f99199`) created `wave119-lhci-single.mjs` as
 * scratch. Wave 119 polish + SW7 used it for full sweep verification.
 * Per Wave 118 + Wave 119 plan pattern, the scratch script was deleted at
 * end-of-wave. Wave 120 SW1 (Item #10) permanentizes it as this file —
 * because every future wave on Windows hits the same EPERM, the wrapper
 * needs to live in version control instead of being recreated each time.
 *
 * ## How it differs from `lhci collect`
 *
 * - **Embedded vite preview API** (NOT spawned subprocess): on Windows,
 *   detached node child processes don't stay alive without TTY stdin.
 *   `import { preview } from "vite"` keeps the server in this process.
 * - **Direct Lighthouse invocation per URL × per run**: Lighthouse
 *   writes the LHR JSON to `--output-path` BEFORE chrome-launcher's
 *   destroyTmp runs, so the LHR survives EPERM. `lhci collect` instead
 *   chains lighthouse + assertion-buffering, which loses the LHR if EPERM
 *   fires before the buffer flushes.
 * - **Median computed locally**: parses LHR JSONs from `.lighthouseci/`
 *   and prints a 3-run median table per URL × per metric.
 * - **No assertion phase**: this script measures + reports only. CI on Linux
 *   still uses `npm run lhci` (which runs `collect` + `assert` together
 *   with no EPERM there).
 *
 * ## Usage
 *
 *   # Full default sweep (10 URLs × 3 runs):
 *   npm run lhci:windows
 *
 *   # Subset:
 *   LHCI_URLS=,dashboard,events npm run lhci:windows  # /, /dashboard, /events
 *   LHCI_URLS=login npm run lhci:windows              # /login only
 *
 *   # Skip rebuild (use existing dist/):
 *   SKIP_BUILD=1 npm run lhci:windows
 *
 *   # Single run instead of 3:
 *   LHCI_RUNS=1 npm run lhci:windows
 *
 *   # Custom port (default 4174 to match lhci-preview.mjs):
 *   LHCI_PREVIEW_PORT=4175 npm run lhci:windows
 *
 * ## Environment honored
 *
 * - `LHCI_URLS`        — comma-separated URL paths; empty segments map to "/"
 *   (omit/unset the variable to run the canonical ten-route default sweep)
 * - `LHCI_RUNS`        — runs per URL (default 3 for median; 1 for quick)
 * - `LHCI_PREVIEW_PORT`— vite preview port (default 4174)
 * - `LHCI_PREVIEW_HOST`— vite preview host (default 127.0.0.1)
 * - `SKIP_BUILD`       — if set, skip `npm run build` (assumes dist/ exists)
 * - `LHCI_THROTTLING`  — `devtools` (default) or `provided`
 * - `LHCI_FORM_FACTOR` — `mobile` (default) or `desktop`
 * - `VITE_LHCI`        — auto-set to "true" (auth bypass per `_auth.tsx`)
 *
 * ## Notes
 *
 * - The default sweep is sourced from `lhci-route-policy-config.cjs`, so the
 *   Windows fallback and Linux LHCI collect the same ten route URLs. This
 *   keeps performance evidence and route/privacy assertions on one inventory.
 * - Bundle invariant: `npm run build` defaults to non-VITE_LHCI mode. This
 *   wrapper sets `VITE_LHCI=true` BEFORE building, so dist/ is the LHCI
 *   build (174,839 bytes; auth bypass tree-shaken out of prod).
 */

import { mkdir, readdir, readFile, rm } from "node:fs/promises"
import { existsSync } from "node:fs"
import path from "node:path"
import process from "node:process"
import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import { preview } from "vite"

import { buildSafeCommandInvocation, resolveNpmCliPath } from "./lhci-command.mjs"
import routePolicyConfig from "./lhci-route-policy-config.cjs"
import { normalizeLhciPath } from "./lhci-route-policy.mjs"

export { buildSafeCommandInvocation, resolveNpmCliPath }

// Wave 121 SW2 — friendly OS guard. The Windows EPERM bug this wrapper works
// around (chrome-launcher destroyTmp rmSync firing before LHR write) is
// platform-specific. On Linux/macOS, `npm run lhci` is the canonical command:
// it's faster (no embedded vite preview API), runs `collect` + `assert`
// together (CI parity), and doesn't lose the assertion phase. The wrapper
// still works on non-Windows (the LHR-survives-cleanup-via---output-path
// approach is platform-agnostic), so we warn but keep going — useful for
// developers running on WSL/macOS who explicitly want consistent behavior
// with their Windows-using teammates.
if (process.platform !== "win32") {
  console.warn(
    `[wave-121-sw2] Non-Windows platform detected (${process.platform}). ` +
      "`npm run lhci` is faster on Linux/macOS and includes the assertion phase " +
      "(CI parity). Continuing with the wrapper anyway."
  )
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")
// W139 SW5 fix — post-W125 SSR migration, dist/ split into dist/client/ +
// dist/server/. Lighthouse must serve from dist/client/ where index.html
// lives. Pre-W125 it was dist/index.html. Defensive detection (matches
// prepare-lhci-routes.mjs + run-lhci.mjs).
const distClientDir = path.join(frontendRoot, "dist", "client")
const distLegacyDir = path.join(frontendRoot, "dist")
const distDir = existsSync(path.join(distClientDir, "index.html")) ? distClientDir : distLegacyDir
const lhrDir = path.join(frontendRoot, ".lighthouseci")

// CRITICAL: set VITE_LHCI BEFORE any build invocation so Rolldown DCE
// substitutes %VITE_LHCI% → "true" in dist/index.html (per run-build.mjs:74).
// This enables auth bypass in _auth.tsx + InstallPrompt push-panel skip
// (CLS-119-01) + InstallPrompt install-panel min-h reservation (CLS-119-02).
process.env.VITE_LHCI = "true"

const HOST = process.env.LHCI_PREVIEW_HOST ?? "127.0.0.1"
const PORT = Number.parseInt(process.env.LHCI_PREVIEW_PORT ?? "4174", 10)
const RUNS = Number.parseInt(process.env.LHCI_RUNS ?? "3", 10)
const THROTTLING = process.env.LHCI_THROTTLING ?? "devtools"
const FORM_FACTOR = process.env.LHCI_FORM_FACTOR ?? "mobile"
// Wave 121 SW8 — Lighthouse 13.x fixes the LanternError cycle-detection bug
// that blocked /activity + /map on 12.x. Default to 13.1.0 (latest stable);
// override via LIGHTHOUSE_VERSION=12.8.2 to compare with W120 baselines.
const LIGHTHOUSE_VERSION = process.env.LIGHTHOUSE_VERSION ?? "13.1.0"

// Keep the Windows fallback on the canonical route inventory used by the
// Linux runner and post-collection route-policy gate. The config intentionally
// stores prepared static-shell URLs with explicit trailing slashes so a
// Lighthouse run does not spend a navigation round-trip on server redirects.
export const DEFAULT_PATHS = Object.freeze([...routePolicyConfig.defaultLhciPaths])

// Delegate to the shared normalizer so route-name overrides (`dashboard`),
// empty segments (root), and explicit directory slashes (`dashboard/`) all
// behave identically across Windows and Linux LHCI collection.
export const normalizePath = normalizeLhciPath
// Match run-lhci.mjs semantics: an unset/empty environment value means "use
// defaults"; a leading comma explicitly requests the root path in a subset.
export function resolveLhciPaths(value) {
  const overridePaths = value
    ? value
        .split(",")
        .map(normalizePath)
        .filter((p, i, arr) => arr.indexOf(p) === i) // dedupe
    : undefined
  return overridePaths?.length ? overridePaths : DEFAULT_PATHS
}

const URL_PATHS = resolveLhciPaths(process.env.LHCI_URLS)

function urlToFilename(urlPath) {
  return urlPath === "/" ? "root" : urlPath.replace(/^\//, "").replace(/\//g, "_")
}

function median(values) {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

async function runCommand(command, args, description, options = {}) {
  return new Promise((resolve, reject) => {
    const { executable, args: spawnArgs } = buildSafeCommandInvocation(command, args)
    const child = spawn(executable, spawnArgs, {
      cwd: frontendRoot,
      stdio: options.silent ? "pipe" : "inherit",
      shell: false,
      windowsHide: true,
      env: { ...process.env, ...(options.env ?? {}) },
    })

    let stdout = ""
    let stderr = ""
    if (options.silent) {
      child.stdout?.on("data", (d) => (stdout += d.toString()))
      child.stderr?.on("data", (d) => (stderr += d.toString()))
    }

    child.on("exit", (code) => {
      if (code === 0) resolve({ stdout, stderr })
      else reject(new Error(`${description} exited with code ${code}\n${stderr}`))
    })
    child.on("error", reject)
  })
}

async function ensureBuild() {
  if (process.env.SKIP_BUILD) {
    if (!existsSync(distDir)) {
      throw new Error("SKIP_BUILD set but dist/ missing — run `npm run build` first")
    }
    console.log(`[skip-build] using existing dist/ (set VITE_LHCI=true to ensure auth bypass)`)
    return
  }
  console.log("[build] VITE_LHCI=true npm run build…")
  await runCommand("npm", ["run", "build"], "vite build")
  console.log("[build] preparing LHCI SPA route fallbacks…")
  await runCommand("node", ["scripts/prepare-lhci-routes.mjs"], "prepare-lhci-routes")
}

async function startPreview() {
  console.log(`[preview] starting vite preview on http://${HOST}:${PORT}/ …`)
  const server = await preview({
    root: frontendRoot,
    preview: { host: HOST, port: PORT, strictPort: true },
  })
  return server
}

async function clearLhrDir() {
  if (existsSync(lhrDir)) {
    const files = await readdir(lhrDir)
    await Promise.all(
      files
        .filter((f) => f.startsWith("lhr_"))
        .map((f) => rm(path.join(lhrDir, f), { force: true }))
    )
  } else {
    await mkdir(lhrDir, { recursive: true })
  }
}

async function runLighthouse(url, runIndex) {
  const urlName = urlToFilename(new URL(url).pathname)
  const outputPath = path.join(lhrDir, `lhr_${urlName}_run${runIndex}.json`)

  // Invoke Lighthouse through npm's JavaScript CLI. The CLI writes the LHR to
  // `--output-path` synchronously BEFORE chrome-launcher's destroyTmp
  // attempts the rmSync that triggers EPERM on Windows. Even when EPERM
  // fires, the LHR file already exists on disk, so the run is recoverable.
  const args = [
    "exec",
    "--yes",
    `--package=lighthouse@${LIGHTHOUSE_VERSION}`,
    "--",
    "lighthouse",
    url,
    `--output=json`,
    `--output-path=${outputPath}`,
    `--throttling-method=${THROTTLING}`,
    `--form-factor=${FORM_FACTOR}`,
    "--quiet",
    "--only-categories=performance,accessibility,best-practices,seo",
    "--chrome-flags=--no-sandbox --disable-dev-shm-usage --headless=new --disable-gpu",
  ]

  // Match run-lhci.mjs behavior: emulated mobile preset implies viewport.
  if (FORM_FACTOR === "mobile") {
    args.push(
      "--screenEmulation.mobile=true",
      "--screenEmulation.width=412",
      "--screenEmulation.height=823",
      "--screenEmulation.deviceScaleFactor=1.75"
    )
  }

  try {
    await runCommand("npm", args, `lighthouse ${url} run ${runIndex}`, { silent: true })
  } catch (err) {
    // Windows EPERM workaround — the LHR is on disk before destroyTmp fires.
    // If the file exists despite the error, treat as recoverable.
    if (existsSync(outputPath)) {
      const fsPromises = await import("node:fs/promises")
      const stat = await fsPromises.stat(outputPath)
      if (stat.size > 1000) {
        console.log(`  [run ${runIndex}] EPERM but LHR survived (${stat.size} bytes)`)
        return outputPath
      }
    }
    throw err
  }
  return outputPath
}

/**
 * LHR (Lighthouse Result) JSON property dependencies.
 *
 * Verified compatible with Lighthouse 13.1.0 schema (Wave 122 SW4 audit
 * against `.lighthouseci/lhr_news_run1.json` produced by `npm run lhci:windows`):
 *
 *   lhr.categories.{performance,accessibility,best-practices,seo}.score
 *   lhr.audits.{cumulative-layout-shift,largest-contentful-paint,total-blocking-time}.numericValue
 *
 * The 7 paths above are the only LHR fields this wrapper reads. They have
 * been stable across Lighthouse 12.x → 13.x; if you bump Lighthouse to a
 * future major (14.x+), re-verify these paths still exist in a sample LHR
 * before merging the bump. Optional chaining + null-coalescing make the
 * wrapper resilient to a missing audit (returns null in summary table).
 *
 * For OTHER LHR fields (network-requests, audits["unused-javascript"],
 * audits["image-delivery-insight"], etc.) the wrapper does NOT read them
 * directly — those are inspected via ad-hoc `node -e` scripts during audit
 * waves (see Wave 121 polish A4 + Wave 122 SW1/SW2 commits for examples).
 */
export async function parseLhr(lhrPath) {
  const raw = await readFile(lhrPath, "utf8")
  const lhr = JSON.parse(raw)
  const categories = lhr?.categories
  const audits = lhr?.audits
  const requiredCategories = ["performance", "accessibility", "best-practices", "seo"]
  if (
    !lhr ||
    typeof lhr !== "object" ||
    Array.isArray(lhr) ||
    !categories ||
    typeof categories !== "object" ||
    Array.isArray(categories) ||
    !audits ||
    typeof audits !== "object" ||
    Array.isArray(audits) ||
    requiredCategories.some((name) => !categories[name] || typeof categories[name] !== "object")
  ) {
    throw new Error(`Invalid Lighthouse result at ${lhrPath}`)
  }
  return {
    perf: categories.performance?.score ?? null,
    a11y: categories.accessibility?.score ?? null,
    bp: categories["best-practices"]?.score ?? null,
    seo: categories.seo?.score ?? null,
    cls: audits["cumulative-layout-shift"]?.numericValue ?? null,
    lcp: audits["largest-contentful-paint"]?.numericValue ?? null,
    tbt: audits["total-blocking-time"]?.numericValue ?? null,
  }
}

/**
 * A successful wrapper run must have one parseable LHR for every requested
 * URL/run pair.  Partial measurements are useful diagnostics, but are not
 * valid quality evidence and therefore fail closed.
 */
export function assertCompleteLighthouseResults(results, expectedRuns = RUNS) {
  if (!(results instanceof Map) || !Number.isInteger(expectedRuns) || expectedRuns < 1) {
    throw new TypeError("Lighthouse result validation inputs are invalid")
  }

  const missing = []
  const metricKeys = ["perf", "a11y", "bp", "seo", "cls", "lcp", "tbt"]
  for (const [urlPath, runs] of results) {
    if (!Array.isArray(runs)) {
      missing.push(`${urlPath}: invalid run collection`)
      continue
    }
    if (runs.length !== expectedRuns) {
      missing.push(`${urlPath}: expected ${expectedRuns} runs, received ${runs.length}`)
    }
    runs.forEach((result, index) => {
      const validResult =
        result &&
        typeof result === "object" &&
        !Array.isArray(result) &&
        metricKeys.every(
          (key) =>
            Object.hasOwn(result, key) && (result[key] === null || typeof result[key] === "number")
        )
      if (!validResult) {
        missing.push(`${urlPath} run ${index + 1}`)
      }
    })
  }

  if (missing.length > 0) {
    throw new Error(
      "Lighthouse fallback did not produce a valid LHR for every URL/run: " + missing.join(", ")
    )
  }
}

function formatRow(label, perf, cls, lcp, tbt, a11y) {
  const isHeader = typeof perf === "string"
  const fmtScore = (v) =>
    isHeader || typeof v === "string"
      ? String(v).padStart(5)
      : v == null
        ? "  -  "
        : v.toFixed(2).padStart(5)
  const fmtMs = (v) =>
    isHeader || typeof v === "string"
      ? String(v).padStart(6)
      : v == null
        ? "    - "
        : `${Math.round(v)}ms`.padStart(6)
  const fmtCls = (v) =>
    isHeader || typeof v === "string"
      ? String(v).padStart(5)
      : v == null
        ? "  -  "
        : v.toFixed(3).padStart(5)
  return `${label.padEnd(14)} | ${fmtScore(perf)} | ${fmtCls(cls)} | ${fmtMs(lcp)} | ${fmtMs(tbt)} | ${fmtScore(a11y)}`
}

async function main() {
  const startTime = Date.now()

  console.log(`[wave-120-sw1] lhci-windows-fallback.mjs`)
  console.log(`  URLs:        ${URL_PATHS.join(", ")}`)
  console.log(`  Runs:        ${RUNS}`)
  console.log(`  Throttling:  ${THROTTLING}`)
  console.log(`  Form-factor: ${FORM_FACTOR}`)
  console.log(`  Preview:     http://${HOST}:${PORT}/`)
  console.log()

  await ensureBuild()
  await clearLhrDir()
  const server = await startPreview()

  const baseUrl = `http://${HOST}:${PORT}`
  const results = new Map() // url → array of metrics per run

  try {
    for (const urlPath of URL_PATHS) {
      const url = `${baseUrl}${urlPath === "/" ? "" : urlPath}`
      const runs = []
      console.log(`\n[measure] ${urlPath}`)
      for (let i = 1; i <= RUNS; i++) {
        try {
          const lhrPath = await runLighthouse(url, i)
          const metrics = await parseLhr(lhrPath)
          runs.push(metrics)
          console.log(
            `  run ${i}: perf=${metrics.perf?.toFixed(2)} cls=${metrics.cls?.toFixed(3)} lcp=${Math.round(metrics.lcp ?? 0)}ms tbt=${Math.round(metrics.tbt ?? 0)}ms a11y=${metrics.a11y?.toFixed(2)}`
          )
        } catch (err) {
          // Full error message including stderr — shortened first-line
          // version was hiding root cause (e.g. shell-quoting bugs in
          // Wave 120 SW1 dev).
          console.warn(`  run ${i}: FAILED`)
          console.warn(`    ${err.message.replace(/\n/g, "\n    ")}`)
          runs.push(null)
        }
      }
      results.set(urlPath, runs)
    }
  } finally {
    console.log(`\n[preview] stopping vite preview…`)
    // W162 SW2 (Tier 2 Path C refined) — Promise.race timeout closes W159
    // §Honesty NEW #1 (vite preview server.close() hangs on Windows due to
    // Worker thread active handles per W136 SW5 trace identifying
    // `MessagePort + Pipe + Socket × 2`; same family as W126 polish #3
    // vite-plugin-pwa Windows hang). The W148 SW3 Promise.race fast-fail
    // pattern bounds the cleanup wait to a hard 5s ceiling; if close()
    // doesn't return within that window, the explicit process.exit(0)
    // call after summary table printing terminates the event loop
    // regardless of lingering handles. W126 polish #3 deeper Worker thread
    // root cause stays open as W163+ candidate.
    const SERVER_CLOSE_TIMEOUT_MS = 5000
    await Promise.race([
      server.close(),
      new Promise((resolve) =>
        setTimeout(() => {
          console.warn(
            `  [server.close] ${SERVER_CLOSE_TIMEOUT_MS}ms timeout — proceeding to summary + force-exit`
          )
          resolve()
        }, SERVER_CLOSE_TIMEOUT_MS)
      ),
    ])
  }

  // Print median summary table.
  console.log("\n" + "=".repeat(80))
  console.log(
    `MEDIAN (${RUNS}-run) ${FORM_FACTOR} preset, ${THROTTLING} throttling, VITE_LHCI=true build`
  )
  console.log("=".repeat(80))
  console.log(formatRow("URL", "Perf", "CLS", "LCP", "TBT", "A11y"))
  console.log("-".repeat(80))

  for (const [urlPath, runs] of results) {
    const valid = runs.filter((r) => r != null)
    if (valid.length === 0) {
      console.log(`${urlPath.padEnd(14)} | (all runs failed)`)
      continue
    }
    const perfMed = median(valid.map((r) => r.perf).filter((v) => v != null))
    const clsMed = median(valid.map((r) => r.cls).filter((v) => v != null))
    const lcpMed = median(valid.map((r) => r.lcp).filter((v) => v != null))
    const tbtMed = median(valid.map((r) => r.tbt).filter((v) => v != null))
    const a11yMed = median(valid.map((r) => r.a11y).filter((v) => v != null))
    console.log(formatRow(urlPath, perfMed, clsMed, lcpMed, tbtMed, a11yMed))
  }

  assertCompleteLighthouseResults(results, RUNS)

  const elapsedMin = ((Date.now() - startTime) / 60000).toFixed(1)
  console.log("=".repeat(80))
  console.log(`Total elapsed: ${elapsedMin} min`)
  console.log(`LHRs saved to: ${path.relative(frontendRoot, lhrDir)}/`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main()
    .then(() => {
      // W162 SW2 — explicit process.exit(0) ensures the wrapper terminates
      // cleanly even when vite preview's underlying Worker thread doesn't
      // fully release the event loop after server.close() (or after the
      // Promise.race timeout fires). Same hang family as W126 polish #3 /
      // W135 SW3 / W136 SW5 trace agent finding. Without this, the script
      // hangs indefinitely after printing the summary table, requiring
      // manual Ctrl+C to terminate — recorded as W159 §Honesty NEW #1.
      process.exit(0)
    })
    .catch((err) => {
      console.error("\n[lhci-windows-fallback] fatal:", err)
      process.exit(1)
    })
}
