import { spawnSync } from "node:child_process"
import { pbkdf2Sync, scryptSync } from "node:crypto"
import { copyFileSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  CRYPTO_WASM_PATH,
  SANITIZER_WASM_PATH,
  createRandom,
  generateText,
  runFuzzCampaign,
  sanitizedMarkupViolation,
  wasmArtifactProblem,
} from "../../../scripts/wasm-fuzzer.mjs"

/**
 * AUD-416: the WASM fuzzer must never report success for artifacts it did not
 * exercise. These checks run the shipped script without the compiled modules.
 */
describe("wasm fuzzer artifact gate", () => {
  let dir: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "wasm-fuzz-"))
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it("classifies an absent artifact as missing", () => {
    expect(wasmArtifactProblem(join(dir, "absent.wasm"))).toBe("missing")
  })

  it("rejects a placeholder-sized artifact", () => {
    const path = join(dir, "placeholder.wasm")
    writeFileSync(path, Buffer.alloc(64))
    expect(wasmArtifactProblem(path)).toBe("placeholder-sized")
  })

  it("rejects a large file that does not start with the WebAssembly header", () => {
    const path = join(dir, "text.wasm")
    writeFileSync(path, Buffer.alloc(2048, 0x41))
    expect(wasmArtifactProblem(path)).toBe("invalid-magic")
  })

  it("accepts a module-sized file with the WebAssembly header", () => {
    const path = join(dir, "module.wasm")
    writeFileSync(path, Buffer.concat([Buffer.from([0x00, 0x61, 0x73, 0x6d]), Buffer.alloc(2000)]))
    expect(wasmArtifactProblem(path)).toBeNull()
  })

  it("fails closed instead of passing when the artifacts are placeholders", async () => {
    const path = join(dir, "placeholder.wasm")
    writeFileSync(path, Buffer.alloc(64))

    const result = await runFuzzCampaign({ sanitizerPath: path, cryptoPath: path, iterations: 1 })

    expect(result.ok).toBe(false)
    expect(result.executed).toBe(0)
    expect(result.failures).toHaveLength(2)
  })

  it("restores the WebAssembly constructor when wrapper initialization throws", () => {
    const sanitizerPath = join(dir, "sanitizer.wasm")
    const cryptoPath = join(dir, "crypto.wasm")
    copyFileSync(SANITIZER_WASM_PATH, sanitizerPath)
    copyFileSync(CRYPTO_WASM_PATH, cryptoPath)
    writeFileSync(join(dir, "package.json"), '{"type":"module"}')
    writeFileSync(
      join(dir, "wasm_sanitizer.js"),
      'export function initSync() { throw new Error("initializer failed") }'
    )
    const fuzzerScript = resolve(dirname(CRYPTO_WASM_PATH), "../../scripts/wasm-fuzzer.mjs")
    const child = spawnSync(
      process.execPath,
      [
        "--input-type=module",
        "--eval",
        `import { pathToFileURL } from "node:url"
         const [script, sanitizerPath, cryptoPath] = process.argv.slice(2)
         const { runFuzzCampaign } = await import(pathToFileURL(script).href)
         const original = WebAssembly.Instance
         const result = await runFuzzCampaign({ sanitizerPath, cryptoPath, iterations: 1 })
         console.log(JSON.stringify({ result, restored: WebAssembly.Instance === original }))`,
        "wasm-fuzz-fixture",
        fuzzerScript,
        sanitizerPath,
        cryptoPath,
      ],
      { encoding: "utf8", timeout: 10_000 }
    )

    expect(child.status, child.stderr).toBe(0)
    expect(JSON.parse(child.stdout)).toEqual({
      result: { ok: false, executed: 0, failures: ["fuzz campaign: threw initializer failed"] },
      restored: true,
    })
  })

  it("fails closed when an artifact is missing", async () => {
    const result = await runFuzzCampaign({
      sanitizerPath: join(dir, "absent.wasm"),
      cryptoPath: join(dir, "absent.wasm"),
      iterations: 1,
    })

    expect(result.ok).toBe(false)
    expect(result.failures[0]).toContain("missing")
  })

  it.each([0, -1, 1.5, Number.NaN, 100_001])(
    "fails closed for an invalid iteration count (%s) before reading artifacts",
    async (iterations) => {
      const path = join(dir, "placeholder.wasm")
      writeFileSync(path, Buffer.alloc(64))

      const result = await runFuzzCampaign({ sanitizerPath: path, cryptoPath: path, iterations })

      expect(result.ok).toBe(false)
      expect(result.executed).toBe(0)
      expect(result.failures).toHaveLength(1)
      expect(result.failures[0]).toContain("iterations")
    }
  )

  it("fails closed for a non-integer or negative seed", async () => {
    const path = join(dir, "placeholder.wasm")
    writeFileSync(path, Buffer.alloc(64))

    const result = await runFuzzCampaign({ sanitizerPath: path, cryptoPath: path, seed: -1 })

    expect(result.ok).toBe(false)
    expect(result.failures[0]).toContain("seed")
  })
})

describe("wasm fuzzer oracles and generators", () => {
  it("flags script-capable elements and event-handler attributes left in sanitizer output", () => {
    expect(sanitizedMarkupViolation("<p>safe</p>")).toBeNull()
    expect(sanitizedMarkupViolation("<script>alert(1)</script>")).toBe("kept a script element")
    expect(sanitizedMarkupViolation('<img src="x" onerror=alert(1)>')).toBe(
      "kept an event-handler attribute"
    )
    expect(sanitizedMarkupViolation(42)).toBe("returned number")
  })

  it.each(["iframe", "object", "embed", "style", "base", "meta", "form", "svg", "math"])(
    "flags a retained <%s> element",
    (tag) => {
      expect(sanitizedMarkupViolation(`<${tag}>content</${tag}>`)).toBe("kept a dangerous element")
    }
  )

  it.each([
    { description: "JavaScript", markup: '<a href="javascript:alert(1)">x</a>', unsafe: true },
    {
      description: "entity-encoded JavaScript",
      markup: "<a href='javascript&#x3a;alert(1)'>x</a>",
      unsafe: true,
    },
    {
      description: "hex-entity tab in JavaScript scheme",
      markup: '<a href="java&#x09;script:alert(1)">x</a>',
      unsafe: true,
    },
    {
      description: "decimal-entity newline in JavaScript scheme",
      markup: '<a href="java&#10;script:alert(1)">x</a>',
      unsafe: true,
    },
    {
      description: "named Tab in JavaScript scheme",
      markup: '<a href="java&Tab;script:alert(1)">x</a>',
      unsafe: true,
    },
    {
      description: "named NewLine in JavaScript scheme",
      markup: '<a href="java&NewLine;script:alert(1)">x</a>',
      unsafe: true,
    },
    {
      description: "JavaScript with control whitespace",
      markup: '<a href="java\nscript:alert(1)">x</a>',
      unsafe: true,
    },
    { description: "vbscript", markup: '<a xlink:href="vbscript:alert(1)">x</a>', unsafe: true },
    { description: "non-image data", markup: '<img src="data:text/html,alert(1)">', unsafe: true },
    {
      description: "form action",
      markup: '<div action="javascript:alert(1)">x</div>',
      unsafe: true,
    },
    {
      description: "formaction",
      markup: '<button formaction="javascript:alert(1)">x</button>',
      unsafe: true,
    },
    {
      description: "inert raster image data",
      markup: '<img src="data:image/png;base64,AAAA">',
      unsafe: false,
    },
    {
      description: "JavaScript after a double-quoted greater-than attribute",
      markup: '<a title=">" href="javascript:alert(1)">x</a>',
      unsafe: true,
    },
    {
      description: "data URL after a single-quoted greater-than attribute",
      markup: "<a title=' > ' href='data:text/html,alert(1)'>x</a>",
      unsafe: true,
    },
    {
      description: "JavaScript before a quoted greater-than attribute",
      markup: '<a href="javascript:alert(1)" title=">">x</a>',
      unsafe: true,
    },
    {
      description: "unterminated quoted markup that parses as text",
      markup: '<a href="javascript:alert(1)',
      unsafe: false,
    },
    {
      description: "unterminated unquoted markup that parses as text",
      markup: "<a href=javascript:alert(1",
      unsafe: false,
    },
    {
      description: "unclosed anchor with a retained JavaScript URL",
      markup: '<a href="javascript:alert(1)">x',
      unsafe: true,
    },
    {
      description: "safe text in an HTML comment",
      markup: '<!-- <a href="javascript:alert(1)"> -->',
      unsafe: false,
    },
    {
      description: "JavaScript URL after an abruptly closed empty comment",
      markup: "<!--><a href=javascript:alert(1)>x</a>",
      unsafe: true,
    },
    {
      description: "JavaScript URL after an abruptly closed dashed comment",
      markup: "<!---><a href=javascript:alert(1)>x</a>",
      unsafe: true,
    },
    {
      description: "event handler after a double-quoted greater-than attribute",
      markup: '<img title=">" onerror=alert(1)>',
      unsafe: true,
      eventHandler: true,
    },
    {
      description: "event handler after a single-quoted greater-than attribute",
      markup: "<div title=' > ' onclick=alert(1)>x</div>",
      unsafe: true,
      eventHandler: true,
    },
    {
      description: "event handler before a quoted greater-than attribute",
      markup: '<img onerror=alert(1) title=">">',
      unsafe: true,
      eventHandler: true,
    },
  ])("checks $description in sanitizer output", ({ markup, unsafe, eventHandler }) => {
    expect(sanitizedMarkupViolation(markup)).toBe(
      eventHandler
        ? "kept an event-handler attribute"
        : unsafe
          ? "kept an unsafe URL attribute"
          : null
    )
  })

  it("replays the same text from the same seed and keeps every string valid UTF-16", () => {
    const first = generateText(createRandom(7))
    expect(generateText(createRandom(7))).toBe(first)
    expect(Buffer.from(first, "utf8").toString("utf8")).toBe(first)
  })

  it("produces different text for different seeds", () => {
    expect(generateText(createRandom(7))).not.toBe(generateText(createRandom(8)))
  })
})

function runStubCampaign(mode: string, iterations = 1) {
  const dir = mkdtempSync(join(tmpdir(), "wasm-fuzz-oracle-"))
  const sanitizerPath = join(dir, "sanitizer.wasm")
  const cryptoPath = join(dir, "crypto.wasm")
  const sanitizerScript = join(dir, "wasm_sanitizer.js")
  const cryptoScript = join(dir, "uni_wasm_crypto.js")

  try {
    writeFileSync(join(dir, "package.json"), '{"type":"module"}')
    copyFileSync(SANITIZER_WASM_PATH, sanitizerPath)
    copyFileSync(CRYPTO_WASM_PATH, cryptoPath)
    copyFileSync(
      join(dirname(SANITIZER_WASM_PATH), "wasm_sanitizer.js"),
      join(dir, "real-sanitizer.js")
    )
    copyFileSync(join(dirname(CRYPTO_WASM_PATH), "uni_wasm_crypto.js"), join(dir, "real-crypto.js"))
    expect(WebAssembly.validate(readFileSync(sanitizerPath))).toBe(true)
    expect(WebAssembly.validate(readFileSync(cryptoPath))).toBe(true)
    writeFileSync(
      sanitizerScript,
      `import * as real from "./real-sanitizer.js"
       const mode = ${JSON.stringify(mode)}
       export const calls = globalThis.__aud416SanitizerCalls ??= { basic: 0, rich: 0, strip: 0 }
       export const initSync = (args) => mode === "passthrough" ? undefined : real.initSync(args)
       const skip = mode === "init-only" || mode === "skip-sanitizer"
       function safeText(input) {
         const end = input.indexOf("</p>")
         return input.startsWith("<p>") && end > 3 ? input.slice(3, end) : ""
       }
       export function sanitize_html_basic(input) {
         calls.basic++
         if (mode === "throw-basic-third" && calls.basic === 3) throw Error("injected basic failure")
         const output = skip || mode === "skip-basic" || (mode === "skip-basic-third" && calls.basic === 3) ? safeText(input) : real.sanitize_html_basic(mode === "fixed-basic" ? "<p>fixed</p>" : input)
         return mode === "fixed-basic" ? safeText(input) : mode === "basic" || mode === "all" ? "" : output
       }
       export function sanitize_rich_text(input) {
         calls.rich++
         const output = skip || mode === "skip-rich" ? safeText(input) : real.sanitize_rich_text(input)
         return mode === "rich" || mode === "all" ? "" : output
       }
       export function strip_html(input) {
         calls.strip++
         const output = skip || mode === "skip-strip" ? safeText(input) : real.strip_html(input)
         return mode === "strip" || mode === "all" ? "" : output
       }`
    )
    writeFileSync(
      cryptoScript,
      `import * as real from "./real-crypto.js"
       import { createHmac, pbkdf2Sync, scryptSync } from "node:crypto"
       const mode = ${JSON.stringify(mode)}
       export const calls = globalThis.__aud416CryptoCalls ??= { hex: 0, base64: 0, pbkdf2: 0, scrypt: 0 }
       export const initSync = (args) => mode === "passthrough" ? undefined : real.initSync(args)
       const skip = mode === "init-only" || mode === "skip-crypto"
       export function hmac_sha256_sign(key, message) {
         calls.hex++
         if (mode === "throw-hex-first") throw Error("injected HMAC failure")
         const output = skip || mode === "skip-hex" ? createHmac("sha256", key).update(message).digest("hex") : real.hmac_sha256_sign(mode === "fixed-hex" ? "fixed" : key, message)
         return mode === "fixed-hex" ? createHmac("sha256", key).update(message).digest("hex") : mode === "hex" || mode === "all" ? "a".repeat(64) : output
       }
       export function hmac_sha256_sign_base64(key, message) {
         calls.base64++
         const output = skip || mode === "skip-base64" ? createHmac("sha256", key).update(message).digest("base64") : real.hmac_sha256_sign_base64(key, message)
         return mode === "base64" || mode === "all" ? "A".repeat(43) + "=" : output
       }
       export function pbkdf2_derive(password, salt, iterations, size) {
         calls.pbkdf2++
         try {
           const bypass = skip || mode === "skip-pbkdf2"
           if (bypass && (iterations < 1000 || iterations > 1000000 || size < 1 || size > 1024)) throw Error("invalid")
           const cost = mode === "alter-cost" && iterations >= 1000 && iterations < 1000000 ? iterations + 1 : iterations
           const output = bypass ? pbkdf2Sync(password, salt, iterations, size, "sha256").toString("hex") : real.pbkdf2_derive(password, salt, cost, size)
           return mode === "alter-cost" ? pbkdf2Sync(password, salt, iterations, size, "sha256").toString("hex") : mode === "pbkdf2" || mode === "all" ? "a".repeat(size * 2) : output
         } catch (error) {
           if (mode === "weak-pbkdf2" && iterations === 1) return "a".repeat(size * 2)
           throw error
         }
       }
       export function scrypt_derive(password, salt, n, r, p, size) {
         calls.scrypt++
         if (mode === "mutate-scrypt") password.fill(0)
         try {
           const bypass = skip || mode === "skip-scrypt"
           if (bypass && (n < 16 || (n & (n - 1)) !== 0 || r === 0 || size < 10 || size > 64)) throw Error("invalid")
           const output = bypass ? scryptSync(password, salt, size, { N: n, r, p }) : real.scrypt_derive(password, salt, n, r, p, size)
           return mode === "scrypt" || mode === "all" ? new Uint8Array(size) : output
         } catch (error) {
           if (mode === "weak-scrypt" && n === 1) return new Uint8Array(size)
           throw error
         }
       }`
    )

    const fuzzerScript = resolve(dirname(CRYPTO_WASM_PATH), "../../scripts/wasm-fuzzer.mjs")
    const child = spawnSync(
      process.execPath,
      [
        "--input-type=module",
        "--eval",
        `import { pathToFileURL } from "node:url"
         const [fuzzerPath, sanitizerPath, cryptoPath, sanitizerScript, cryptoScript, iterations] = process.argv.slice(2)
         const { runFuzzCampaign } = await import(pathToFileURL(fuzzerPath).href)
         const result = await runFuzzCampaign({ sanitizerPath, cryptoPath, seed: 20261101, iterations: Number(iterations) })
         const sanitizer = await import(pathToFileURL(sanitizerScript).href)
         const crypto = await import(pathToFileURL(cryptoScript).href)
         console.log(JSON.stringify({ result, calls: { ...sanitizer.calls, ...crypto.calls } }))`,
        "wasm-fuzz-fixture",
        fuzzerScript,
        sanitizerPath,
        cryptoPath,
        sanitizerScript,
        cryptoScript,
        String(iterations),
      ],
      { encoding: "utf8", timeout: 10_000 }
    )

    expect(child.error).toBeUndefined()
    expect(child.status, child.stderr).toBe(0)
    return JSON.parse(child.stdout) as {
      result: { ok: boolean; executed: number; failures: string[] }
      calls: Record<string, number>
    }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe("wasm fuzzer binary campaign", () => {
  it("fails when wrappers instantiate the binaries but skip their exports", () => {
    const { result } = runStubCampaign("init-only")

    expect(result.ok).toBe(false)
    expect(result.failures.some((failure) => failure.includes("WebAssembly"))).toBe(true)
  })
  it.each([
    ["skip-sanitizer", "sanitize_html_basic"],
    ["skip-crypto", "hmac_sha256_sign"],
  ])("detects %s even when the other binary is exercised", (mode, label) => {
    const { result } = runStubCampaign(mode)

    expect(result.ok).toBe(false)
    expect(
      result.failures.some(
        (failure) =>
          failure.startsWith(`${label}:`) && failure.includes("skipped the WebAssembly export")
      )
    ).toBe(true)
  })

  it.each([
    ["skip-basic", "sanitize_html_basic"],
    ["skip-rich", "sanitize_rich_text"],
    ["skip-strip", "strip_html"],
    ["skip-hex", "hmac_sha256_sign"],
    ["skip-base64", "hmac_sha256_sign_base64"],
    ["skip-pbkdf2", "pbkdf2_derive"],
    ["skip-scrypt", "scrypt_derive"],
  ])("detects one skipped WASM export: %s", (mode, label) => {
    const { result } = runStubCampaign(mode)

    expect(result.ok).toBe(false)
    expect(
      result.failures.some(
        (failure) =>
          failure.startsWith(`${label}:`) && failure.includes("skipped the WebAssembly export")
      )
    ).toBe(true)
  })

  it("detects a single skipped invocation among calls that reach WASM", () => {
    const { result } = runStubCampaign("skip-basic-third", 2)

    expect(result.ok).toBe(false)
    expect(result.failures).toContain("sanitize_html_basic: 1 calls skipped the WebAssembly export")
  })

  it.each([
    ["fixed-basic", "sanitize_html_basic"],
    ["fixed-hex", "hmac_sha256_sign"],
    ["alter-cost", "pbkdf2_derive"],
    ["mutate-scrypt", "scrypt_derive"],
  ])("detects changed inputs passed to a called WASM export: %s", (mode, label) => {
    const { result } = runStubCampaign(mode, 2)

    expect(result.ok).toBe(false)
    expect(
      result.failures.some(
        (failure) =>
          failure.startsWith(`${label}:`) && failure.includes("WebAssembly inputs differ")
      )
    ).toBe(true)
  })

  it("fails when realistic wrappers ignore both WASM binaries", () => {
    const { result } = runStubCampaign("passthrough")

    expect(result.ok).toBe(false)
    expect(result.failures.some((failure) => failure.includes("WebAssembly"))).toBe(true)
  })

  it("enforces crypto cost boundaries through the generated WASM exports", async () => {
    const crypto = await import("../../../rust-crypto/pkg/uni_wasm_crypto.js")
    crypto.initSync({ module: readFileSync(CRYPTO_WASM_PATH) })

    for (const iterations of [0, 1, 999]) {
      expect(() => crypto.pbkdf2_derive("pw", "salt", iterations, 32)).toThrow(
        "PBKDF2 iterations must be between 1,000 and 1,000,000"
      )
    }
    expect(crypto.pbkdf2_derive("pw", "salt", 1_000, 32)).toBe(
      pbkdf2Sync("pw", "salt", 1_000, 32, "sha256").toString("hex")
    )

    const password = Buffer.from("pw")
    const salt = Buffer.from("salt")
    expect(() => crypto.scrypt_derive(password, salt, 0, 1, 1, 32)).toThrow(
      "Invalid scrypt params: N must be a non-zero power of two"
    )
    for (const n of [1, 8]) {
      expect(() => crypto.scrypt_derive(password, salt, n, 1, 1, 32)).toThrow(
        "Invalid scrypt params: N must be at least 16"
      )
    }
    expect(Buffer.from(crypto.scrypt_derive(password, salt, 16, 1, 1, 32))).toEqual(
      scryptSync(password, salt, 32, { N: 16, r: 1, p: 1 })
    )
  })

  it.each([0, 7, 20261101])(
    "executes seed %s against both generated WASM modules",
    async (seed) => {
      const result = await runFuzzCampaign({ seed, iterations: 1 })

      expect(result).toEqual({ ok: true, executed: 22, failures: [] })
    }
  )

  it("executes varied inputs against both WASM modules", async () => {
    const result = await runFuzzCampaign({ seed: 20261101, iterations: 2 })

    expect(result).toEqual({ ok: true, executed: 31, failures: [] })
  })

  it("exits unsuccessfully for a zero-iteration campaign", () => {
    const script = resolve(dirname(CRYPTO_WASM_PATH), "../../scripts/wasm-fuzzer.mjs")
    const result = spawnSync(process.execPath, [script], {
      encoding: "utf8",
      env: { ...process.env, WASM_FUZZ_SEED: "20261101", WASM_FUZZ_ITERATIONS: "0" },
    })

    expect(result.error).toBeUndefined()
    expect(result.status).toBe(1)
    expect(result.stdout).not.toContain("passed")
    expect(result.stderr).toContain("iterations must be an integer from 1 to 100000")
  })

  it.each([
    ["weak-pbkdf2", "pbkdf2_derive(iterations=1)"],
    ["weak-scrypt", "scrypt_derive(N=1)"],
  ])("detects %s accepting a degenerate cost", (mode, label) => {
    const { result, calls } = runStubCampaign(mode)

    expect(result.ok).toBe(false)
    expect(result.failures).toEqual([`${label}: invalid parameters were accepted`])
    expect(calls).toEqual({ basic: 2, rich: 2, strip: 1, hex: 1, base64: 1, pbkdf2: 7, scrypt: 8 })
    expect(result.executed).toBe(Object.values(calls).reduce((total, count) => total + count, 0))
  })

  it.each([
    ["rich", "sanitize_rich_text"],
    ["basic", "sanitize_html_basic"],
    ["strip", "strip_html"],
    ["hex", "hmac_sha256_sign"],
    ["base64", "hmac_sha256_sign_base64"],
    ["pbkdf2", "pbkdf2_derive"],
    ["scrypt", "scrypt_derive"],
  ])("rejects constant %s output with valid WASM artifacts", (mode, label) => {
    const { result } = runStubCampaign(mode)

    expect(result.ok).toBe(false)
    expect(result.failures.some((failure) => failure.startsWith(`${label}:`))).toBe(true)
  })

  it("rejects no-op wrappers returning plausible constants and rejecting weak costs", () => {
    const { result } = runStubCampaign("all")

    expect(result.ok).toBe(false)
    expect(result.failures.some((failure) => failure.startsWith("sanitize_rich_text:"))).toBe(true)
    expect(result.failures.some((failure) => failure.startsWith("pbkdf2_derive:"))).toBe(true)
  })

  it("counts every attempted export when a sanitizer throws during the campaign", () => {
    const { result, calls } = runStubCampaign("throw-basic-third", 2)

    expect(result.ok).toBe(false)
    expect(result.failures).toContain("fuzz campaign: threw injected basic failure")
    expect(calls).toEqual({ basic: 3, rich: 4, strip: 1, hex: 0, base64: 0, pbkdf2: 0, scrypt: 0 })
    expect(result.executed).toBe(8)
  })

  it("retains sanitizer progress and the attempted call when a crypto export throws", () => {
    const { result, calls } = runStubCampaign("throw-hex-first")

    expect(result.ok).toBe(false)
    expect(result.failures).toContain("fuzz campaign: threw injected HMAC failure")
    expect(calls).toEqual({ basic: 2, rich: 2, strip: 1, hex: 1, base64: 0, pbkdf2: 0, scrypt: 0 })
    expect(result.executed).toBe(6)
  })
})
