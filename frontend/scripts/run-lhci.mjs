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

const LOCAL_PREVIEW_PORT = 4174
process.env.VITE_LHCI = "true"

const base = process.env.PREVIEW_URL ?? process.env.LHCI_URL ?? ""
const useRemotePreview = Boolean(base)
let dependenciesEnsured = false

async function ensureSystemDependencies() {
  if (dependenciesEnsured) {
    return
  }

  await runCommand(
    "npx",
    ["playwright", "install-deps", "chromium"],
    "playwright install-deps chromium"
  )
  dependenciesEnsured = true
}

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
  const chromePath = process.env.LHCI_CHROME_PATH ?? chromium.executablePath()

  await ensureSystemDependencies()

  try {
    await access(chromePath)
    return chromePath
  } catch (error) {
    if (error && error.code !== "ENOENT") {
      throw error
    }
  }

  await runCommand("npx", ["playwright", "install", "chromium"], "playwright install chromium")

  await access(chromePath)
  return chromePath
}

async function createConfig() {
  const chromePath = await ensureChromiumExecutable()
  process.env.CHROME_PATH = chromePath

  const collect = {
    numberOfRuns: 1,
    url: useRemotePreview ? [base, `${base}/login`] : ["/", "/login"],
    chromePath,
    settings: {
      chromeFlags:
        "--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type " +
        "--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:4174",
      throttlingMethod: "devtools",
      emulatedFormFactor: "desktop",
    },
    budgetsPath: path.resolve(frontendRoot, "../../budget.json"),
  }

  if (!useRemotePreview) {
    collect.beforeAllScript = "npm run build && node scripts/prepare-lhci-routes.mjs"
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

  await writeFile(tempConfigPath, JSON.stringify(config), "utf8")

  await runCommand("lhci", ["collect", `--config=${tempConfigPath}`], "lhci collect")
  await runCommand("lhci", ["assert", `--config=${tempConfigPath}`], "lhci assert")

  await rm(tempDir, { recursive: true, force: true })
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
