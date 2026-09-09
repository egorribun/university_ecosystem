/**
 * Source-bound integrity metadata for the checked-in WebAssembly packages.
 *
 * The generated glue and binary are build products, so a normal Git diff cannot
 * prove that they were produced from the source currently being tested.  This
 * module records a deterministic hash of every build input and every package
 * file.  Consumers validate the record before falling back to checked-in
 * packages; a source edit or a tampered binary therefore fails closed.
 */

import { createHash } from "node:crypto"
import { access, lstat, readFile, readdir, stat, writeFile } from "node:fs/promises"
import path from "node:path"

export const PROVENANCE_FILENAME = "WASM_SOURCE_PROVENANCE.json"

const DEFAULT_SOURCE_FILES = [
  "rust-crypto/Cargo.toml",
  "rust-crypto/Cargo.lock",
  "rust-crypto/src/lib.rs",
  "wasm-sanitizer/Cargo.toml",
  "wasm-sanitizer/Cargo.lock",
  "wasm-sanitizer/src/lib.rs",
]

const PACKAGE_ROOTS = ["rust-crypto/pkg", "wasm-sanitizer/pkg"]

// wasm-pack emits these local-only files next to the public package assets.
// They are ignored by each package's .gitignore and absent from a clean
// checkout, so do not bind checkout validity to optional local build output.
const OPTIONAL_WASM_BINDGEN_DECLARATION = /\.wasm\.d\.ts$/
const OPTIONAL_WASM_PACKAGE_METADATA = ".gitignore"

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex")
}

// Locale-aware comparison is not reproducible across Windows and Linux
// runners (and can reorder JSON object keys).  Provenance bytes are an
// integrity contract, so sort paths by their stable UTF-16 code-unit order.
function compareCanonicalPaths(left, right) {
  if (left === right) return 0
  return left < right ? -1 : 1
}

function canonicalJson(value) {
  return JSON.stringify(value)
}

function safeRelativePath(root, relativePath, label) {
  if (typeof relativePath !== "string" || relativePath.length === 0) {
    throw new Error(`${label} must be a non-empty relative path`)
  }
  const normalized = relativePath.replaceAll("\\", "/")
  if (normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)) {
    throw new Error(`${label} must stay within the checkout: ${relativePath}`)
  }
  const absolute = path.resolve(root, normalized)
  const rootAbsolute = path.resolve(root)
  if (absolute !== rootAbsolute && !absolute.startsWith(`${rootAbsolute}${path.sep}`)) {
    throw new Error(`${label} escapes the checkout: ${relativePath}`)
  }
  return { absolute, relative: normalized }
}

async function fileRecord(root, relativePath, label) {
  const { absolute, relative } = safeRelativePath(root, relativePath, label)
  const linkInfo = await lstat(absolute)
  if (linkInfo.isSymbolicLink()) throw new Error(`${label} must not be a symlink: ${relative}`)
  const info = await stat(absolute)
  if (!info.isFile()) throw new Error(`${label} is not a regular file: ${relative}`)
  const bytes = await readFile(absolute)
  return { path: relative, size: bytes.length, sha256: sha256(bytes) }
}

async function packageRecords(root, packageRoot) {
  const { absolute, relative } = safeRelativePath(root, packageRoot, "WASM package root")
  const info = await stat(absolute).catch(() => null)
  if (!info?.isDirectory()) throw new Error(`WASM package root is missing: ${relative}`)

  const records = []
  async function visit(directory, prefix) {
    const entries = await readdir(directory, { withFileTypes: true })
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      if (
        entry.name === OPTIONAL_WASM_PACKAGE_METADATA ||
        OPTIONAL_WASM_BINDGEN_DECLARATION.test(entry.name)
      ) {
        continue
      }
      const entryRelative = `${prefix}/${entry.name}`
      const entryPath = path.join(directory, entry.name)
      if (entry.isSymbolicLink()) throw new Error(`symlink in WASM package: ${entryRelative}`)
      if (entry.isDirectory()) {
        await visit(entryPath, entryRelative)
      } else if (entry.isFile()) {
        records.push(await fileRecord(root, entryRelative, "WASM package file"))
      } else {
        throw new Error(`unsupported WASM package entry: ${entryRelative}`)
      }
    }
  }
  await visit(absolute, relative)
  if (records.length === 0) throw new Error(`WASM package is empty: ${relative}`)
  return records
}

/** Build deterministic metadata for the current source and generated packages. */
export async function buildSourceProvenance(root, { sourceFiles = DEFAULT_SOURCE_FILES } = {}) {
  const rootAbsolute = path.resolve(root)
  const sourceRecords = []
  const seen = new Set()
  for (const sourceFile of sourceFiles) {
    const record = await fileRecord(rootAbsolute, sourceFile, "WASM source file")
    if (seen.has(record.path)) throw new Error(`duplicate WASM source file: ${record.path}`)
    seen.add(record.path)
    sourceRecords.push(record)
  }
  sourceRecords.sort((left, right) => compareCanonicalPaths(left.path, right.path))

  const packageRecordList = []
  for (const packageRoot of PACKAGE_ROOTS) {
    packageRecordList.push(...(await packageRecords(rootAbsolute, packageRoot)))
  }
  packageRecordList.sort((left, right) => compareCanonicalPaths(left.path, right.path))
  const sourceTreeSha256 = sha256(canonicalJson(sourceRecords))

  return {
    schema_version: 1,
    source_files: sourceRecords,
    source_tree_sha256: sourceTreeSha256,
    packages: Object.fromEntries(
      packageRecordList.map(({ path: relative, size, sha256: digest }) => [
        relative,
        { size, sha256: digest },
      ])
    ),
  }
}

export async function writeSourceProvenance(root, options = {}) {
  const metadata = await buildSourceProvenance(root, options)
  await writeFile(
    path.join(path.resolve(root), PROVENANCE_FILENAME),
    `${JSON.stringify(metadata, null, 2)}\n`,
    "utf8"
  )
  return metadata
}

function assertMetadataShape(metadata) {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    throw new Error(`${PROVENANCE_FILENAME} must contain a JSON object`)
  }
  const expectedKeys = ["packages", "schema_version", "source_files", "source_tree_sha256"]
  const actualKeys = Object.keys(metadata).sort(compareCanonicalPaths)
  if (canonicalJson(actualKeys) !== canonicalJson(expectedKeys)) {
    throw new Error(`${PROVENANCE_FILENAME} has an unexpected provenance metadata field`)
  }
  if (metadata.schema_version !== 1) {
    throw new Error(`${PROVENANCE_FILENAME} has an unsupported schema version`)
  }
  if (!Array.isArray(metadata.source_files) || !metadata.source_tree_sha256) {
    throw new Error(`${PROVENANCE_FILENAME} is missing the source inventory`)
  }
  if (!metadata.packages || typeof metadata.packages !== "object") {
    throw new Error(`${PROVENANCE_FILENAME} is missing the generated package inventory`)
  }
}

/** Validate metadata and all source/package bytes; throws on any mismatch. */
export async function validateSourceProvenance(root, options = {}) {
  const rootAbsolute = path.resolve(root)
  const metadataPath = path.join(rootAbsolute, PROVENANCE_FILENAME)
  await access(metadataPath).catch(() => {
    throw new Error(`${PROVENANCE_FILENAME} is missing`)
  })
  let metadata
  try {
    metadata = JSON.parse(await readFile(metadataPath, "utf8"))
  } catch (error) {
    throw new Error(`${PROVENANCE_FILENAME} is not valid JSON: ${error.message}`)
  }
  assertMetadataShape(metadata)

  const expected = await buildSourceProvenance(rootAbsolute, options)
  if (
    metadata.source_tree_sha256 !== expected.source_tree_sha256 ||
    canonicalJson(metadata.source_files) !== canonicalJson(expected.source_files)
  ) {
    throw new Error(`${PROVENANCE_FILENAME} source inventory drift detected`)
  }
  if (canonicalJson(metadata.packages) !== canonicalJson(expected.packages)) {
    throw new Error(`${PROVENANCE_FILENAME} generated package drift detected`)
  }
  return metadata
}
