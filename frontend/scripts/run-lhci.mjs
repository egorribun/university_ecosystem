import { access, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { spawn } from "node:child_process"

import { chromium } from "playwright"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")

process.env.VITE_LHCI = "true"

const base = process.env.PREVIEW_URL ?? process.env.LHCI_URL ?? ""
const useRemotePreview = Boolean(base)
let dependenciesEnsured = false

async function runCommand(command, args, description, extraEnv = {}) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: frontendRoot,
      env: { ...process.env, ...extraEnv },
      stdio: "inherit",
      shell: true,
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
  if (dependenciesEnsured) {
    return
  }

  await runCommand(
    "npm",
    ["exec", "playwright", "install-deps", "chromium"],
    "playwright install-deps chromium"
  )
  dependenciesEnsured = true
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
  const defaultPaths = [
    "/",
    "/login",
    "/dashboard",
    "/news",
    "/schedule",
    "/events",
    "/activity",
    "/map",
    "/404",
  ]
  // Wave 119 SW2 — empty string trims to "/" so callers can measure root via
  // LHCI_URLS=,schedule,404 (Windows MSYS_NO_PATHCONV bypass: leading slashes
  // in /-paths are mangled to git-bash absolute paths). Without this map,
  // .filter(Boolean) drops "" and root never gets measured.
  const overridePaths = process.env.LHCI_URLS?.split(",")
    .map((p) => p.trim() || "/")
    .filter(Boolean)
  const targetPaths = overridePaths?.length ? overridePaths : defaultPaths
  const collect = {
    numberOfRuns: 3,
    url: useRemotePreview ? targetPaths.map((p) => `${base}${p === "/" ? "" : p}`) : targetPaths,
    chromePath,
    settings: {
      chromeFlags:
        "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --disable-gpu --headless=new",
      throttlingMethod: "devtools",
      emulatedFormFactor: "mobile",
      maxWaitForFcp: 45000,
      maxWaitForLoad: 60000,
    },
    budgetsPath: path.resolve(frontendRoot, "../../budget.json"),
  }

  if (!useRemotePreview) {
    collect.staticDistDir = path.resolve(frontendRoot, "dist")
    collect.isSinglePageApplication = true
  } else {
    collect.startServerCommand = "node scripts/lhci-preview.mjs"
    collect.startServerReadyPattern = "LHCI_READY"
    collect.startServerReadyTimeout = 120000
  }

  return {
    ci: {
      collect,
      // Wave 112 — thresholds per production-grade April 2026 brief.
      // Wave 117 SW8 — flipped `categories:performance` from `warn@0.9`
      // → `error@0.15` (ratchet floor based on Wave-117 measured medians
      // 0.18-0.56). Wave 118 SW5 — ratcheted again to `error@0.30` after
      // SW1-SW4 dropped CLS 86%+ on authenticated routes by addressing
      // four content-shift culprits (footer anchor, InstallPrompt
      // bottom-anchored variable height, EventsBackdrop %-based sizing,
      // Dashboard hero + dash-tilt-card growing-content). Wave 119 SW3 —
      // ratcheted Perf 0.30 → 0.40 + flipped CLS warn@0.1 → error@0.15.
      // Wave 119 SW2 3-run medians (mobile, devtools throttling):
      //   / 0.45/CLS 0.061 | /login 0.57/0.022 | /dashboard 0.46/0.061 |
      //   /news 0.53/0.006 | /schedule 0.52/0.003 | /events 0.48/0.062 |
      //   /404 0.54/0.000.
      // Perf floor = min(0.45) − 0.05 safety = 0.40 (matches plan
      // decision tree "Any Perf < 0.50 → floor = min − 0.05").
      // CLS floor = 0.15 because worst 3-run CLS = 0.062 (/events) +
      // typical 0.04 variance lands at 0.10 = right at boundary —
      // error@0.15 has 8pt margin while still being strictly stronger
      // than warn@0.1 (warn never blocked CI). Wave 120+ should aim
      // for error@0.1 once /events + /dashboard residual shifts close.
      // A11y/BP/SEO already production-grade (error@0.95).
      assert: {
        assertions: {
          "categories:performance": ["error", { minScore: 0.4 }],
          "categories:accessibility": ["error", { minScore: 0.95 }],
          "categories:best-practices": ["error", { minScore: 0.95 }],
          "categories:seo": ["error", { minScore: 0.9 }],
          "largest-contentful-paint": [
            "warn",
            { maxNumericValue: 2500, aggregationMethod: "median" },
          ],
          "total-blocking-time": ["warn", { maxNumericValue: 200, aggregationMethod: "median" }],
          "cumulative-layout-shift": [
            "error",
            { maxNumericValue: 0.15, aggregationMethod: "median" },
          ],
        },
      },
    },
  }
}

async function run() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "lhci-config-"))
  const tempConfigPath = path.join(tempDir, "lighthouserc.json")

  const config = await createConfig()

  // Build and prepare dist for LHCI mode if not using remote preview
  const useRemotePreview = Boolean(process.env.PREVIEW_URL ?? process.env.LHCI_URL ?? "")
  if (!useRemotePreview) {
    if (!process.env.SKIP_BUILD) {
      console.log("Building for LHCI...")
      await runCommand("npm", ["run", "build"], "npm run build")
    } else {
      console.log("SKIP_BUILD is set, skipping npm run build.")
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
  // MSYS_NO_PATHCONV=1 prevents Git Bash on Windows from mangling URL-style
  // paths like `/news` into `c:/Program Files/Git/news` when LHCI forwards
  // them to the Lighthouse CLI subprocess (shell: true is required for
  // `npx` resolution on Windows).
  const lhciEnv = { MSYS_NO_PATHCONV: "1" }
  try {
    await runCommand(
      "npx",
      ["-y", "@lhci/cli@^0.15.1", "collect", `--config=${tempConfigPath}`],
      "lhci collect",
      lhciEnv
    )
  } catch (error) {
    if (process.platform === "win32" && error.message.includes("code 1")) {
      console.warn(
        "lhci collect exited with code 1. This is often caused by an EPERM error when chrome-launcher attempts to clean up its temp profile on Windows. Proceeding to assert phase..."
      )
    } else {
      throw error
    }
  }
  await runCommand(
    "npx",
    ["-y", "@lhci/cli@^0.15.1", "assert", `--config=${tempConfigPath}`],
    "lhci assert",
    lhciEnv
  )

  await rm(tempDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 1000 })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
