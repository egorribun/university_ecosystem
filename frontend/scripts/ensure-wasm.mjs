/**
 * TD-24-04: Pre-install check for wasm-sanitizer built artifacts.
 *
 * package.json declares "wasm-sanitizer": "file:./wasm-sanitizer/pkg", which
 * means npm must reject installation when a real generated package is absent.
 * This script runs as a "preinstall" hook and validates both local packages
 * before npm can accept an unsafe placeholder as a dependency.
 */

import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"

import { validateWasmArtifacts } from "./verify-wasm-artifacts.mjs"

const __dirname = dirname(fileURLToPath(import.meta.url))
const pkgRoot = resolve(__dirname, "..")

try {
  await validateWasmArtifacts(pkgRoot)
} catch (error) {
  console.error(`WASM artifacts are required before npm install: ${error.message}`)
  console.error(
    "Run `wasm-pack build rust-crypto --target web --release` and `wasm-pack build wasm-sanitizer --target web --release` from frontend/."
  )
  process.exitCode = 1
}
