/**
 * TD-24-04: Pre-install check for wasm-sanitizer built artifacts.
 *
 * package.json declares "wasm-sanitizer": "file:./wasm-sanitizer/pkg", which
 * means npm will fail at install time if that directory (or its package.json)
 * does not exist.  This script runs as a "preinstall" hook to surface a clear
 * warning before the cryptic npm error.
 *
 * Exit code is always 0 so that CI environments without a Rust toolchain can
 * still proceed (the full build script in run-build.mjs handles the wasm-pack
 * step separately).
 */

import { existsSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const pkgRoot = resolve(__dirname, "..")
const wasmPkgJson = resolve(pkgRoot, "wasm-sanitizer", "pkg", "package.json")

if (!existsSync(wasmPkgJson)) {
  console.warn(
    "\n" +
      "-------------------------------------------------------------\n" +
      " WARNING (TD-24-04): wasm-sanitizer/pkg/package.json missing.\n" +
      "\n" +
      ' The frontend depends on "wasm-sanitizer" as a local file\n' +
      " dependency (file:./wasm-sanitizer/pkg).  npm install will\n" +
      " fail unless the WASM package has been built first.\n" +
      "\n" +
      " To fix, run from the frontend directory:\n" +
      "\n" +
      "   wasm-pack build wasm-sanitizer --target web\n" +
      "\n" +
      " If you do not have wasm-pack / Rust installed, see:\n" +
      "   https://rustwasm.github.io/wasm-pack/installer/\n" +
      "-------------------------------------------------------------\n"
  )
}

process.exit(0)
