import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { promisify } from "node:util"

import { finalizeWasmLicenses } from "./finalize-wasm-licenses.mjs"

const run = promisify(execFile)
const legalFiles = [
  "LICENSE",
  "LICENSE-THIRD-PARTY",
  "LICENSE-THIRD-PARTY-SOURCES.md",
  "LICENSE-RUST-STD",
  "LICENSE-RUST-STD-COPYRIGHT.txt",
  "LICENSE-RUST-STD-SOURCES.md",
]

test("npm archives retain every legal file after wasm-pack generates a restrictive files list", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "wasm-license-pack-"))
  try {
    for (const crate of ["rust-crypto", "wasm-sanitizer"]) {
      const source = path.join(root, crate)
      const pkg = path.join(source, "pkg")
      await mkdir(pkg, { recursive: true })
      for (const file of legalFiles)
        await writeFile(path.join(source, file), `${file}\nUpstream text\n`)
      await writeFile(path.join(pkg, "module.js"), "export default 1\n")
      await writeFile(
        path.join(pkg, "package.json"),
        JSON.stringify({ name: crate, version: "1.0.0", files: ["module.js"] })
      )
    }
    await finalizeWasmLicenses(root)
    const first = await readFile(path.join(root, "rust-crypto/pkg/package.json"), "utf8")
    await finalizeWasmLicenses(root)
    assert.equal(await readFile(path.join(root, "rust-crypto/pkg/package.json"), "utf8"), first)
    for (const crate of ["rust-crypto", "wasm-sanitizer"]) {
      const pkg = path.join(root, crate, "pkg")
      for (const file of legalFiles) {
        assert.deepEqual(
          await readFile(path.join(pkg, file)),
          await readFile(path.join(root, crate, file))
        )
      }
      const npmCli =
        process.env.npm_execpath ||
        path.join(path.dirname(process.execPath), "node_modules/npm/bin/npm-cli.js")
      const { stdout } = await run(
        process.execPath,
        [npmCli, "pack", "--dry-run", "--json", "--ignore-scripts"],
        { cwd: pkg }
      )
      const packed = JSON.parse(stdout)[0].files.map(({ path: file }) => file)
      for (const file of legalFiles)
        assert.ok(packed.includes(file), `${crate}: ${file} missing from npm pack`)
      assert.ok(packed.includes("module.js"))
    }
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("missing source notices abort finalization", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "wasm-license-missing-"))
  try {
    const source = path.join(root, "rust-crypto")
    await mkdir(path.join(source, "pkg"), { recursive: true })
    await writeFile(path.join(source, "pkg/package.json"), JSON.stringify({ files: [] }))
    await writeFile(path.join(source, "LICENSE"), "project notice")
    await writeFile(path.join(source, "LICENSE-THIRD-PARTY"), "upstream notice")
    await assert.rejects(finalizeWasmLicenses(root), /LICENSE-THIRD-PARTY-SOURCES\.md/)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
