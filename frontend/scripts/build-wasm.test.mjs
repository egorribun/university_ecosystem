import assert from "node:assert/strict"
import test from "node:test"

import { buildWasmArtifacts, canonicalWasmBuildEnvironment } from "./build-wasm.mjs"

test("propagates the first wasm-pack failure instead of accepting a fallback", async () => {
  const calls = []
  const runCommand = async (command, args) => {
    calls.push([command, args])
    throw new Error("wasm-pack is unavailable")
  }

  await assert.rejects(
    () => buildWasmArtifacts("C:/frontend", { runCommand }),
    /wasm-pack is unavailable/
  )
  assert.deepEqual(calls, [["wasm-pack", ["build", "rust-crypto", "--target", "web", "--release"]]])
})

test("reuses validated checked-in artifacts when wasm-pack is missing", async () => {
  const calls = []
  let validatedRoot
  const missingWasmPack = Object.assign(new Error("spawn wasm-pack ENOENT"), { code: "ENOENT" })

  await buildWasmArtifacts("C:/frontend", {
    runCommand: async (command, args) => {
      calls.push([command, args])
      throw missingWasmPack
    },
    validateArtifacts: async (root) => {
      validatedRoot = root
    },
  })

  assert.deepEqual(calls, [["wasm-pack", ["build", "rust-crypto", "--target", "web", "--release"]]])
  assert.equal(validatedRoot, "C:/frontend")
})

test("runs both builds before validating generated artifacts", async () => {
  const calls = []
  const runCommand = async (command, args) => {
    calls.push([command, args])
  }

  await assert.rejects(() => buildWasmArtifacts("C:/missing-frontend", { runCommand }), /ENOENT/)
  assert.deepEqual(calls, [
    ["wasm-pack", ["build", "rust-crypto", "--target", "web", "--release"]],
    ["wasm-pack", ["build", "wasm-sanitizer", "--target", "web", "--release"]],
  ])
})

test("passes canonical source-path remapping to every wasm-pack build", async () => {
  const calls = []

  await buildWasmArtifacts(process.cwd(), {
    runCommand: async (command, args, options) => {
      calls.push({ command, args, options })
    },
    validateArtifacts: async () => {},
  })

  assert.equal(calls.length, 2)
  for (const { command, options } of calls) {
    assert.equal(command, "wasm-pack")
    assert.match(options.env.RUSTFLAGS, /--remap-path-prefix=.*=\/usr\/local\/cargo/u)
    assert.match(options.env.RUSTFLAGS, /--remap-path-prefix=.*=\/work/u)
  }
})

test("preserves caller Rust flags without mutating the base environment", () => {
  const baseEnvironment = {
    CARGO_HOME: "C:/cargo",
    GITHUB_WORKSPACE: "C:/workspace",
    RUSTFLAGS: "--cfg=feature_a",
  }

  const environment = canonicalWasmBuildEnvironment("C:/workspace/frontend", baseEnvironment)

  assert.equal(baseEnvironment.RUSTFLAGS, "--cfg=feature_a")
  assert.match(environment.RUSTFLAGS, /^--cfg=feature_a /u)
  assert.match(environment.RUSTFLAGS, /--remap-path-prefix=C:\/cargo=\/usr\/local\/cargo/u)
  assert.match(environment.RUSTFLAGS, /--remap-path-prefix=C:\/workspace=\/work/u)
})
