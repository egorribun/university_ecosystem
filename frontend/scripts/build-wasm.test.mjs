import assert from "node:assert/strict"
import test from "node:test"

import { buildWasmArtifacts } from "./build-wasm.mjs"

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
