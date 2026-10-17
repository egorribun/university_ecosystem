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

import { buildSafeCommandInvocation } from "./lhci-command.mjs"
import routePolicyConfig from "./lhci-route-policy-config.cjs"
import { assertLhciRoutePolicy, normalizeLhciPath } from "./lhci-route-policy.mjs"
import {
  pathForLhciPreview,
  previewReadyPattern,
  previewServerCommand,
  resolveLhciPreviewMode,
} from "./lhci-preview-mode.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")

process.env.VITE_LHCI = "true"

const previewMode = resolveLhciPreviewMode(process.env)
const base = previewMode.base
const useRemotePreview = previewMode.kind === "remote"
const useSsrPreview = previewMode.kind === "ssr"
let dependenciesEnsured = false

async function runCommand(command, args, description, extraEnv = {}) {
  const { executable, args: spawnArgs } = buildSafeCommandInvocation(command, args)

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
    throw new Error(`Unable to fetch preview robots.txt ${robotsUrl}: ${error.message}`, {
      cause: error,
    })
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
  const previewPaths = targetPaths.map((pathname) => pathForLhciPreview(pathname, previewMode))
  const collect = {
    numberOfRuns: 3,
    url:
      useRemotePreview || useSsrPreview
        ? previewPaths.map((p) => `${base}${p === "/" ? "" : p}`)
        : targetPaths,
    chromePath,
    settings: {
      // Linux Lighthouse 13.1.0/headless Chrome has returned a null composite
      // Performance score when screenshot audits cannot collect frames, while
      // trace-based CLS/LCP/TBT remain available. Track upstream context at
      // https://github.com/GoogleChrome/lighthouse/issues/17021 and verify the
      // current toolchain before changing assertions or runner configuration.
      // Keep current quality thresholds below; historical measurement runs are
      // not evidence for a different release gate.
      //
      // On Windows, use `lhci:windows` for local measurement: it writes reports
      // before Chrome's temporary-profile cleanup can fail. Record the platform
      // and run configuration with performance evidence.
      chromeFlags:
        "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --headless=new",
      throttlingMethod: "devtools",
      // Lighthouse normally aborts on non-2xx navigations.  The route matrix
      // deliberately includes the production 404 document, whose HTTP 404
      // status is part of the public contract.  Keep the status semantics in
      // the server and ask Lighthouse to continue collecting the document so
      // the same accessibility/SEO/performance gates apply to it.
      ignoreStatusCode: true,
      emulatedFormFactor: "mobile",
      budgetPath: path.resolve(frontendRoot, "../budget.json"),
      maxWaitForFcp: 45000,
      maxWaitForLoad: 60000,
    },
  }

  if (!useRemotePreview && !useSsrPreview) {
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
    collect.startServerCommand = previewServerCommand(previewMode)
    collect.startServerReadyPattern = previewReadyPattern(previewMode)
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
                // Keep the accepted CLS ceiling at 0.05; do not relax it based
                // on historical per-run measurements.
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

  // Build and prepare dist for LHCI mode if using the static fallback. The
  // managed SSR preview serves route-specific HTML directly from the same
  // immutable build, so copying a route-agnostic SPA shell would reintroduce
  // the createRoot() cold-start penalty this mode is designed to measure.
  const runPreviewMode = resolveLhciPreviewMode(process.env)
  const useRemotePreview = runPreviewMode.kind === "remote"
  const useSsrPreview = runPreviewMode.kind === "ssr"
  if (!useRemotePreview && !useSsrPreview) {
    if (!process.env.SKIP_BUILD) {
      console.log("Building for LHCI...")
      await runCommand("npm", ["run", "build"], "npm run build")
    } else {
      console.log("SKIP_BUILD is set, reusing the downloaded production bundle.")
    }
    console.log("Preparing LHCI routes...")
    await runCommand("node", ["scripts/prepare-lhci-routes.mjs"], "prepare-lhci-routes")
  }

  // Never merge reports from a previous local invocation. CI starts with a
  // clean workspace, but explicit cleanup keeps local reruns equally
  // fail-closed and makes the report set SHA/attempt scoped by construction.
  await rm(path.resolve(frontendRoot, ".lighthouseci"), {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 1000,
  })
  await writeFile(tempConfigPath, JSON.stringify(config), "utf8")

  // Wave 116 SW3 — invoke @lhci/cli through the package manager so the script
  // works without a global `lhci` install. POSIX uses npx's local resolution;
  // Windows uses the shell-free npm exec form selected above. `--yes`
  // auto-accepts the download prompt on the Windows path.
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
  const lhciCommand = process.platform === "win32" ? "npm" : "npx"
  const lhciPrefix = process.platform === "win32" ? ["exec", "--yes", "lhci", "--"] : ["lhci"]
  try {
    await runCommand(
      lhciCommand,
      [...lhciPrefix, "collect", `--config=${tempConfigPath}`],
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
  await runCommand(
    lhciCommand,
    [...lhciPrefix, "assert", `--config=${tempConfigPath}`],
    "lhci assert",
    lhciEnv
  )

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
    expectedRuns: config.ci.collect.numberOfRuns,
  })

  await rm(tempDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 1000 })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
