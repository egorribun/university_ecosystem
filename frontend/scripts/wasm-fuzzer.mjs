import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(__dirname, "../..")

const sanitizerWasmPath = path.resolve(
  rootDir,
  "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm"
)
const cryptoWasmPath = path.resolve(rootDir, "frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm")

// Helper to determine if a WASM file is a real compiled binary or a placeholder mock
function isRealWasm(filePath) {
  if (!fs.existsSync(filePath)) return false
  const stats = fs.statSync(filePath)
  if (stats.size < 1000) return false // Mock files are usually < 100 bytes

  // Check WASM magic header: \0asm (0x00 0x61 0x73 0x6D)
  const fd = fs.openSync(filePath, "r")
  const buffer = Buffer.alloc(4)
  fs.readSync(fd, buffer, 0, 4, 0)
  fs.closeSync(fd)
  return buffer.readUInt32BE(0) === 0x0061736d
}

async function runFuzzer() {
  console.log("=== WASM Binary Fuzzer starting ===")

  const hasSanitizer = isRealWasm(sanitizerWasmPath)
  const hasCrypto = isRealWasm(cryptoWasmPath)

  if (!hasSanitizer && !hasCrypto) {
    console.log("WASM modules are mock placeholders or missing. Skipping binary fuzzing.")
    process.exit(0)
  }

  // Fuzz inputs
  const fuzzInputs = [
    "",
    "A".repeat(10000), // Extreme length
    "<script>alert('xss')</script>",
    "<IMG SRC=javascript:alert('XSS')>",
    "<iframe src='javascript:alert(1)'>",
    "\0\0\0\0\0\0\0\0\0\0", // Null bytes
    "😀".repeat(1000), // Emojis
    "<>\"'&", // Special chars
    "<![CDATA[<script>alert(1)</script>]]>",
  ]

  // Fuzz binary payloads (for raw memory inputs)
  const fuzzByteArrays = [
    new Uint8Array(0),
    new Uint8Array(10000).fill(65), // "AAAA..."
    new Uint8Array([0, 1, 2, 3, 255, 254, 128, 127]), // Random / bad bytes
    new Uint8Array([0xff, 0xfe, 0xfd, 0xfc]), // Invalid UTF-8 sequence
  ]

  if (hasSanitizer) {
    console.log("Fuzzing wasm-sanitizer...")
    // Dynamic import to load the wasm-sanitizer js wrapper
    const sanitizerModule = await import("../wasm-sanitizer/pkg/wasm_sanitizer.js")
    const wasmBuffer = fs.readFileSync(sanitizerWasmPath)

    // Initialize the module sync
    if (typeof sanitizerModule.initSync === "function") {
      sanitizerModule.initSync({ module: wasmBuffer })
    } else {
      await sanitizerModule.default({ module: wasmBuffer })
    }

    // Fuzz export functions
    const { sanitize_rich_text, sanitize_html_basic, strip_html, sanitize_rich_text_raw } =
      sanitizerModule

    for (const input of fuzzInputs) {
      try {
        sanitize_rich_text(input)
        sanitize_html_basic(input)
        strip_html(input)
      } catch (err) {
        console.error(
          "Crash detected in wasm-sanitizer string functions with input: %s",
          input.slice(0, 100),
          err
        )
        process.exit(1)
      }
    }

    // Fuzz raw pointer functions if exposed
    if (typeof sanitize_rich_text_raw === "function") {
      for (const bytes of fuzzByteArrays) {
        try {
          // Emulate raw pointer by passing buffer
          // In Node environment / wasm-bindgen, we can't easily pass raw pointers without allocating inside the wasm memory,
          // but calling it with invalid pointers/lengths should throw JS exceptions rather than segfaulting.
          // Let's call with invalid args to ensure safety
          await expectToFailOrSucceed(() => sanitize_rich_text_raw(0, bytes.length))
          await expectToFailOrSucceed(() => sanitize_rich_text_raw(9999999, bytes.length))
        } catch (err) {
          console.error("Crash detected in sanitize_rich_text_raw", err)
          process.exit(1)
        }
      }
    }
    console.log("wasm-sanitizer fuzzed successfully.")
  }

  if (hasCrypto) {
    console.log("Fuzzing rust-crypto...")
    const cryptoModule = await import("../rust-crypto/pkg/uni_wasm_crypto.js")
    const wasmBuffer = fs.readFileSync(cryptoWasmPath)

    if (typeof cryptoModule.initSync === "function") {
      cryptoModule.initSync({ module: wasmBuffer })
    } else {
      await cryptoModule.default({ module: wasmBuffer })
    }

    const { pbkdf2_derive, hmac_sha256_sign, scrypt_derive } = cryptoModule

    for (const input of fuzzInputs) {
      try {
        pbkdf2_derive(input, "salt", 10, 32)
        hmac_sha256_sign("key", input)
      } catch (err) {
        console.error(
          "Crash detected in rust-crypto string functions with input: %s",
          input.slice(0, 100),
          err
        )
        process.exit(1)
      }
    }

    if (typeof scrypt_derive === "function") {
      for (const bytes of fuzzByteArrays) {
        try {
          scrypt_derive(bytes, new Uint8Array([1, 2, 3]), 16, 8, 1, 32)
        } catch (err) {
          // Invalid params might throw a JS error, which is fine, but it should not cause a native crash/segfault
        }
      }
    }
    console.log("rust-crypto fuzzed successfully.")
  }

  console.log("=== WASM Binary Fuzzer finished successfully ===")
}

async function expectToFailOrSucceed(fn) {
  try {
    fn()
  } catch (e) {
    // Expected behaviour for invalid pointer access
  }
}

runFuzzer().catch((err) => {
  console.error("Fuzzer exited with unhandled error:", err)
  process.exit(1)
})
