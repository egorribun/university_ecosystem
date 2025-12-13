import { spawn } from "node:child_process"
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
  await run("vite", ["build", ...sanitizedArgs], { cwd: path.resolve(process.cwd()) })
  if (wantsReport) {
    await run("node", [path.resolve(process.cwd(), "scripts/check-bundle-budget.mjs")])
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
