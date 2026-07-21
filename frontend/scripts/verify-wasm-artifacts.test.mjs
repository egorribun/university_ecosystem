import assert from "node:assert/strict"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

import { validateWasmArtifacts } from "./verify-wasm-artifacts.mjs"

const validWasm = Buffer.from([
  0x00,
  0x61,
  0x73,
  0x6d,
  0x01,
  0x00,
  0x00,
  0x00,
  ...Array.from({ length: 9 }, () => [0x00, 0x01, 0x00]).flat(),
])

const packageFixtures = {
  "wasm-sanitizer": {
    filename: "wasm_sanitizer",
    source: `async function init() { return undefined }
export { init as default }
export function initSync() {}
export function sanitize_rich_text() { return "clean" }
export function sanitize_html_basic() { return "clean" }
export function strip_html() { return "clean" }
export function sanitize_rich_text_raw() { return "clean" }
`,
  },
  "rust-crypto": {
    packageName: "uni-wasm-crypto",
    filename: "uni_wasm_crypto",
    source: `async function init() { return undefined }
export { init as default }
export function pbkdf2_derive() { return "derived" }
export function scrypt_derive() { return Uint8Array.of(1) }
export function hmac_sha256_sign() { return "signature" }
`,
  },
}

async function writePackage(root, name, overrides = {}) {
  const fixture = packageFixtures[name]
  const packageDir = path.join(root, name, "pkg")
  await mkdir(packageDir, { recursive: true })
  await writeFile(
    path.join(packageDir, "package.json"),
    JSON.stringify({
      name: fixture.packageName ?? name,
      version: "0.1.0",
      type: "module",
      main: `${fixture.filename}.js`,
      ...overrides.metadata,
    })
  )
  await writeFile(
    path.join(packageDir, `${fixture.filename}.js`),
    overrides.source ?? fixture.source
  )
  await writeFile(path.join(packageDir, `${fixture.filename}_bg.wasm`), overrides.wasm ?? validWasm)
}

async function withFixture(callback) {
  const root = await mkdtemp(path.join(os.tmpdir(), "wasm-artifact-validator-"))
  try {
    await writePackage(root, "wasm-sanitizer")
    await writePackage(root, "rust-crypto")
    await callback(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("accepts packages containing valid WebAssembly and the required generated exports", async () => {
  await withFixture(async (root) => {
    await assert.doesNotReject(() => validateWasmArtifacts(root))
  })
})

test("rejects text masquerading as a WebAssembly module", async () => {
  await withFixture(async (root) => {
    await writePackage(root, "wasm-sanitizer", { wasm: Buffer.from("mock_wasm_data\n") })
    await assert.rejects(
      () => validateWasmArtifacts(root),
      /wasm-sanitizer.*valid WebAssembly module/i
    )
  })
})

test("rejects package glue that omits a required sanitizer export", async () => {
  await withFixture(async (root) => {
    await writePackage(root, "wasm-sanitizer", {
      source:
        "export default async function init() { return undefined }\nexport function initSync() {}\n",
    })
    await assert.rejects(() => validateWasmArtifacts(root), /sanitize_rich_text/)
  })
})

test("requires the ESM package metadata produced by wasm-pack web builds", async () => {
  await withFixture(async (root) => {
    await writePackage(root, "wasm-sanitizer", { metadata: { type: "commonjs" } })
    await assert.rejects(() => validateWasmArtifacts(root), /type.*module/i)
  })
})

test("rejects the known sanitizer pass-through placeholder", async () => {
  await withFixture(async (root) => {
    await writePackage(root, "wasm-sanitizer", {
      source: `export default async function init() {}
export function initSync() {}
export function sanitize_rich_text(dirty) { return dirty; }
export function sanitize_html_basic(dirty) { return dirty; }
export function strip_html(dirty) { return dirty; }
export function sanitize_rich_text_raw() { return ""; }
`,
    })
    await assert.rejects(() => validateWasmArtifacts(root), /pass-through placeholder/i)
  })
})

test("can execute as a command-line module", () => {
  assert.equal(path.basename(fileURLToPath(import.meta.url)), "verify-wasm-artifacts.test.mjs")
})

test("exposes artifact validation through the frontend package scripts", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8")
  )
  assert.equal(
    packageJson.scripts["test:wasm-artifacts"],
    "node --test scripts/verify-wasm-artifacts.test.mjs"
  )
})
