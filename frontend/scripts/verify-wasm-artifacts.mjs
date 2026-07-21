import { readFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const WASM_MAGIC = Buffer.from([0x00, 0x61, 0x73, 0x6d])
const MINIMUM_WASM_BYTES = 32

const ARTIFACTS = [
  {
    directory: "wasm-sanitizer/pkg",
    packageName: "wasm-sanitizer",
    jsFile: "wasm_sanitizer.js",
    wasmFile: "wasm_sanitizer_bg.wasm",
    exports: [
      "default",
      "initSync",
      "sanitize_rich_text",
      "sanitize_html_basic",
      "strip_html",
      "sanitize_rich_text_raw",
    ],
    placeholderPatterns: [
      {
        pattern: /function\s+sanitize_rich_text\s*\([^)]*\)\s*\{\s*return\s+\w+\s*;\s*\}/,
        description: "pass-through placeholder",
      },
    ],
  },
  {
    directory: "rust-crypto/pkg",
    packageName: "uni-wasm-crypto",
    jsFile: "uni_wasm_crypto.js",
    wasmFile: "uni_wasm_crypto_bg.wasm",
    exports: ["default", "pbkdf2_derive", "scrypt_derive", "hmac_sha256_sign"],
    placeholderPatterns: [
      {
        pattern: /function\s+pbkdf2_derive\s*\([^)]*\)\s*\{\s*return\s+["']{2}\s*;\s*\}/,
        description: "empty cryptographic output placeholder",
      },
      {
        pattern:
          /function\s+scrypt_derive\s*\([^)]*\)\s*\{\s*return\s+new\s+Uint8Array\(\)\s*;\s*\}/,
        description: "empty cryptographic output placeholder",
      },
    ],
  },
]

function hasNamedExport(source, name) {
  return new RegExp(
    `export\\s+(?:async\\s+)?function\\s+${name}\\b|export\\s*\\{[^}]*\\b${name}\\b`
  ).test(source)
}

function assertValidWasm(bytes, label) {
  const hasMagic = bytes.subarray(0, WASM_MAGIC.length).equals(WASM_MAGIC)
  if (bytes.length <= MINIMUM_WASM_BYTES || !hasMagic || !WebAssembly.validate(bytes)) {
    throw new Error(`${label} is not a valid WebAssembly module`)
  }
}

function assertGeneratedExports(source, artifact) {
  for (const exportName of artifact.exports) {
    const exists =
      exportName === "default"
        ? /export\s+default\b|export\s*\{[^}]*\bdefault\b/.test(source)
        : hasNamedExport(source, exportName)
    if (!exists) {
      throw new Error(
        `${artifact.packageName} generated glue is missing required export: ${exportName}`
      )
    }
  }

  for (const { pattern, description } of artifact.placeholderPatterns) {
    if (pattern.test(source)) {
      throw new Error(`${artifact.packageName} generated glue contains a ${description}`)
    }
  }
}

async function readPackageArtifact(root, artifact) {
  const directory = path.join(root, artifact.directory)
  const [packageJson, source, wasm] = await Promise.all([
    readFile(path.join(directory, "package.json"), "utf8"),
    readFile(path.join(directory, artifact.jsFile), "utf8"),
    readFile(path.join(directory, artifact.wasmFile)),
  ])
  const metadata = JSON.parse(packageJson)

  if (metadata.name !== artifact.packageName || metadata.main !== artifact.jsFile) {
    throw new Error(`${artifact.packageName} package metadata does not describe ${artifact.jsFile}`)
  }
  if (metadata.type !== "module") {
    throw new Error(`${artifact.packageName} package metadata must declare type: module`)
  }

  assertValidWasm(wasm, artifact.packageName)
  assertGeneratedExports(source, artifact)
}

export async function validateWasmArtifacts(root) {
  await Promise.all(ARTIFACTS.map((artifact) => readPackageArtifact(root, artifact)))
}

const currentFile = fileURLToPath(import.meta.url)
const invokedFile = process.argv[1] ? path.resolve(process.argv[1]) : ""

if (currentFile === invokedFile) {
  const frontendRoot = path.dirname(path.dirname(currentFile))
  validateWasmArtifacts(frontendRoot)
    .then(() => {
      console.log("WASM artifacts are valid.")
    })
    .catch((error) => {
      console.error(`WASM artifact validation failed: ${error.message}`)
      process.exitCode = 1
    })
}
