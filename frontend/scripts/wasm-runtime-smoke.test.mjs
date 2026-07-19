import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const sanitizer = await import("../wasm-sanitizer/pkg/wasm_sanitizer.js")
const crypto = await import("../rust-crypto/pkg/uni_wasm_crypto.js")

const sanitizerBytes = await readFile(
  new URL("../wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm", import.meta.url)
)
const cryptoBytes = await readFile(
  new URL("../rust-crypto/pkg/uni_wasm_crypto_bg.wasm", import.meta.url)
)

await sanitizer.default({ module_or_path: sanitizerBytes })
await crypto.default({ module_or_path: cryptoBytes })

test("the generated sanitizer removes executable markup", () => {
  const sanitized = sanitizer.sanitize_rich_text(
    "<img src=x onerror=alert(1)><script>alert(2)</script><p><strong>safe</strong></p>"
  )

  assert.doesNotMatch(sanitized, /<script|onerror/i)
  assert.match(sanitized, /safe/)
})

test("the generated crypto module matches deterministic known-answer vectors", () => {
  assert.equal(
    crypto.pbkdf2_derive("password", "salt", 1, 32),
    "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"
  )
  assert.equal(
    crypto.hmac_sha256_sign("key", "The quick brown fox jumps over the lazy dog"),
    "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
  )
  assert.equal(
    Buffer.from(
      crypto.scrypt_derive(
        new TextEncoder().encode("password"),
        new TextEncoder().encode("NaCl"),
        1024,
        8,
        16,
        64
      )
    ).toString("hex"),
    "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b3731622eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640"
  )
})
