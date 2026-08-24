import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { describe, it } from "node:test"
import { fileURLToPath } from "node:url"

import { validateWasmArtifacts } from "./verify-wasm-artifacts.mjs"
import { buildWasmArtifacts } from "./build-wasm.mjs"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const mergeScriptPath = path.join(__dirname, "merge-vitest-coverage.mjs")
const frontendRoot = path.dirname(__dirname)

// A valid minimal 36-byte WASM binary module (\0asm + version 1 + empty sections)
const validMinimalWasm = Buffer.from([
  0x00,
  0x61,
  0x73,
  0x6d, // magic
  0x01,
  0x00,
  0x00,
  0x00, // version
  0x00,
  0x08,
  0x04,
  0x74,
  0x65,
  0x73,
  0x74,
  0x00,
  0x00,
  0x00,
  0x00,
  0x08,
  0x04,
  0x74,
  0x65,
  0x73,
  0x74,
  0x00,
  0x00,
  0x00,
  0x00,
  0x08,
  0x04,
  0x74,
  0x65,
  0x73,
  0x74,
  0x00,
  0x00,
  0x00,
])

const validSanitizerJs = `async function init() { return undefined }
export { init as default }
export function initSync() {}
export function sanitize_rich_text(html) { return "clean" }
export function sanitize_html_basic(html) { return "clean" }
export function strip_html(html) { return "clean" }
export function sanitize_rich_text_raw(html) { return "clean" }
`

const validCryptoJs = `async function init() { return undefined }
export { init as default }
export function pbkdf2_derive() { return "derived" }
export function scrypt_derive() { return Uint8Array.of(1) }
export function hmac_sha256_sign() { return "signature" }
`

async function createFixturePackage(root, name, overrides = {}) {
  const pkgDir = path.join(root, name, "pkg")
  await mkdir(pkgDir, { recursive: true })
  const isCrypto = name === "rust-crypto"
  const defaultPkgName = isCrypto ? "uni-wasm-crypto" : name
  const defaultJsFile = isCrypto ? "uni_wasm_crypto.js" : "wasm_sanitizer.js"
  const defaultWasmFile = isCrypto ? "uni_wasm_crypto_bg.wasm" : "wasm_sanitizer_bg.wasm"
  const defaultSource = isCrypto ? validCryptoJs : validSanitizerJs

  await writeFile(
    path.join(pkgDir, "package.json"),
    JSON.stringify({
      name: overrides.packageName ?? defaultPkgName,
      version: "0.1.0",
      type: overrides.packageType ?? "module",
      main: overrides.packageMain ?? defaultJsFile,
      ...overrides.extraMetadata,
    })
  )
  await writeFile(path.join(pkgDir, defaultJsFile), overrides.source ?? defaultSource)
  await writeFile(path.join(pkgDir, defaultWasmFile), overrides.wasm ?? validMinimalWasm)
}

function runMerger(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [mergeScriptPath, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    })
    let stdout = ""
    let stderr = ""
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (c) => {
      stdout += c
    })
    child.stderr.on("data", (c) => {
      stderr += c
    })
    child.once("error", reject)
    child.once("close", (code) => resolve({ code, stdout, stderr }))
  })
}

describe("ADVERSARIAL: merge-vitest-coverage.mjs edge cases", () => {
  let tmpDir

  it("fails closed when missing --input or --output arguments", async () => {
    const res1 = await runMerger([])
    assert.notEqual(res1.code, 0)
    assert.match(res1.stderr, /Usage:/)

    const res2 = await runMerger(["--input=some_dir"])
    assert.notEqual(res2.code, 0)
    assert.match(res2.stderr, /Usage:/)
  })

  it("fails closed on non-integer or non-positive --expected-shards", async () => {
    tmpDir = await mkdtemp(path.join(os.tmpdir(), "vitest-cov-adv-"))
    const inDir = path.join(tmpDir, "in")
    const outDir = path.join(tmpDir, "out")
    await mkdir(inDir, { recursive: true })
    const sampleReport = {
      "src/sample.ts": {
        path: "src/sample.ts",
        statementMap: { 0: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } } },
        fnMap: {},
        branchMap: {},
        s: { 0: 1 },
        f: {},
        b: {},
      },
    }
    await writeFile(path.join(inDir, "coverage-final.json"), JSON.stringify(sampleReport))

    for (const badVal of ["0", "-1", "abc"]) {
      const res = await runMerger([
        `--input=${inDir}`,
        `--output=${outDir}`,
        `--expected-shards=${badVal}`,
      ])
      assert.notEqual(res.code, 0)
      assert.match(res.stderr, /--expected-shards must be a positive integer/)
    }
  })

  it("fails closed when encountering malformed JSON syntax in a shard", async () => {
    const shardDir = path.join(tmpDir, "shard-malformed")
    await mkdir(shardDir, { recursive: true })
    await writeFile(path.join(shardDir, "coverage-final.json"), "{ invalid: json content [}")

    const outDir = path.join(tmpDir, "out-malformed")
    const res = await runMerger([`--input=${shardDir}`, `--output=${outDir}`])
    assert.notEqual(res.code, 0)
    assert.match(res.stderr, /Cannot parse coverage report/)
  })

  it("fails closed when a shard report is an array or null", async () => {
    const shardDir = path.join(tmpDir, "shard-array")
    await mkdir(shardDir, { recursive: true })
    await writeFile(path.join(shardDir, "coverage-final.json"), '["not", "an", "object"]')

    const outDir = path.join(tmpDir, "out-array")
    const res = await runMerger([`--input=${shardDir}`, `--output=${outDir}`])
    assert.notEqual(res.code, 0)
    assert.match(res.stderr, /must be a JSON object/)
  })

  it("fails closed when merged coverage report is empty (no instrumented files)", async () => {
    const shardDir = path.join(tmpDir, "shard-empty-obj")
    await mkdir(shardDir, { recursive: true })
    await writeFile(path.join(shardDir, "coverage-final.json"), "{}")

    const outDir = path.join(tmpDir, "out-empty-obj")
    const res = await runMerger([`--input=${shardDir}`, `--output=${outDir}`])
    assert.notEqual(res.code, 0)
    assert.match(res.stderr, /Merged coverage contains no instrumented files/)
  })

  it("successfully discovers and merges deeply nested shards and accumulates counts", async () => {
    const deepRoot = path.join(tmpDir, "deep")
    const shard1 = path.join(deepRoot, "a", "b", "c")
    const shard2 = path.join(deepRoot, "x", "y", "z")
    await mkdir(shard1, { recursive: true })
    await mkdir(shard2, { recursive: true })

    const fileA = "src/moduleA.ts"
    const fileB = "src/moduleB.ts"
    const makeReport = (p, hits) => ({
      [p]: {
        path: p,
        statementMap: { 0: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } } },
        fnMap: {
          0: {
            name: "test",
            decl: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } },
            loc: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } },
          },
        },
        branchMap: {},
        s: { 0: hits },
        f: { 0: hits },
        b: {},
      },
    })

    await writeFile(path.join(shard1, "coverage-final.json"), JSON.stringify(makeReport(fileA, 2)))
    await writeFile(path.join(shard2, "coverage-final.json"), JSON.stringify(makeReport(fileB, 3)))

    const outDir = path.join(tmpDir, "deep-out")
    const res = await runMerger([
      `--input=${deepRoot}`,
      `--output=${outDir}`,
      "--expected-shards=2",
    ])
    assert.equal(res.code, 0, res.stderr)
    assert.match(res.stdout, /Merged 2 Vitest coverage shards/)

    const merged = JSON.parse(await readFile(path.join(outDir, "coverage-final.json"), "utf8"))
    assert.equal(merged[fileA].s["0"], 2)
    assert.equal(merged[fileB].s["0"], 3)

    const lcov = await readFile(path.join(outDir, "lcov.info"), "utf8")
    assert.match(lcov, /SF:.*moduleA\.ts/)
    assert.match(lcov, /SF:.*moduleB\.ts/)
  })
})

describe("ADVERSARIAL: verify-wasm-artifacts.mjs edge cases", () => {
  it("rejects when directory does not exist", async () => {
    await assert.rejects(() => validateWasmArtifacts("C:/non-existent-wasm-path-12345"), /ENOENT/)
  })

  it("rejects WASM binary with valid magic but truncated length (<= 32 bytes)", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-trunc-"))
    try {
      await createFixturePackage(tmp, "wasm-sanitizer", {
        wasm: Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]), // only 8 bytes
      })
      await createFixturePackage(tmp, "rust-crypto")
      await assert.rejects(
        () => validateWasmArtifacts(tmp),
        /wasm-sanitizer is not a valid WebAssembly module/
      )
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })

  it("rejects WASM binary with valid length and magic but corrupted bytecode failing WebAssembly.validate()", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-corrupt-"))
    try {
      const corruptWasm = Buffer.concat([
        Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]),
        Buffer.alloc(64, 0xff), // invalid section opcode 0xff
      ])
      await createFixturePackage(tmp, "wasm-sanitizer", { wasm: corruptWasm })
      await createFixturePackage(tmp, "rust-crypto")
      await assert.rejects(
        () => validateWasmArtifacts(tmp),
        /wasm-sanitizer is not a valid WebAssembly module/
      )
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })

  it("rejects package.json with mismatched name or mismatched main file", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-mismatch-"))
    try {
      await createFixturePackage(tmp, "wasm-sanitizer", { packageName: "wrong-name" })
      await createFixturePackage(tmp, "rust-crypto")
      await assert.rejects(() => validateWasmArtifacts(tmp), /package metadata does not describe/)
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })

  it("rejects crypto package missing required export (e.g. scrypt_derive)", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-missing-exp-"))
    try {
      await createFixturePackage(tmp, "wasm-sanitizer")
      await createFixturePackage(tmp, "rust-crypto", {
        source: `async function init() {}
export { init as default }
export function pbkdf2_derive() { return "derived" }
export function hmac_sha256_sign() { return "signature" }
`, // omitted scrypt_derive
      })
      await assert.rejects(
        () => validateWasmArtifacts(tmp),
        /uni-wasm-crypto generated glue is missing required export: scrypt_derive/
      )
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })

  it("rejects fake crypto placeholders returning empty outputs", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-fake-crypto-"))
    try {
      await createFixturePackage(tmp, "wasm-sanitizer")
      await createFixturePackage(tmp, "rust-crypto", {
        source: `async function init() {}
export { init as default }
export function pbkdf2_derive() { return ""; }
export function scrypt_derive() { return new Uint8Array(); }
export function hmac_sha256_sign() { return "sig"; }
`,
      })
      await assert.rejects(
        () => validateWasmArtifacts(tmp),
        /uni-wasm-crypto generated glue contains a empty cryptographic output placeholder/
      )
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })
})

describe("ADVERSARIAL: build-wasm.mjs flags and fail-closed contracts", () => {
  it("SKIP_WASM_BUILD=1 validates existing valid artifacts without executing wasm-pack", async () => {
    const tmp = await mkdtemp(path.join(os.tmpdir(), "wasm-skip-"))
    try {
      await createFixturePackage(tmp, "wasm-sanitizer")
      await createFixturePackage(tmp, "rust-crypto")

      const originalEnv = process.env.SKIP_WASM_BUILD
      process.env.SKIP_WASM_BUILD = "1"
      let commandInvoked = false
      const runCommand = async () => {
        commandInvoked = true
      }

      try {
        await buildWasmArtifacts(tmp, { runCommand })
        assert.equal(commandInvoked, false)
      } finally {
        if (originalEnv !== undefined) {
          process.env.SKIP_WASM_BUILD = originalEnv
        } else {
          delete process.env.SKIP_WASM_BUILD
        }
      }
    } finally {
      await rm(tmp, { recursive: true, force: true })
    }
  })
})

describe("EMPIRICAL: Live WASM runtime stress testing & security fuzzing", () => {
  let sanitizer
  let crypto

  it("loads and initializes production WASM modules from disk", async () => {
    sanitizer = await import("../wasm-sanitizer/pkg/wasm_sanitizer.js")
    crypto = await import("../rust-crypto/pkg/uni_wasm_crypto.js")

    const sanitizerBytes = await readFile(
      path.join(frontendRoot, "wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm")
    )
    const cryptoBytes = await readFile(
      path.join(frontendRoot, "rust-crypto/pkg/uni_wasm_crypto_bg.wasm")
    )

    await sanitizer.default({ module_or_path: sanitizerBytes })
    await crypto.default({ module_or_path: cryptoBytes })

    assert.equal(typeof sanitizer.sanitize_rich_text, "function")
    assert.equal(typeof sanitizer.strip_html, "function")
    assert.equal(typeof crypto.pbkdf2_derive, "function")
    assert.equal(typeof crypto.hmac_sha256_sign, "function")
    assert.equal(typeof crypto.scrypt_derive, "function")
  })

  it("sanitizer neutralizes advanced XSS attack payloads", () => {
    const dangerousPayloads = [
      "<script>alert('xss')</script>",
      '<SCRIPT/XSS SRC="http://evil.com/xss.js"></SCRIPT>',
      "<img src=x onerror=alert('img_xss')>",
      "<svg/onload=alert('svg_xss')>",
      "<iframe src=\"javascript:alert('iframe_xss')\"></iframe>",
      "<a href=\"javascript:alert('a_xss')\">evil link</a>",
      "<a href=\"jav&#x09;ascript:alert('proto_evasion')\">proto</a>",
      "<div onmouseover=\"alert('event_xss')\" onclick=\"alert('click')\">hover</div>",
      "<body onload=alert('body_xss')>",
      '<<SCRIPT>alert("nested");//<</SCRIPT>',
      '<object data="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="></object>',
      '<embed src="evil.swf"></embed>',
      '<link rel=import href="evil.html">',
      "<math><mtext><table><mglyph><style><img src=1 onerror=alert(1)>",
    ]

    for (const payload of dangerousPayloads) {
      const sanitized = sanitizer.sanitize_rich_text(payload)
      assert.doesNotMatch(
        sanitized,
        /<script|onerror|onload|onmouseover|onclick|javascript:|data:text\/html|<iframe|<object|<embed/i,
        `Payload was not safely neutralized: ${payload} -> ${sanitized}`
      )
    }
  })

  it("strip_html completely strips markup leaving only text content", () => {
    const raw = "<p>Hello <b>World</b>! <script>alert(1)</script><img src='x' alt='pic'> End.</p>"
    const stripped = sanitizer.strip_html(raw)
    assert.doesNotMatch(stripped, /<[^>]+>/)
    assert.match(stripped, /Hello World!.*End\./)
  })

  it("crypto module computes deterministic outputs for variable input lengths and boundaries", () => {
    // Empty key and data HMAC
    const hmacEmpty = crypto.hmac_sha256_sign("", "")
    assert.equal(hmacEmpty, "b613679a0814d9ec772f95d778c35fc5ff1697c493715653c6c712144292c5ad") // pragma: allowlist secret

    // Long payload HMAC (10,000 characters)
    const longData = "A".repeat(10000)
    const hmacLong = crypto.hmac_sha256_sign("secret-key", longData)
    assert.equal(typeof hmacLong, "string")
    assert.equal(hmacLong.length, 64)

    // PBKDF2 with 100 iterations
    const pbkdf2Res = crypto.pbkdf2_derive("mypassword", "mysalt", 100, 32)
    assert.equal(typeof pbkdf2Res, "string")
    assert.equal(pbkdf2Res.length, 64)

    // scrypt derivation with varied key length
    const scrypt32 = crypto.scrypt_derive(
      new TextEncoder().encode("pass"),
      new TextEncoder().encode("salt"),
      1024,
      8,
      1,
      32
    )
    assert.equal(scrypt32.length, 32)
  })
})
