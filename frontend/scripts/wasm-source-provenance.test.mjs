import assert from "node:assert/strict"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
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
    await callback(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("source provenance is deterministic and records source/package hashes", async () => {
  await withFixture(async (root) => {
    const first = await buildSourceProvenance(root, {
      sourceFiles: ["rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs"],
    })
    const second = await buildSourceProvenance(root, {
      sourceFiles: ["rust-crypto/Cargo.toml", "rust-crypto/Cargo.lock", "rust-crypto/src/lib.rs"],
    })
    assert.deepEqual(first, second)
    assert.equal(first.schema_version, 1)
    assert.equal(first.source_files.length, 3)
    assert.equal(first.packages["rust-crypto/pkg/uni_wasm_crypto_bg.wasm"].size, 4)
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
