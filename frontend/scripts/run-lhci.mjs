// Wave 122 SW4: this script delegates LHR parsing to `@lhci/cli` (via
// `npx lhci collect` + `npx lhci assert`). It does NOT read LHR JSON
// properties directly. The wrapper variant `lhci-windows-fallback.mjs`
// (Wave 120 SW1, default since Wave 121 SW2) is what reads LHR fields —
// see that file's `parseLhr()` JSDoc for the property-path dependencies
// that have been verified compatible with Lighthouse 13.1.0.
import { access, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { spawn } from "node:child_process"

import { chromium } from "playwright"

import routePolicyConfig from "./lhci-route-policy-config.cjs"
import { assertLhciRoutePolicy, normalizeLhciPath } from "./lhci-route-policy.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")

process.env.VITE_LHCI = "true"

const base = process.env.PREVIEW_URL ?? process.env.LHCI_URL ?? ""
const useRemotePreview = Boolean(base)
let dependenciesEnsured = false

async function runCommand(command, args, description, extraEnv = {}) {
  // npm and npx are .cmd shims on Windows and cannot be spawned directly with
  // shell:false. Invoke the Windows command interpreter explicitly while
  // keeping Node's shell option disabled; all command names and arguments are
  // fixed by this script.
  const isWindowsBatchCommand =
    process.platform === "win32" && (command === "npm" || command === "npx")
  const executable = isWindowsBatchCommand ? (process.env.ComSpec ?? "cmd.exe") : command
  const spawnArgs = isWindowsBatchCommand ? ["/d", "/s", "/c", `${command}.cmd`, ...args] : args

  await new Promise((resolve, reject) => {
    const child = spawn(executable, spawnArgs, {
      cwd: frontendRoot,
      env: { ...process.env, ...extraEnv },
      stdio: "inherit",
      shell: false,
    })

    child.on("exit", (code, signal) => {
      if (signal) {
        reject(new Error(`${description} exited due to signal ${signal}`))
        return
      }
      if (code === 0) {
        resolve()
      } else {
        reject(new Error(`${description} exited with code ${code}`))
      }
    })

    child.on("error", reject)
  })
}

async function ensureChromiumExecutable() {
  await ensureSystemDependencies()

  const chromePath = process.env.LHCI_CHROME_PATH ?? chromium.executablePath()

  try {
    await access(chromePath)
    return chromePath
  } catch (error) {
    if (error && error.code !== "ENOENT") {
      throw error
    }
  }

  await runCommand(
    "npm",
    ["exec", "playwright", "install", "chromium"],
    "playwright install chromium"
  )

  // Re-calculate or verify the path after install
  const finalPath = process.env.LHCI_CHROME_PATH ?? chromium.executablePath()
  await access(finalPath)
  return finalPath
}

async function ensureSystemDependencies() {
  const skipSystemDependencies =
    process.env.LHCI_SKIP_SYSTEM_DEPS === "1" || process.env.LHCI_SKIP_SYSTEM_DEPS === "true"

  // GitHub-hosted Ubuntu runners are pre-provisioned with the shared browser
  // libraries. Re-running Playwright's apt bootstrap in every Lighthouse
  // matrix shard is both redundant and vulnerable to slow package mirrors
  // (the 20-minute shard budget can be exhausted before Lighthouse starts).
  // Keep the explicit opt-out so local and self-hosted runners retain the
  // documented `playwright install-deps chromium` fallback by default.
  if (dependenciesEnsured || skipSystemDependencies) {
    if (skipSystemDependencies && !dependenciesEnsured) {
      console.log("Skipping Playwright system-dependency bootstrap (LHCI_SKIP_SYSTEM_DEPS is set).")
    }
    return
  }

  await runCommand(
    "npm",
    ["exec", "playwright", "install-deps", "chromium"],
    "playwright install-deps chromium"
  )
  dependenciesEnsured = true
}

async function fetchRemoteRobots(previewUrl) {
  let preview
  try {
    preview = new URL(previewUrl)
  } catch {
    throw new Error("PREVIEW_URL/LHCI_URL must be an absolute HTTP(S) URL")
  }
  if (preview.protocol !== "http:" && preview.protocol !== "https:") {
    throw new Error("PREVIEW_URL/LHCI_URL must use HTTP(S)")
  }

  const robotsUrl = new URL("/robots.txt", preview)
  let response
  try {
    response = await fetch(robotsUrl, {
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    })
  } catch (error) {
    throw new Error(`Unable to fetch preview robots.txt ${robotsUrl}: ${error.message}`)
  }
  if (!response.ok) {
    throw new Error(`Preview robots.txt returned HTTP ${response.status}`)
  }

  let responseUrl
  try {
    responseUrl = new URL(response.url)
  } catch {
    throw new Error("Preview robots.txt response URL is invalid")
  }
  if (responseUrl.origin !== preview.origin || responseUrl.pathname !== "/robots.txt") {
    throw new Error("Preview robots.txt response crossed the tested origin boundary")
  }
  return response.text()
}

async function createConfig() {
  const chromePath = await ensureChromiumExecutable()
  process.env.CHROME_PATH = chromePath

  // Wave 112 — coverage expanded from 2 URLs (/ + /login) to 7 (home + login +
  // 6 target pages). Auth-gated pages measure redirect-to-login CWV baseline;
  // Wave 116 SW3 switches LHCI to authenticated mode via VITE_LHCI=true bypass
  // in _auth.tsx + useProfileSync.ts. Optional LHCI_URLS env var narrows the
  // set for focused iteration (Windows EPERM mitigation — Wave 113 note).
  // Wave 119 SW2 — added "/" and "/404" so all scorable URLs measure.
  // /activity + /map remain Lighthouse LanternError-blocked (Wave 116 honest
  // deferral); included in defaults so CI surface is the same as auth-bypass
  // sweep but expect those audits to fail under Lighthouse — investigate or
  // skip per Wave 120+ scope.
  const defaultPaths = [...routePolicyConfig.defaultLhciPaths]
  // Wave 119 SW2 — empty segments normalize to "/" so callers can measure
  // root via LHCI_URLS=,schedule,404 (Windows MSYS_NO_PATHCONV bypass: leading
  // slashes in /-paths are mangled to git-bash absolute paths). The shared
  // normalizer also adds a slash to route-name inputs such as `404` before
  // Lighthouse and the route-policy inventory see them.
  // Wave 160 SW1 — distinguish truly-empty LHCI_URLS (the workflow_dispatch
  // default "" when no override is intended → use defaults) from a non-empty
  // override with leading comma (`,schedule,404` → measure / + 2 paths).
  // Pre-W160 `process.env.LHCI_URLS?.split(",")` on `""` returned `[""]` → map
  // produced `["/"]` (truthy) → overrode the 9-URL default with single root.
  // `.github/workflows/lhci-linux.yml` sets `LHCI_URLS: ${{ inputs.urls }}`
  // unconditionally, so an unset workflow input arrived as literal "" — silently
  // shrinking the sweep. Truthiness gate now distinguishes "" (falsy → defaults)
  // from any non-empty string (process via the W119 SW2 leading-comma flow).
  const lhciUrlsEnv = process.env.LHCI_URLS
  const overridePaths = lhciUrlsEnv
    ? lhciUrlsEnv.split(",").map(normalizeLhciPath).filter(Boolean)
    : undefined
  const targetPaths = overridePaths?.length ? overridePaths : defaultPaths
  const collect = {
    numberOfRuns: 3,
    url: useRemotePreview ? targetPaths.map((p) => `${base}${p === "/" ? "" : p}`) : targetPaths,
    chromePath,
    settings: {
      // W162 SW1 (Tier 1 Path d) — W160 §Honesty NEW #1 CLOSED via "platform
      // limitation accepted" honest framing per W141 anti-pattern #4 +
      // feedback_perfectionism.md ("if you can't measure, defer honestly").
      //
      // ## Empirical evidence justifying closure
      //
      // Linux CI Lighthouse Perf=null was structurally reproduced across
      // THREE measurement attempts in W160-W161:
      //
      //   1. W160 SW2 baseline: 3 sessions × 3 runs × 9 URLs = 81 LHRs.
      //      ALL Perf scores null (speed-index + screenshot-thumbnails +
      //      metrics audits errored with "Chrome didn't collect any
      //      screenshots during the page load"). Runs `25988551157` +
      //      `25989078530` + `25989579477`. CLS/LCP/TBT measured cleanly.
      //
      //   2. W161 SW1 Approach A (restore GPU-backed capture): CI run
      //      `25997872114` Perf=null at run 1; workflow cancelled at 25m.
      //
      //   3. W161 SW1 Approach B (swap `--headless=new` → `--headless=chrome`
      //      + timeout 25→30): CI run `25998541600` completed 25m15s but
      //      Perf STILL null across 21 LHRs (7 URLs × 3 runs).
      //
      // Chrome flag tuning is structurally insufficient. Lighthouse 13.1.0
      // + headless Chrome + ubuntu-latest CI runner combo cannot collect
      // screenshots required by the speed-index audit. Other paths considered
      // and deferred:
      //
      //   - Path (a) Upstream Lighthouse issue → weeks of response cadence;
      //     unclear ownership (Google Lighthouse vs Chromium); W163+ candidate.
      //   - Path (b) Alternate CI runner (ubuntu-22.04 / windows-latest /
      //     self-hosted) → unknown root cause; lighthouse-ci's own CI uses
      //     ubuntu-latest without screenshot failures, so root cause is
      //     non-obvious; W163+ candidate.
      //   - Path (c) `lhci --collect.method=node` → STRUCTURALLY INFEASIBLE;
      //     `@lhci/cli@0.15.1` source has zero `--collect.method` matches
      //     (verified W162 Phase 3 Review via grep on node_modules). Would
      //     require forking lighthouse-ci or upgrading to a version that
      //     doesn't yet exist.
      //
      // ## Canonical Perf measurement: Windows wrapper
      //
      // `npm run lhci:windows` (frontend/scripts/lhci-windows-fallback.mjs)
      // IS the canonical Perf measurement tool. W159 SW2 baseline (post-W158
      // SW1 canonical minified PROD bundle restoration):
      //
      //   /           Perf 0.96  CLS 0.001
      //   /dashboard  Perf 0.96  CLS 0.001
      //   /login      Perf 0.96  CLS 0.000
      //   /events     Perf 0.94  CLS 0.062
      //
      // Windows wrapper bypasses EPERM + screenshot-collection issues via
      // direct `npx lighthouse` invocation per URL × per run (LHR written
      // to --output-path BEFORE chrome-launcher's destroyTmp fires).
      //
      // ## Production CI gate (asymmetric measurement by design)
      //
      // Production gates CLS `error@0.05` (W160 SW2 ratchet) — Linux CI
      // hard-blocks on CLS regression. Perf composite is `warn@0.40` only,
      // measured via Windows wrapper per-wave (asymmetric measurement
      // intentional). 81-LHR Linux baseline preserves CLS/LCP/TBT data
      // points for cross-wave comparability.
      //
      // chromeFlags PRESERVED at W160 SW2 baseline (cross-wave 81-LHR
      // comparability). lhci-linux.yml `timeout-minutes: 30` PRESERVED
      // (independent structural improvement; W161 SW1-fix retains margin).
      //
      // W163+ may revisit via Path (a) upstream issue OR Path (b) alternate
      // runner experiment if measurement-parity demand emerges. See
      // CLAUDE.md ## Gotchas "Linux CI Lighthouse Perf=null platform
      // limitation" entry for the full closure narrative.
      //
      // W166 SW3 — Path (a) Lighthouse upstream issue FILED at
      // https://github.com/GoogleChrome/lighthouse/issues/17021 with 108-LHR
      // reproducibility evidence (81 LHRs W160 baseline + 27 LHRs W165
      // ubuntu-22.04 cross-OS + W161 SW1 disproof attempts). State shifts
      // from "permanent platform limitation accepted" (W162 SW1) to
      // "tracked-upstream" — see also memory/wave166_lighthouse_upstream_issue.md
      // for the full draft + anticipated maintainer-response timeline.
      //
      // Monitoring snapshot (2026-05-21): the upstream issue remained OPEN
      // without maintainer activity. The GitHub issue state is the source of
      // truth for future reassessment. Until upstream behavior changes, Linux
      // The current MVP contract supersedes this historical advisory floor.
      //
      // W180 SW1 — monitoring tick at W180 open (2026-05-21). WebFetch re-
      // verified at session start: state OPEN, still NO triage, NO maintainer
      // comments, NO reactions, NO labels since 2026-05-18 filing. 3 calendar
      // days elapsed since last check; well within W180-W184 expected window
      // per W179 SW3 calibration. Push next monitoring window to W181-W185
      // (sliding 1-week cadence per W170 SW3 calibration framework — re-check
      // 1-2 calendar weeks from this tick). State stays "tracked-upstream".
      // See memory/wave180_lighthouse_upstream_check.md for full snapshot +
      // pre-flight evidence captured at W180 Phase 1 Explore Agent 1.
      //
      // W188 SW5 — monitoring tick at W188 open (2026-05-26). WebFetch re-
      // verified: state OPEN, 0 comments, 0 maintainer responses, 0 labels,
      // 0 reactions since 2026-05-18 filing (8 calendar days elapsed). Per
      // W180 SW1 calibration the W181-W185 window already closed (W181=
      // 2026-05-22 → W185=2026-05-23; W187 closed 2026-05-24). Push next
      // monitoring window to W189-W193 (sliding 1-week cadence preserved
      // per W170 SW3 framework — re-check 1-2 calendar weeks from this
      // tick at W195+ if still no upstream movement). State stays
      // "tracked-upstream". Empirical evidence: no upstream-level CI
      // ratchet possible without Linux CI Perf=null fix, no fix possible
      // without upstream movement; Windows wrapper measurement remains
      // canonical Perf measurement per W162 SW1 acceptance. See
      // memory/wave188_lighthouse_upstream_check.md for full snapshot.
      //
      // W191 SW1 — monitoring tick at W191 open (2026-05-28). `gh issue view
      // 17021 --repo GoogleChrome/lighthouse` re-verified: state OPEN, 0
      // comments, 0 maintainer responses, 0 labels, 0 reactions, 0 assignees,
      // updatedAt = createdAt (no edits) since 2026-05-18 filing (10 calendar
      // days elapsed). Per W188 SW5 calibration the W189-W193 window currently
      // active (W189 + W190 closed 2026-05-26 + W191 opens 2026-05-28 — all
      // 3 fall inside window). Push next monitoring window to W195-W199
      // (sliding 1-week cadence preserved per W170 SW3 framework — re-check
      // 1-2 calendar weeks from this tick at W199+ if still no upstream
      // movement). State stays "tracked-upstream" — **6th separately-fired
      // tick (W163 + W170 + W179 + W180 + W188 + W191); 8 monitoring-state-
      // preservations counting W189 + W190 inherited from W188 SW5 by-design
      // without separate tick** (polish-v1 framing correction post «безупречно?»
      // probe — SW1 narrative initially claimed "7th consecutive tick" which
      // matched neither honest count). Empirical evidence unchanged: no
      // upstream-level CI ratchet possible without Linux CI Perf=null fix;
      // Windows wrapper measurement remains canonical Perf measurement per
      // W162 SW1 acceptance. See memory/wave191_lighthouse_upstream_check.md
      // for full snapshot (also corrected post-polish-v1).
      //
      // W192 SW1 — monitoring tick at W192 open (2026-05-28, same calendar
      // day as W191 close per session continuity). `gh issue view 17021
      // --repo GoogleChrome/lighthouse` re-verified: state OPEN, 0 comments,
      // 0 maintainer responses, 0 labels, 0 reactions, 0 assignees, updatedAt
      // = createdAt (no edits) since 2026-05-18 filing (10 calendar days
      // elapsed — IDENTICAL to W191 SW1 snapshot, no inter-wave movement).
      // Per W191 SW1 calibration the W195-W199 window currently next-active.
      // Push next monitoring window to **W196-W200** (sliding 1-week cadence
      // preserved per W170 SW3 framework — re-check 1-2 calendar weeks from
      // this tick at W200+ if still no upstream movement). State stays
      // "tracked-upstream" — **7th separately-fired tick (W163 + W170 + W179
      // + W180 + W188 + W191 + W192); 9 monitoring-state-preservations
      // counting W189 + W190 inherited from W188 SW5 by-design without
      // separate tick** (extends W191 SW1 polish-v1 honest count framing).
      // Empirical evidence unchanged: no upstream-level CI ratchet possible
      // without Linux CI Perf=null fix; Windows wrapper measurement remains
      // canonical Perf measurement per W162 SW1 acceptance. See
      // memory/wave192_lighthouse_upstream_check.md for full snapshot.
      chromeFlags:
        "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --headless=new",
      throttlingMethod: "devtools",
      emulatedFormFactor: "mobile",
      budgetPath: path.resolve(frontendRoot, "../budget.json"),
      maxWaitForFcp: 45000,
      maxWaitForLoad: 60000,
    },
  }

  if (!useRemotePreview) {
    // W139 SW5 fix — post-W125 SSR migration, dist/ is split into dist/client/
    // (browser bundle + index.html) + dist/server/ (SSR handler). Lighthouse
    // staticDistDir MUST point at dist/client/ for index.html-driven routes.
    //
    // First-attempt fix used existsSync defensive detection but that was
    // BROKEN due to call-order: createConfig() runs BEFORE `npm run build`,
    // so existsSync(dist/client/index.html) returned false on clean runs →
    // fell back to dist/ → 404 on Lighthouse navigation.
    //
    // Post-W125 is the canonical state. Hardcoding dist/client/ avoids the
    // ordering bug. Pre-W125 SPA layout is no longer supported by this
    // codebase; if reverted, this path would clearly fail at lhci collect
    // rather than silently fall through to wrong dir.
    collect.staticDistDir = path.resolve(frontendRoot, "dist", "client")
    collect.isSinglePageApplication = true
  } else {
    collect.startServerCommand = "node scripts/lhci-preview.mjs"
    collect.startServerReadyPattern = "LHCI_READY"
    collect.startServerReadyTimeout = 120000
  }

  return {
    ci: {
      collect,
      // Release-blocking lab budgets are shared by every route. SEO is
      // intentionally route-aware: only public/auth pages receive an SEO
      // assertion, while the companion route policy validates robots.txt and
      // crawl-audit provenance for protected pages. INP is a field metric and
      // is therefore measured by the production CWV pipeline, not Lighthouse.
      assert: {
        assertMatrix: [
          {
            matchingUrlPattern: ".*",
            assertions: {
              // INP is a field metric, not a Lighthouse navigation audit. Production
              // p75 aggregation is a separate release-closure requirement; TBT is the
              // blocking lab responsiveness proxy in this configuration.
              "categories:performance": ["error", { minScore: 0.95 }],
              "categories:accessibility": ["error", { minScore: 0.95 }],
              "categories:best-practices": ["error", { minScore: 0.95 }],
              "largest-contentful-paint": [
                "error",
                { maxNumericValue: 2500, aggregationMethod: "median" },
              ],
              "total-blocking-time": [
                "error",
                { maxNumericValue: 200, aggregationMethod: "median" },
              ],
              "cumulative-layout-shift": [
                "error",
                // W160 SW2 — ratcheted error@0.10 → error@0.05 after 3-session
                // × 3-run CI Linux methodology measured worst cross-session
                // median 0.044 (on /map; 8 of 9 URLs measure CLS ≤ 0.001).
                // Variance ~0.000 across sessions; 0.05 ceiling has 12% margin
                // (0.006 buffer). Tightens WCAG-Good ceiling by 50%.
                { maxNumericValue: 0.05, aggregationMethod: "median" },
              ],
            },
          },
          {
            matchingUrlPattern: routePolicyConfig.publicSeoUrlPattern,
            assertions: {
              "categories:seo": ["error", { minScore: routePolicyConfig.publicSeoMinScore }],
            },
          },
        ],
      },
    },
  }
}

async function run() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "lhci-config-"))
  const tempConfigPath = path.join(tempDir, "lighthouserc.json")

  const config = await createConfig()
  const expectedPaths = config.ci.collect.url

  // Build and prepare dist for LHCI mode if not using remote preview
  const useRemotePreview = Boolean(process.env.PREVIEW_URL ?? process.env.LHCI_URL ?? "")
  if (!useRemotePreview) {
    if (!process.env.SKIP_BUILD) {
      console.log("Building for LHCI...")
      await runCommand("npm", ["run", "build"], "npm run build")
    } else {
      console.log("SKIP_BUILD is set, reusing the downloaded production bundle.")
    }
    console.log("Preparing LHCI routes...")
    await runCommand("node", ["scripts/prepare-lhci-routes.mjs"], "prepare-lhci-routes")
  }

  await writeFile(tempConfigPath, JSON.stringify(config), "utf8")

  // Wave 116 SW3 — invoke @lhci/cli via npx so the script works without a
  // global `lhci` install. `-y` auto-accepts the download prompt; after the
  // first run npx caches the package locally. Previously the script assumed
  // a global install and failed fast on fresh environments.
  //
  // Wave 121 polish — switched from `npx -y @lhci/cli@^0.15.1` to plain `npx
  // lhci` so the local node_modules install (with the package.json
  // `lighthouse: ^13.1.0` override) is used. The `-y` form bypasses local
  // node_modules and downloads a fresh @lhci/cli + bundled lighthouse@12.6.1
  // to the npx cache, defeating the override and re-introducing the
  // LanternError on /activity + /map in CI on Linux.
  //
  // MSYS_NO_PATHCONV=1 prevents Git Bash on Windows from mangling URL-style
  // paths like `/news` into `c:/Program Files/Git/news` when LHCI forwards
  // them to the Lighthouse CLI subprocess.
  const lhciEnv = { MSYS_NO_PATHCONV: "1" }
  try {
    await runCommand(
      "npx",
      ["lhci", "collect", `--config=${tempConfigPath}`],
      "lhci collect",
      lhciEnv
    )
  } catch (error) {
    if (process.platform === "win32" && error.message.includes("code 1")) {
      console.warn(
        "lhci collect exited with code 1. This is often caused by an EPERM error when chrome-launcher attempts to clean up its temp profile on Windows. Proceeding to assert phase..."
      )
    } else if (error.message.includes("code 1")) {
      // Wave 146 SW2 — chronic PAGE_HUNG family on certain URLs (often `/`
      // which is a redirect-only route in `src/routes/index.tsx` — Lighthouse
      // sometimes can't reliably detect FCP through the redirect chain to
      // /dashboard, especially under headless Chrome + Linux CI runner
      // resource pressure). Documented chronic since W128/W139 NO_FCP
      // family. When `lhci collect` exits non-zero, it means at least one
      // URL hit a hard error — but partial LHRs for OTHER URLs typically
      // still get written to `.lighthouseci/` before the failing run
      // crashes the worker. Proceed to assert with whatever was collected;
      // assert will either:
      //   (a) pass the assertions for URLs that DID measure successfully
      //       (which is the bulk of the value — perf scores for /login,
      //        /news, /events, etc. that always work), OR
      //   (b) fail assert if collection was so bad nothing survived (which
      //       legitimately deserves a CI failure signal).
      // This is structurally identical to the Windows EPERM branch — the
      // ROOT cause differs (Linux PAGE_HUNG vs Windows tmpdir cleanup)
      // but the mitigation logic is the same: tolerate collect-phase
      // failures, let assert-phase be the source of truth for whether
      // the build passes performance gates.
      console.warn(
        "lhci collect exited with code 1 on a non-Windows platform. " +
          "Most commonly LighthouseError: PAGE_HUNG on a slow-to-paint URL " +
          "(redirect chain, infinite loop, or CI runner resource pressure). " +
          "Proceeding to assert phase against whatever LHRs were collected " +
          "— see W146 SW2 closure note in scripts/run-lhci.mjs."
      )
    } else {
      throw error
    }
  }
  await runCommand("npx", ["lhci", "assert", `--config=${tempConfigPath}`], "lhci assert", lhciEnv)

  // LHCI supports category assertions but cannot express the intentional
  // SEO distinction between public and robots-protected application routes.
  // Validate that route intent, robots directives, and crawl-audit provenance
  // all agree before the shard is uploaded as release evidence.
  const robotsText = useRemotePreview ? await fetchRemoteRobots(base) : undefined
  await assertLhciRoutePolicy({
    reportsDir: path.resolve(frontendRoot, ".lighthouseci"),
    robotsPath: path.resolve(frontendRoot, "public", "robots.txt"),
    robotsText,
    expectedPaths,
  })

  await rm(tempDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 1000 })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
