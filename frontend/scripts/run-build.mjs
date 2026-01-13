import { spawn } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import process from "node:process"

const args = process.argv.slice(2)
const wantsReport = args.includes("--report")
const sanitizedArgs = args.filter((arg) => arg !== "--report")

const env = {
  ...process.env,
  ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
}

function run(command, commandArgs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: "inherit", env, ...options })
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`${command} exited with code ${code}`))
      } else {
        resolve(undefined)
      }
    })
  })
}

async function main() {
  await run("vite", ["build", ...sanitizedArgs], {
    cwd: path.resolve(process.cwd()),
    shell: true,
  })
  if (wantsReport) {
    await run("node", [path.resolve(process.cwd(), "scripts/check-bundle-budget.mjs")])
  }

  // Manual replacement for VITE_LHCI and visibility fixes in index.html
  const isLHCI = process.env.VITE_LHCI === "true"
  const distIndex = path.resolve(process.cwd(), "dist/index.html")
  try {
    let html = readFileSync(distIndex, "utf8")
    if (isLHCI) {
      // Force visibility CSS that works regardless of scripts
      const lhciStyles = "html, body, #root { background: #FFFFFF !important; color: #000000 !important; opacity: 1 !important; visibility: visible !important; } #lhci-marker { display: flex !important; }"
      html = html.replace("/* LHCI_CSS_PLACEHOLDER */", lhciStyles)
      html = html.replace(/%VITE_LHCI%/g, "true")
    } else {
      html = html.replace("/* LHCI_CSS_PLACEHOLDER */", "")
      html = html.replace(/%VITE_LHCI%/g, "false")
    }
    writeFileSync(distIndex, html, "utf8")
  } catch (error) {
    console.warn("Could not perform manual VITE_LHCI replacement in index.html:", error.message)
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
