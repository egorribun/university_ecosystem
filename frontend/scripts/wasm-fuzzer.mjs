import fs from "node:fs"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(__dirname, "../..")

export const SANITIZER_WASM_PATH = path.resolve(
  rootDir,
  "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm"
)
export const CRYPTO_WASM_PATH = path.resolve(
  rootDir,
  "frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm"
)

const WASM_MAGIC = 0x0061736d
// Real wasm-bindgen modules are hundreds of kilobytes; placeholders are tiny.
const MIN_WASM_BYTES = 1000
const MAX_TEXT_CODE_POINTS = 2048
export const DEFAULT_SEED = 0x5eed1234
export const DEFAULT_ITERATIONS = 400
const MAX_ITERATIONS = 100_000

const SCRIPT_ELEMENT = /<\s*script\b/i
const EVENT_HANDLER_ATTRIBUTE = /<[^>]*\son[a-z]+\s*=/i
const LOWER_HEX_64 = /^[0-9a-f]{64}$/
const BASE64_44 = /^[A-Za-z0-9+/]{43}=$/

// Markup that historically breaks HTML sanitizers. Mixed into generated text
// so each campaign exercises both tag structure and arbitrary Unicode.
const MARKUP_FRAGMENTS = [
  "<script>alert(1)</script>",
  "<IMG SRC=javascript:alert('XSS')>",
  "<svg onload=alert(1)>",
  "<iframe src='javascript:alert(1)'>",
  '<a href="javascript:alert(1)">x</a>',
  "<![CDATA[<script>alert(1)</script>]]>",
  "<!-- <script> -->",
  '<p style="background:url(javascript:alert(1))">',
  "&lt;script&gt;",
  "<>\"'&",
  "\u0000",
  "�",
]

/** Why `filePath` is not a compiled WebAssembly module, or null when it is one. */
export function wasmArtifactProblem(filePath) {
  if (!fs.existsSync(filePath)) return "missing"
  if (fs.statSync(filePath).size < MIN_WASM_BYTES) return "placeholder-sized"
  const fd = fs.openSync(filePath, "r")
  try {
    const header = Buffer.alloc(4)
    fs.readSync(fd, header, 0, 4, 0)
    return header.readUInt32BE(0) === WASM_MAGIC ? null : "invalid-magic"
  } finally {
    fs.closeSync(fd)
  }
}

/** Deterministic mulberry32 generator: a failing campaign replays from its seed. */
export function createRandom(seed) {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function randomCodePoint(random) {
  // Stay out of the surrogate range so every generated string is valid UTF-16.
  return random() < 0.5 ? Math.floor(random() * 0xd800) : 0x10000 + Math.floor(random() * 0xfffff)
}

export function generateText(random) {
  const target = Math.floor(random() * MAX_TEXT_CODE_POINTS)
  const parts = []
  let length = 0
  while (length < target) {
    const part =
      random() < 0.6
        ? MARKUP_FRAGMENTS[Math.floor(random() * MARKUP_FRAGMENTS.length)]
        : String.fromCodePoint(randomCodePoint(random))
    parts.push(part)
    length += [...part].length
  }
  return parts.join("")
}

export function generateBytes(random, maxLength) {
  const bytes = new Uint8Array(Math.floor(random() * (maxLength + 1)))
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Math.floor(random() * 256)
  }
  return bytes
}

function fail(failures, label, detail) {
  failures.push(`${label}: ${detail}`)
}

/** Records a failure when `fn` does not throw; invalid parameters must be rejected. */
function expectRejection(failures, label, fn) {
  try {
    fn()
  } catch {
    return
  }
  fail(failures, label, "invalid parameters were accepted")
}

/** Describes the first unsafe construct left in sanitizer output, or null when it is clean. */
export function sanitizedMarkupViolation(output) {
  if (typeof output !== "string") return `returned ${typeof output}`
  if (SCRIPT_ELEMENT.test(output)) return "kept a script element"
  if (EVENT_HANDLER_ATTRIBUTE.test(output)) return "kept an event-handler attribute"
  return null
}

function checkSanitizedMarkup(failures, label, input, output) {
  const violation = sanitizedMarkupViolation(output)
  if (violation)
    fail(failures, label, `${violation} for input ${JSON.stringify(input.slice(0, 80))}`)
}

async function loadInitializedModule(jsPath, wasmPath) {
  const moduleNamespace = await import(pathToFileURL(jsPath).href)
  const wasmBuffer = fs.readFileSync(wasmPath)
  if (typeof moduleNamespace.initSync === "function") {
    moduleNamespace.initSync({ module: wasmBuffer })
  } else {
    await moduleNamespace.default({ module: wasmBuffer })
  }
  return moduleNamespace
}

async function fuzzSanitizer(wasmPath, random, iterations, failures) {
  const sanitizer = await loadInitializedModule(
    path.join(path.dirname(wasmPath), "wasm_sanitizer.js"),
    wasmPath
  )
  const { sanitize_html_basic, sanitize_rich_text, strip_html } = sanitizer
  let executed = 0
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const input = generateText(random)
    for (const [label, sanitize] of [
      ["sanitize_rich_text", sanitize_rich_text],
      ["sanitize_html_basic", sanitize_html_basic],
    ]) {
      const output = sanitize(input)
      checkSanitizedMarkup(failures, label, input, output)
      if (sanitize(input) !== output) fail(failures, label, "is not deterministic")
      executed += 2
    }
    if (typeof strip_html(input) !== "string")
      fail(failures, "strip_html", "did not return a string")
    executed += 1
  }
  return executed
}

async function fuzzCrypto(wasmPath, random, iterations, failures) {
  const crypto = await loadInitializedModule(
    path.join(path.dirname(wasmPath), "uni_wasm_crypto.js"),
    wasmPath
  )
  const { hmac_sha256_sign, hmac_sha256_sign_base64, pbkdf2_derive, scrypt_derive } = crypto
  let executed = 0
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const key = generateText(random)
    const message = generateText(random)
    const hex = hmac_sha256_sign(key, message)
    if (!LOWER_HEX_64.test(hex))
      fail(failures, "hmac_sha256_sign", "is not 64 lowercase hex digits")
    const encoded = hmac_sha256_sign_base64(key, message)
    if (!BASE64_44.test(encoded)) fail(failures, "hmac_sha256_sign_base64", "is not padded base64")

    const keySize = 1 + Math.floor(random() * 64)
    const pbkdf2Iterations = 1 + Math.floor(random() * 3)
    const derived = pbkdf2_derive(key, message, pbkdf2Iterations, keySize)
    if (derived.length !== keySize * 2 || !/^[0-9a-f]+$/.test(derived)) {
      fail(failures, "pbkdf2_derive", `returned ${derived.length} chars for key_size ${keySize}`)
    }

    const dkLen = 10 + Math.floor(random() * 55)
    const scryptN = 16 * 2 ** Math.floor(random() * 3)
    const scryptR = 1 + Math.floor(random() * 2)
    const salt = generateBytes(random, 32)
    const password = generateBytes(random, 64)
    const dk = scrypt_derive(password, salt, scryptN, scryptR, 1, dkLen)
    if (dk.length !== dkLen)
      fail(failures, "scrypt_derive", `returned ${dk.length} bytes for ${dkLen}`)
    executed += 6
  }

  // Each invalid parameter must be rejected; acceptance is a validation failure.
  const probe = new Uint8Array([1, 2, 3])
  expectRejection(failures, "pbkdf2_derive(iterations=0)", () => pbkdf2_derive("p", "s", 0, 32))
  expectRejection(failures, "pbkdf2_derive(iterations=1000001)", () =>
    pbkdf2_derive("p", "s", 1_000_001, 32)
  )
  expectRejection(failures, "pbkdf2_derive(key_size=0)", () => pbkdf2_derive("p", "s", 1, 0))
  expectRejection(failures, "pbkdf2_derive(key_size=1025)", () => pbkdf2_derive("p", "s", 1, 1025))
  expectRejection(failures, "scrypt_derive(N=0)", () => scrypt_derive(probe, probe, 0, 8, 1, 32))
  expectRejection(failures, "scrypt_derive(N=3)", () => scrypt_derive(probe, probe, 3, 8, 1, 32))
  expectRejection(failures, "scrypt_derive(N=1)", () => scrypt_derive(probe, probe, 1, 1, 1, 32))
  expectRejection(failures, "scrypt_derive(N=8)", () => scrypt_derive(probe, probe, 8, 1, 1, 32))
  expectRejection(failures, "scrypt_derive(r=0)", () => scrypt_derive(probe, probe, 16, 0, 1, 32))
  expectRejection(failures, "scrypt_derive(dk_len=9)", () =>
    scrypt_derive(probe, probe, 16, 1, 1, 9)
  )
  expectRejection(failures, "scrypt_derive(dk_len=65)", () =>
    scrypt_derive(probe, probe, 16, 1, 1, 65)
  )
  return executed + 11
}

/**
 * Runs a bounded, seeded fuzz campaign. Returns `{ ok, executed, failures }`
 * instead of exiting, so callers and tests decide how a failure is reported.
 * A missing or placeholder artifact is a failure, never a silent pass.
 */
export async function runFuzzCampaign({
  sanitizerPath = SANITIZER_WASM_PATH,
  cryptoPath = CRYPTO_WASM_PATH,
  seed = DEFAULT_SEED,
  iterations = DEFAULT_ITERATIONS,
} = {}) {
  const failures = []
  for (const [label, wasmPath] of [
    ["wasm-sanitizer", sanitizerPath],
    ["rust-crypto", cryptoPath],
  ]) {
    const problem = wasmArtifactProblem(wasmPath)
    if (problem) fail(failures, label, `artifact ${wasmPath} is ${problem}; refusing to pass`)
  }
  if (failures.length > 0) return { ok: false, executed: 0, failures }

  let executed = 0
  try {
    executed += await fuzzSanitizer(sanitizerPath, createRandom(seed), iterations, failures)
    executed += await fuzzCrypto(cryptoPath, createRandom(seed ^ 0x9e3779b9), iterations, failures)
  } catch (error) {
    fail(
      failures,
      "fuzz campaign",
      `threw ${error instanceof Error ? error.message : String(error)}`
    )
  }
  return { ok: failures.length === 0 && executed > 0, executed, failures }
}

async function main() {
  const seed = Number(process.env.WASM_FUZZ_SEED ?? DEFAULT_SEED)
  const iterations = Number(process.env.WASM_FUZZ_ITERATIONS ?? DEFAULT_ITERATIONS)
  if (!Number.isSafeInteger(seed) || seed < 0)
    throw new Error("WASM_FUZZ_SEED must be a non-negative integer")
  if (!Number.isSafeInteger(iterations) || iterations < 1 || iterations > MAX_ITERATIONS) {
    throw new Error(`WASM_FUZZ_ITERATIONS must be an integer from 1 to ${MAX_ITERATIONS}`)
  }

  console.log(`=== WASM Binary Fuzzer: seed ${seed}, ${iterations} iterations ===`)
  const result = await runFuzzCampaign({ seed, iterations })
  for (const failure of result.failures) console.error(`Fuzz failure: ${failure}`)
  if (!result.ok) {
    console.error(`=== WASM Binary Fuzzer FAILED after ${result.executed} cases ===`)
    process.exitCode = 1
    return
  }
  console.log(`=== WASM Binary Fuzzer passed: ${result.executed} cases ===`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error("Fuzzer exited with unhandled error:", err)
    process.exitCode = 1
  })
}
