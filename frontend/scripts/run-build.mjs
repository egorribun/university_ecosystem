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

  // Manual replacement for VITE_LHCI in index.html to ensure visibility fixes work as expected
  const lhciValue = process.env.VITE_LHCI === "true" ? "true" : "false"
  const distIndex = path.resolve(process.cwd(), "dist/index.html")
  try {
    let html = readFileSync(distIndex, "utf8")
    if (html.includes("%VITE_LHCI%")) {
      html = html.replace(/%VITE_LHCI%/g, lhciValue)
      writeFileSync(distIndex, html, "utf8")
    }
  } catch (error) {
    console.warn("Could not perform manual VITE_LHCI replacement in index.html:", error.message)
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
