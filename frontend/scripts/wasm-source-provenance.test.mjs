import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  PROVENANCE_FILENAME,
  buildSourceProvenance,
  writeSourceProvenance,
  validateSourceProvenance,
} from "./wasm-source-provenance.mjs"

async function withFixture(callback) {
  const root = await mkdtemp(path.join(os.tmpdir(), "wasm-source-provenance-"))
  try {
    await mkdir(path.join(root, "rust-crypto", "src"), { recursive: true })
    await mkdir(path.join(root, "rust-crypto", "pkg"), { recursive: true })
    await mkdir(path.join(root, "wasm-sanitizer", "src"), { recursive: true })
    await mkdir(path.join(root, "wasm-sanitizer", "pkg"), { recursive: true })
    await writeFile(path.join(root, "rust-crypto", "pkg", ".gitignore"), "*\n")
    await writeFile(path.join(root, "wasm-sanitizer", "pkg", ".gitignore"), "*\n")
    await writeFile(path.join(root, "rust-crypto", "Cargo.toml"), "[package]\nname='crypto'\n")
    await writeFile(path.join(root, "rust-crypto", "Cargo.lock"), "version = 4\n")
    await writeFile(
      path.join(root, "rust-crypto", "src", "lib.rs"),
      "pub fn answer() -> u8 { 42 }\n"
    )
    await writeFile(path.join(root, "rust-crypto", "pkg", "uni_wasm_crypto.js"), "export {}\n")
    await writeFile(
      path.join(root, "rust-crypto", "pkg", "uni_wasm_crypto_bg.wasm"),
      Buffer.from([0, 97, 115, 109])
    )
    await writeFile(
      path.join(root, "rust-crypto", "pkg", "uni_wasm_crypto_bg.wasm.d.ts"),
      "// wasm-bindgen private declaration\n"
    )
    await writeFile(
      path.join(root, "wasm-sanitizer", "Cargo.toml"),
      "[package]\nname='sanitizer'\n"
    )
    await writeFile(path.join(root, "wasm-sanitizer", "Cargo.lock"), "version = 4\n")
    await writeFile(
      path.join(root, "wasm-sanitizer", "src", "lib.rs"),
      'pub fn sanitize() -> &\'static str { "ok" }\n'
    )
    await writeFile(path.join(root, "wasm-sanitizer", "pkg", "wasm_sanitizer.js"), "export {}\n")
    await writeFile(
      path.join(root, "wasm-sanitizer", "pkg", "wasm_sanitizer_bg.wasm"),
      Buffer.from([0, 97, 115, 109])
    )
    await writeFile(
      path.join(root, "wasm-sanitizer", "pkg", "wasm_sanitizer_bg.wasm.d.ts"),
      "// wasm-bindgen private declaration\n"
    )
    await callback(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("source provenance is deterministic and records source/package hashes", async () => {
  await withFixture(async (root) => {
    const first = await buildSourceProvenance(root, {
      sourceFiles: ["rust-crypto/src/lib.rs", "rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock"],
    })
    const second = await buildSourceProvenance(root, {
      sourceFiles: ["rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs", "rust-crypto/Cargo.toml"],
    })
    assert.deepEqual(first, second)
    assert.equal(first.schema_version, 1)
    assert.equal(first.source_files.length, 3)
    assert.deepEqual(
      first.source_files.map(({ path: relativePath }) => relativePath),
      ["rust-crypto/Cargo.lock", "rust-crypto/Cargo.toml", "rust-crypto/src/lib.rs"]
    )
    assert.equal(first.packages["rust-crypto/pkg/uni_wasm_crypto_bg.wasm"].size, 4)
    assert.equal(first.packages["rust-crypto/pkg/.gitignore"], undefined)
    assert.equal(first.packages["wasm-sanitizer/pkg/.gitignore"], undefined)
    assert.equal(first.packages["rust-crypto/pkg/uni_wasm_crypto_bg.wasm.d.ts"], undefined)
    assert.equal(first.packages["wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm.d.ts"], undefined)
  })
})

test("validator rejects source or generated package drift", async () => {
  await withFixture(async (root) => {
    await writeSourceProvenance(root, {
      sourceFiles: ["rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs"],
    })
    await assert.doesNotReject(() =>
      validateSourceProvenance(root, {
        sourceFiles: ["rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs"],
      })
    )

    await writeFile(
      path.join(root, "rust-crypto", "src", "lib.rs"),
      "pub fn answer() -> u8 { 43 }\n"
    )
    await assert.rejects(
      () =>
        validateSourceProvenance(root, {
          sourceFiles: [
            "rust-crypto/Cargo.toml",
            "rust-crypto/Cargo.lock",
            "rust-crypto/src/lib.rs",
          ],
        }),
      /source inventory drift/i
    )
  })
})

test("validator rejects unexpected provenance metadata fields", async () => {
  await withFixture(async (root) => {
    const sourceFiles = [
      "rust-crypto/Cargo.toml",
      "rust-crypto/Cargo.lock",
      "rust-crypto/src/lib.rs",
    ]
    await writeSourceProvenance(root, { sourceFiles })
    const metadataPath = path.join(root, PROVENANCE_FILENAME)
    const metadata = JSON.parse(await readFile(metadataPath, "utf8"))
    metadata.unexpected = "not part of the integrity contract"
    await writeFile(metadataPath, `${JSON.stringify(metadata)}\n`, "utf8")

    await assert.rejects(
      () => validateSourceProvenance(root, { sourceFiles }),
      /unexpected provenance metadata field/i
    )
  })
})

test("validator fails closed when the provenance file is missing", async () => {
  await withFixture(async (root) => {
    await assert.rejects(
      () => validateSourceProvenance(root),
      new RegExp(`${PROVENANCE_FILENAME}.*missing`, "i")
    )
  })
})

test("tampered package bytes are rejected even when source is unchanged", async () => {
  await withFixture(async (root) => {
    await writeSourceProvenance(root, {
      sourceFiles: ["rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs"],
    })
    await writeFile(
      path.join(root, "rust-crypto", "pkg", "uni_wasm_crypto_bg.wasm"),
      Buffer.from([0, 97, 115, 109, 1])
    )
    await assert.rejects(
      () =>
        validateSourceProvenance(root, {
          sourceFiles: [
            "rust-crypto/Cargo.toml",
            "rust-crypto/Cargo.lock",
            "rust-crypto/src/lib.rs",
          ],
        }),
      /generated package drift/i
    )
  })
})
