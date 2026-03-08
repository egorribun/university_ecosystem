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

async function runCommand(command, args, description) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: frontendRoot,
      env: process.env,
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

  const collect = {
    numberOfRuns: 3,
    url: useRemotePreview ? [base, `${base}/login`] : ["/", "/login"],
    chromePath,
    settings: {
      chromeFlags:
        "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --disable-gpu --headless=new",
      throttlingMethod: "devtools",
      emulatedFormFactor: "desktop",
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
      assert: {
        assertions: {
          "categories:performance": ["warn", { minScore: 0.8 }],
          "categories:accessibility": ["error", { minScore: 0.8 }],
          "categories:best-practices": ["error", { minScore: 0.8 }],
          "categories:seo": ["error", { minScore: 0.8 }],
          "total-blocking-time": ["warn", { maxNumericValue: 435, aggregationMethod: "median" }],
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

  await runCommand("lhci", ["collect", `--config=${tempConfigPath}`], "lhci collect")
  await runCommand("lhci", ["assert", `--config=${tempConfigPath}`], "lhci assert")

  await rm(tempDir, { recursive: true, force: true })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
