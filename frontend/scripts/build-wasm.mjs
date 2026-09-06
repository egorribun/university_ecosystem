import { spawn } from "node:child_process"
import process from "node:process"

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

export async function buildWasmArtifacts(
  frontendRoot,
  { runCommand = runWasmPack, validateArtifacts = validateWasmArtifacts } = {}
) {
  if (process.env.SKIP_WASM_BUILD === "1") {
    console.log("SKIP_WASM_BUILD=1: skipping wasm-pack build and validating existing artifacts")
    await validateArtifacts(frontendRoot)
    return
  }

  const buildArgs = (directory) => ["build", directory, "--target", "web", "--release"]

  try {
    await runCommand("wasm-pack", buildArgs("rust-crypto"), { cwd: frontendRoot })
    await runCommand("wasm-pack", buildArgs("wasm-sanitizer"), { cwd: frontendRoot })
  } catch (error) {
    // Standard Node build workers may not install the Rust toolchain.  The
    // repository carries generated, integrity-checked packages, so reuse
    // those artifacts only when the executable is genuinely absent.  Any
    // actual wasm-pack build failure remains fatal and cannot silently fall
    // back to stale or partial output.
    if (error?.code !== "ENOENT") throw error
    console.warn("wasm-pack is unavailable; validating the checked-in WASM artifacts")
    await validateArtifacts(frontendRoot)
    return
  }
  await validateArtifacts(frontendRoot)
}
