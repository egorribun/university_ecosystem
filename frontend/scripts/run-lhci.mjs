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
  const defaultPaths = ["/", "/login", "/dashboard", "/news", "/schedule", "/events", "/activity", "/map"]
  const overridePaths = process.env.LHCI_URLS?.split(",").map((p) => p.trim()).filter(Boolean)
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
      // (aspirational, never blocked CI) to `error@0.15` (strictly
      // stronger enforcement — this DOES block CI). 0.15 is a RATCHET
      // FLOOR based on the lowest measured median post-Wave-117
      // (authenticated routes /dashboard + /news + /events scored
      // 0.18-0.27, /login 0.56 — floor = 0.18 - 0.05 safety margin,
      // rounded conservatively to 0.15). This is NOT the target — it is
      // the floor we clear with margin. Wave 118 will ratchet higher
      // once CLS content-shift culprits are addressed on authenticated
      // routes. A11y/BP/SEO already production-grade (error@0.95).
      assert: {
        assertions: {
          "categories:performance": ["error", { minScore: 0.15 }],
          "categories:accessibility": ["error", { minScore: 0.95 }],
          "categories:best-practices": ["error", { minScore: 0.95 }],
          "categories:seo": ["error", { minScore: 0.9 }],
          "largest-contentful-paint": ["warn", { maxNumericValue: 2500, aggregationMethod: "median" }],
          "total-blocking-time": ["warn", { maxNumericValue: 200, aggregationMethod: "median" }],
          "cumulative-layout-shift": ["warn", { maxNumericValue: 0.1, aggregationMethod: "median" }],
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
  await runCommand("npx", ["-y", "@lhci/cli@^0.15.1", "collect", `--config=${tempConfigPath}`], "lhci collect", lhciEnv)
  await runCommand("npx", ["-y", "@lhci/cli@^0.15.1", "assert", `--config=${tempConfigPath}`], "lhci assert", lhciEnv)

  await rm(tempDir, { recursive: true, force: true })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
