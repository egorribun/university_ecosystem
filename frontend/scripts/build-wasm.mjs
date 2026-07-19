import { spawn } from "node:child_process"

import { validateWasmArtifacts } from "./verify-wasm-artifacts.mjs"

function runWasmPack(command, args, { cwd }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, shell: false, stdio: "inherit" })
    let settled = false
    const finish = (callback, value) => {
      if (!settled) {
        settled = true
        callback(value)
      }
    }

    child.once("error", (error) => finish(reject, error))
    child.once("close", (code) => {
      if (code === 0) {
        finish(resolve)
      } else {
        finish(reject, new Error(`${command} exited with code ${code}`))
      }
    })
  })
}

export async function buildWasmArtifacts(frontendRoot, { runCommand = runWasmPack } = {}) {
  const buildArgs = (directory) => ["build", directory, "--target", "web", "--release"]

  await runCommand("wasm-pack", buildArgs("rust-crypto"), { cwd: frontendRoot })
  await runCommand("wasm-pack", buildArgs("wasm-sanitizer"), { cwd: frontendRoot })
  await validateWasmArtifacts(frontendRoot)
}
