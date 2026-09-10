import { spawn } from "node:child_process"
import os from "node:os"
import path from "node:path"
import process from "node:process"

import { validateWasmArtifacts } from "./verify-wasm-artifacts.mjs"
import { writeSourceProvenance } from "./wasm-source-provenance.mjs"

function runWasmPack(command, args, { cwd, env = process.env }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env, shell: false, stdio: "inherit" })
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

function canonicalPath(value) {
  const normalized = String(value).replaceAll("\\", "/")
  // Keep portable drive/UNC paths intact when a Windows fixture is evaluated
  // by a POSIX CI runner; resolving them there would prepend the repo cwd.
  if (/^(?:[A-Za-z]:\/|\/\/)/u.test(normalized)) return normalized
  return path.resolve(normalized).replaceAll("\\", "/")
}

/**
 * Return a build environment whose Rust path metadata is stable across hosts.
 *
 * wasm-pack embeds dependency and workspace paths in optimized WASM custom
 * sections.  The checked-in packages use the same canonical roots as the CI
 * producer; injecting these remaps here prevents a local Windows build from
 * rewriting provenance with machine-specific paths.  Caller-provided flags
 * are preserved verbatim and the remaps are added only when absent.
 */
export function canonicalWasmBuildEnvironment(frontendRoot, baseEnvironment = process.env) {
  const environment = { ...baseEnvironment }
  const workspaceRoot = environment.GITHUB_WORKSPACE
    ? canonicalPath(environment.GITHUB_WORKSPACE)
    : canonicalPath(path.dirname(path.resolve(frontendRoot)))
  const cargoRoot = canonicalPath(environment.CARGO_HOME || path.join(os.homedir(), ".cargo"))
  const requiredFlags = [
    `--remap-path-prefix=${cargoRoot}=/usr/local/cargo`,
    `--remap-path-prefix=${workspaceRoot}=/work`,
  ]
  const existingFlags = typeof environment.RUSTFLAGS === "string" ? environment.RUSTFLAGS : ""
  const additions = requiredFlags.filter((flag) => !existingFlags.includes(flag))
  environment.RUSTFLAGS = [existingFlags.trim(), ...additions].filter(Boolean).join(" ")
  return environment
}

export async function buildWasmArtifacts(
  frontendRoot,
  { runCommand = runWasmPack, validateArtifacts = validateWasmArtifacts } = {}
) {
  if (process.env.SKIP_WASM_BUILD === "1") {
    console.log("SKIP_WASM_BUILD=1: skipping wasm-pack build and validating existing artifacts")
    await validateArtifacts(frontendRoot, { requireSourceProvenance: true })
    return
  }

  const buildArgs = (directory) => ["build", directory, "--target", "web", "--release"]
  const buildEnvironment = canonicalWasmBuildEnvironment(frontendRoot)

  try {
    await runCommand("wasm-pack", buildArgs("rust-crypto"), {
      cwd: frontendRoot,
      env: buildEnvironment,
    })
    await runCommand("wasm-pack", buildArgs("wasm-sanitizer"), {
      cwd: frontendRoot,
      env: buildEnvironment,
    })
  } catch (error) {
    // Standard Node build workers may not install the Rust toolchain.  The
    // repository carries generated, integrity-checked packages, so reuse
    // those artifacts only when the executable is genuinely absent.  Any
    // actual wasm-pack build failure remains fatal and cannot silently fall
    // back to stale or partial output.
    if (error?.code !== "ENOENT") throw error
    console.warn("wasm-pack is unavailable; validating the checked-in WASM artifacts")
    await validateArtifacts(frontendRoot, { requireSourceProvenance: true })
    return
  }
  await writeSourceProvenance(frontendRoot)
  await validateArtifacts(frontendRoot, { requireSourceProvenance: true })
}
