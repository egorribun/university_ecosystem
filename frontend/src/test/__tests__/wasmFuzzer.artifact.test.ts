import { spawnSync } from "node:child_process"
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  CRYPTO_WASM_PATH,
  SANITIZER_WASM_PATH,
  wasmArtifactProblem,
} from "../../../scripts/wasm-fuzzer.mjs"

describe("wasm fuzzer artifact failures", () => {
  let root: string
  let script: string
  let sanitizerDir: string
  let sanitizerPath: string

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "wasm-fuzzer-artifacts-"))
    const scriptsDir = join(root, "frontend", "scripts")
    sanitizerDir = join(root, "frontend", "wasm-sanitizer", "pkg")
    const cryptoDir = join(root, "frontend", "rust-crypto", "pkg")
    for (const dir of [scriptsDir, sanitizerDir, cryptoDir]) mkdirSync(dir, { recursive: true })

    script = join(scriptsDir, "wasm-fuzzer.mjs")
    sanitizerPath = join(sanitizerDir, "wasm_sanitizer_bg.wasm")
    copyFileSync(resolve(dirname(SANITIZER_WASM_PATH), "../../scripts/wasm-fuzzer.mjs"), script)
    copyFileSync(SANITIZER_WASM_PATH, sanitizerPath)
    copyFileSync(CRYPTO_WASM_PATH, join(cryptoDir, "uni_wasm_crypto_bg.wasm"))
    writeFileSync(join(sanitizerDir, "package.json"), JSON.stringify({ type: "module" }))
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  function runFixture() {
    return spawnSync(process.execPath, [script], {
      encoding: "utf8",
      env: { ...process.env, WASM_FUZZ_SEED: "20261101", WASM_FUZZ_ITERATIONS: "1" },
      timeout: 10_000,
    })
  }

  it("fails without a success report when the generated JavaScript wrapper is missing", () => {
    expect(wasmArtifactProblem(sanitizerPath)).toBeNull()
    expect(WebAssembly.validate(readFileSync(sanitizerPath))).toBe(true)

    const result = runFixture()

    expect(result.error).toBeUndefined()
    expect(result.status).toBe(1)
    expect(result.stdout).not.toContain("Fuzzer passed")
    expect(result.stderr).toContain("Fuzz failure: fuzz campaign: threw")
    expect(result.stderr).toContain("wasm_sanitizer.js")
    expect(result.stderr).toContain("Fuzzer FAILED after 0 cases")
  })

  it("fails without a success report for a corrupt binary with valid magic and size", () => {
    const corrupt = Buffer.concat([Buffer.from([0, 0x61, 0x73, 0x6d]), Buffer.alloc(2000)])
    writeFileSync(sanitizerPath, corrupt)
    copyFileSync(
      join(dirname(SANITIZER_WASM_PATH), "wasm_sanitizer.js"),
      join(sanitizerDir, "wasm_sanitizer.js")
    )
    expect(wasmArtifactProblem(sanitizerPath)).toBeNull()
    expect(WebAssembly.validate(corrupt)).toBe(false)

    const result = runFixture()

    expect(result.error).toBeUndefined()
    expect(result.status).toBe(1)
    expect(result.stdout).not.toContain("Fuzzer passed")
    expect(result.stderr).toContain("Fuzz failure: fuzz campaign: threw")
    expect(result.stderr).toMatch(/WebAssembly|version/)
    expect(result.stderr).toContain("Fuzzer FAILED after 0 cases")
  })
})
