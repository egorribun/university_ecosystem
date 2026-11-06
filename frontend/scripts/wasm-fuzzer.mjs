import fs from "node:fs"
import { createHash, createHmac, pbkdf2Sync, scryptSync } from "node:crypto"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { parseFragment } from "parse5"

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

const INERT_IMAGE_DATA_URL = /^data:image\/(?:avif|bmp|gif|jpe?g|png|webp)(?:;[^,]*)?,/i
const URL_ATTRIBUTES = new Set(["href", "src", "xlink:href", "action", "formaction"])
const DANGEROUS_ELEMENTS = new Set([
  "script",
  "iframe",
  "object",
  "embed",
  "style",
  "base",
  "meta",
  "form",
  "svg",
  "math",
])
const LOWER_HEX_64 = /^[0-9a-f]{64}$/
const BASE64_44 = /^[A-Za-z0-9+/]{43}=$/

// Markup that historically breaks HTML sanitizers. Mixed into generated text
// so each campaign exercises both tag structure and arbitrary Unicode.
const MARKUP_FRAGMENTS = [
  "<script>alert(1)</script>",
  "<IMG SRC=javascript:alert('XSS')>",
  '<a href="data:text/html,alert(1)">x</a>',
  "<svg onload=alert(1)>",
  "<iframe src='javascript:alert(1)'>",
  "<object data='javascript:alert(1)'></object>",
  "<embed src='data:text/html,alert(1)'>",
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

function normalizeUrlAttribute(value) {
  const separator = value.indexOf(":")
  if (separator < 0) return value.trim()
  const scheme = Array.from(value.slice(0, separator))
    .filter((character) => {
      const codePoint = character.codePointAt(0)
      return codePoint !== undefined && codePoint > 0x20 && codePoint !== 0x7f
    })
    .join("")
  return `${scheme}:${value.slice(separator + 1)}`
}

function fail(failures, label, detail) {
  failures.push(`${label}: ${detail}`)
}

/** Records a failure when `fn` does not throw; invalid parameters must be rejected. */
function expectRejection(failures, progress, label, fn) {
  try {
    progress.executed += 1
    fn()
  } catch {
    return
  }
  fail(failures, label, "invalid parameters were accepted")
}

/** Describes the first unsafe construct left in sanitizer output, or null when it is clean. */
export function sanitizedMarkupViolation(output) {
  if (typeof output !== "string") return `returned ${typeof output}`
  const fragment = parseFragment(output)
  const pending = [...fragment.childNodes]
  let foundUnsafeUrl = false
  while (pending.length > 0) {
    const node = pending.pop()
    const tagName = node.tagName?.toLowerCase()
    if (tagName === "script") return "kept a script element"
    if (tagName && DANGEROUS_ELEMENTS.has(tagName)) return "kept a dangerous element"
    for (const attribute of node.attrs ?? []) {
      const name = attribute.name.toLowerCase()
      if (/^on[a-z]+$/i.test(name)) return "kept an event-handler attribute"
      if (URL_ATTRIBUTES.has(name)) {
        const value = normalizeUrlAttribute(attribute.value)
        if (/^(?:javascript|vbscript):/i.test(value)) foundUnsafeUrl = true
        if (/^data:/i.test(value) && !INERT_IMAGE_DATA_URL.test(value)) foundUnsafeUrl = true
      }
    }
    if (node.content?.childNodes) pending.push(...node.content.childNodes)
    if (node.childNodes) pending.push(...node.childNodes)
  }
  return foundUnsafeUrl ? "kept an unsafe URL attribute" : null
}

function checkSanitizedMarkup(failures, label, input, output) {
  const violation = sanitizedMarkupViolation(output)
  if (violation)
    fail(failures, label, `${violation} for input ${JSON.stringify(input.slice(0, 80))}`)
}

function wasmInputsMatch(memory, rawArgs, inputs) {
  // wasm-bindgen passes one pointer/length pair per string or byte array.
  const buffers = inputs.length === 1 ? 1 : 2
  try {
    for (let index = 0; index < buffers; index += 1) {
      const expected = Buffer.from(inputs[index])
      const actual = Buffer.from(memory.buffer, rawArgs[index * 2] >>> 0, rawArgs[index * 2 + 1])
      if (!actual.equals(expected)) return false
    }
    return inputs.slice(buffers).every((value, index) => rawArgs[buffers * 2 + index] === value)
  } catch {
    return false
  }
}

let moduleSequence = 0

async function loadInitializedModule(jsPath, wasmPath, exportNames) {
  // wasm-bindgen caches its instance within each imported module. A fresh URL
  // ensures every campaign instruments the exact bytes it was asked to test.
  const moduleUrl = pathToFileURL(jsPath)
  moduleUrl.searchParams.set("fuzz-campaign", String(++moduleSequence))
  const moduleNamespace = await import(moduleUrl.href)
  if (typeof moduleNamespace.initSync !== "function") {
    throw new Error("WebAssembly wrapper has no synchronous initializer")
  }

  const compiled = new WebAssembly.Module(fs.readFileSync(wasmPath))
  const nativeInstance = WebAssembly.Instance
  const calls = Object.fromEntries(exportNames.map((name) => [name, 0]))
  const missed = Object.fromEntries(exportNames.map((name) => [name, 0]))
  const mismatched = Object.fromEntries(exportNames.map((name) => [name, 0]))
  const activeInputs = {}
  let instances = 0
  // The constructor is replaced only for the synchronous initialization, so
  // the wrapper receives real exports whose calls can be counted.
  const instrumentedInstance = new Proxy(nativeInstance, {
    construct(target, args) {
      const instance = Reflect.construct(target, args)
      if (args[0] !== compiled) return instance
      instances += 1
      const wrappedExports = { ...instance.exports }
      for (const name of exportNames) {
        const fn = wrappedExports[name]
        if (typeof fn !== "function") throw new Error(`WebAssembly export missing: ${name}`)
        wrappedExports[name] = (...args) => {
          calls[name] += 1
          if (
            activeInputs[name] &&
            !wasmInputsMatch(instance.exports.memory, args, activeInputs[name])
          ) {
            mismatched[name] += 1
          }
          return fn(...args)
        }
      }
      return new Proxy(instance, {
        get(target, property) {
          return property === "exports" ? wrappedExports : Reflect.get(target, property, target)
        },
      })
    },
  })

  try {
    WebAssembly.Instance = instrumentedInstance
    moduleNamespace.initSync({ module: compiled })
  } finally {
    WebAssembly.Instance = nativeInstance
  }
  if (instances !== 1) throw new Error("WebAssembly artifact was not initialized exactly once")

  const exports = {}
  for (const name of exportNames) {
    const fn = moduleNamespace[name]
    if (typeof fn !== "function") throw new Error(`WebAssembly wrapper export missing: ${name}`)
    exports[name] = (...args) => {
      const before = calls[name]
      activeInputs[name] = args.map((arg) => (arg instanceof Uint8Array ? Buffer.from(arg) : arg))
      try {
        return fn(...args)
      } finally {
        delete activeInputs[name]
        if (calls[name] === before) missed[name] += 1
      }
    }
  }
  return { exports, missed, mismatched }
}

function checkWasmCalls(failures, missed, mismatched) {
  for (const [name, count] of Object.entries(missed)) {
    if (count > 0) fail(failures, name, `${count} calls skipped the WebAssembly export`)
  }
  for (const [name, count] of Object.entries(mismatched)) {
    if (count > 0)
      fail(failures, name, `${count} calls had WebAssembly inputs differ from generated values`)
  }
}

async function fuzzSanitizer(wasmPath, random, iterations, failures, progress) {
  const {
    exports: sanitizer,
    missed,
    mismatched,
  } = await loadInitializedModule(
    path.join(path.dirname(wasmPath), "wasm_sanitizer.js"),
    wasmPath,
    ["sanitize_html_basic", "sanitize_rich_text", "strip_html"]
  )
  const { sanitize_html_basic, sanitize_rich_text, strip_html } = sanitizer
  let firstInput
  let varied = false
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const generated = generateText(random)
    if (iteration === 0) firstInput = generated
    else if (generated !== firstInput) varied = true
    // Exercise text preservation without spending another WASM call or changing
    // the random stream used by later iterations.
    const marker =
      iteration === 0 ? `fuzz${createHash("sha256").update(generated).digest("hex")}` : null
    const input = marker === null ? generated : `<p>${marker}</p>${generated}`
    for (const [label, sanitize] of [
      ["sanitize_rich_text", sanitize_rich_text],
      ["sanitize_html_basic", sanitize_html_basic],
    ]) {
      progress.executed += 1
      const output = sanitize(input)
      checkSanitizedMarkup(failures, label, input, output)
      if (marker !== null && typeof output === "string" && !output.includes(marker)) {
        fail(failures, label, "did not preserve safe text")
      }
      progress.executed += 1
      if (sanitize(input) !== output) fail(failures, label, "is not deterministic")
    }
    progress.executed += 1
    const stripped = strip_html(input)
    if (typeof stripped !== "string") fail(failures, "strip_html", "did not return a string")
    else if (marker !== null && !stripped.includes(marker))
      fail(failures, "strip_html", "did not preserve safe text")
  }
  if (iterations > 1 && !varied) fail(failures, "wasm-sanitizer", "generated inputs did not vary")
  checkWasmCalls(failures, missed, mismatched)
}

async function fuzzCrypto(wasmPath, random, iterations, failures, progress) {
  const {
    exports: crypto,
    missed,
    mismatched,
  } = await loadInitializedModule(
    path.join(path.dirname(wasmPath), "uni_wasm_crypto.js"),
    wasmPath,
    ["hmac_sha256_sign", "hmac_sha256_sign_base64", "pbkdf2_derive", "scrypt_derive"]
  )
  const { hmac_sha256_sign, hmac_sha256_sign_base64, pbkdf2_derive, scrypt_derive } = crypto
  let firstKey
  let firstMessage
  let firstSalt
  let firstPassword
  let varied = false
  let variedBytes = false
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const key = generateText(random)
    const message = generateText(random)
    if (iteration === 0) {
      firstKey = key
      firstMessage = message
    } else if (key !== firstKey || message !== firstMessage) {
      varied = true
    }
    progress.executed += 1
    const hex = hmac_sha256_sign(key, message)
    if (!LOWER_HEX_64.test(hex))
      fail(failures, "hmac_sha256_sign", "is not 64 lowercase hex digits")
    progress.executed += 1
    const encoded = hmac_sha256_sign_base64(key, message)
    if (!BASE64_44.test(encoded)) fail(failures, "hmac_sha256_sign_base64", "is not padded base64")

    const keySize = 1 + Math.floor(random() * 64)
    const pbkdf2Iterations = 1_000 + Math.floor(random() * 3)
    progress.executed += 1
    const derived = pbkdf2_derive(key, message, pbkdf2Iterations, keySize)
    if (derived.length !== keySize * 2 || !/^[0-9a-f]+$/.test(derived)) {
      fail(failures, "pbkdf2_derive", `returned ${derived.length} chars for key_size ${keySize}`)
    }

    const dkLen = 10 + Math.floor(random() * 55)
    const scryptN = 16 * 2 ** Math.floor(random() * 3)
    const scryptR = 1 + Math.floor(random() * 2)
    const salt = generateBytes(random, 32)
    const password = generateBytes(random, 64)
    if (iteration === 0) {
      firstSalt = salt.slice()
      firstPassword = password.slice()
    } else if (
      !variedBytes &&
      (!Buffer.from(salt).equals(Buffer.from(firstSalt)) ||
        !Buffer.from(password).equals(Buffer.from(firstPassword)))
    ) {
      variedBytes = true
    }
    progress.executed += 1
    const dk = scrypt_derive(password, salt, scryptN, scryptR, 1, dkLen)
    if (dk.length !== dkLen)
      fail(failures, "scrypt_derive", `returned ${dk.length} bytes for ${dkLen}`)
    if (iteration === 0) {
      // Independent native references validate the already-executed exports.
      const expectedHmac = createHmac("sha256", key).update(message).digest()
      if (hex !== expectedHmac.toString("hex"))
        fail(failures, "hmac_sha256_sign", "digest mismatch")
      if (encoded !== expectedHmac.toString("base64"))
        fail(failures, "hmac_sha256_sign_base64", "digest mismatch")
      if (derived !== pbkdf2Sync(key, message, pbkdf2Iterations, keySize, "sha256").toString("hex"))
        fail(failures, "pbkdf2_derive", "derived key mismatch")
      const expectedScrypt = scryptSync(password, salt, dkLen, { N: scryptN, r: scryptR, p: 1 })
      if (!Buffer.from(dk).equals(expectedScrypt))
        fail(failures, "scrypt_derive", "derived key mismatch")
    }
  }

  // Each invalid parameter must be rejected; acceptance is a validation failure.
  const probe = new Uint8Array([1, 2, 3])
  expectRejection(failures, progress, "pbkdf2_derive(iterations=0)", () =>
    pbkdf2_derive("p", "s", 0, 32)
  )
  expectRejection(failures, progress, "pbkdf2_derive(iterations=1)", () =>
    pbkdf2_derive("p", "s", 1, 32)
  )
  expectRejection(failures, progress, "pbkdf2_derive(iterations=999)", () =>
    pbkdf2_derive("p", "s", 999, 32)
  )
  expectRejection(failures, progress, "pbkdf2_derive(iterations=1000001)", () =>
    pbkdf2_derive("p", "s", 1_000_001, 32)
  )
  expectRejection(failures, progress, "pbkdf2_derive(key_size=0)", () =>
    pbkdf2_derive("p", "s", 1_000, 0)
  )
  expectRejection(failures, progress, "pbkdf2_derive(key_size=1025)", () =>
    pbkdf2_derive("p", "s", 1_000, 1025)
  )
  expectRejection(failures, progress, "scrypt_derive(N=0)", () =>
    scrypt_derive(probe, probe, 0, 8, 1, 32)
  )
  expectRejection(failures, progress, "scrypt_derive(N=3)", () =>
    scrypt_derive(probe, probe, 3, 8, 1, 32)
  )
  expectRejection(failures, progress, "scrypt_derive(N=1)", () =>
    scrypt_derive(probe, probe, 1, 1, 1, 32)
  )
  expectRejection(failures, progress, "scrypt_derive(N=8)", () =>
    scrypt_derive(probe, probe, 8, 1, 1, 32)
  )
  expectRejection(failures, progress, "scrypt_derive(r=0)", () =>
    scrypt_derive(probe, probe, 16, 0, 1, 32)
  )
  expectRejection(failures, progress, "scrypt_derive(dk_len=9)", () =>
    scrypt_derive(probe, probe, 16, 1, 1, 9)
  )
  expectRejection(failures, progress, "scrypt_derive(dk_len=65)", () =>
    scrypt_derive(probe, probe, 16, 1, 1, 65)
  )
  if (iterations > 1 && !varied) fail(failures, "rust-crypto", "generated inputs did not vary")
  if (iterations > 1 && !variedBytes)
    fail(failures, "scrypt_derive", "generated byte inputs did not vary")
  checkWasmCalls(failures, missed, mismatched)
}

/** Why the campaign parameters are unusable, or null when they are valid. */
export function campaignParameterProblem({ seed, iterations }) {
  if (!Number.isSafeInteger(seed) || seed < 0) return "seed must be a non-negative integer"
  if (!Number.isSafeInteger(iterations) || iterations < 1 || iterations > MAX_ITERATIONS) {
    return `iterations must be an integer from 1 to ${MAX_ITERATIONS}`
  }
  return null
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
  // AUD-416: a zero-iteration campaign still runs the fixed rejection probes,
  // so it must be refused here rather than reported as a pass.
  const parameterProblem = campaignParameterProblem({ seed, iterations })
  if (parameterProblem) return { ok: false, executed: 0, failures: [parameterProblem] }

  const failures = []
  for (const [label, wasmPath] of [
    ["wasm-sanitizer", sanitizerPath],
    ["rust-crypto", cryptoPath],
  ]) {
    const problem = wasmArtifactProblem(wasmPath)
    if (problem) fail(failures, label, `artifact ${wasmPath} is ${problem}; refusing to pass`)
  }
  if (failures.length > 0) return { ok: false, executed: 0, failures }

  // Count every attempted export, including one that throws, so a failed
  // campaign retains the progress made before the exception.
  const progress = { executed: 0 }
  try {
    await fuzzSanitizer(sanitizerPath, createRandom(seed), iterations, failures, progress)
    await fuzzCrypto(cryptoPath, createRandom(seed ^ 0x9e3779b9), iterations, failures, progress)
  } catch (error) {
    fail(
      failures,
      "fuzz campaign",
      `threw ${error instanceof Error ? error.message : String(error)}`
    )
  }
  return {
    ok: failures.length === 0 && progress.executed > 0,
    executed: progress.executed,
    failures,
  }
}

async function main() {
  const seed = Number(process.env.WASM_FUZZ_SEED ?? DEFAULT_SEED)
  const iterations = Number(process.env.WASM_FUZZ_ITERATIONS ?? DEFAULT_ITERATIONS)
  const parameterProblem = campaignParameterProblem({ seed, iterations })
  if (parameterProblem) throw new Error(parameterProblem)

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
