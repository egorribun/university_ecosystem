/**
 * Web Worker for heavy cryptographic operations.
 * Uses native Web Crypto API to prevent blocking the main thread.
 */

import init, { pbkdf2_derive, scrypt_derive, hmac_sha256_sign } from "../../rust-crypto/pkg/rust_crypto.js"

let wasmInitPromise: Promise<any> | null = null

async function getWasm() {
  if (!wasmInitPromise) {
    wasmInitPromise = init()
  }
  return wasmInitPromise
}

self.onmessage = async (event: MessageEvent) => {
  const { type, payload, id } = event.data

  try {
    await getWasm()

    if (type === "SCRYPT") {
      const { password, salt, N, r, p, dkLen } = payload

      const result = scrypt_derive(
        password,
        salt,
        N,
        r,
        p,
        dkLen
      )
      self.postMessage({ id, result: Array.from(result) })

    } else if (type === "PBKDF2") {
      const { value, salt, keySize, iterations } = payload
      /* Previous implementation expected a hex output for pbkdf2 and took keySize in bits.
         Our WASM pbkdf2_derive takes key_size in bytes. Wait, previous was keySize=256 bits,
         so bytes should be keySize / 8. No, crypto-js used "words" so 256/32 = 8 words = 32 bytes.
         In `useProfileSync`, pbkdf2 derives a key for AES-GCM (which needs 256 bits = 32 bytes).
         Let's just pass `keySize / 8` to Rust which expects `key_size` in bytes. */

      const byteLen = Math.floor(keySize / 8)
      const hex = pbkdf2_derive(value, salt, iterations, byteLen)
      self.postMessage({ id, result: hex })

    } else if (type === "HMAC_SHA256") {
      const { json, key } = payload
      const hex = hmac_sha256_sign(key, json)
      // JS implementation returned base64. Let's convert hex to base64.
      const match = hex.match(/\w{2}/g)
      if (!match) throw new Error("Invalid hex from WASM HMAC")
      const uint8 = new Uint8Array(match.map((a: string) => parseInt(a, 16)))
      const base64 = btoa(String.fromCharCode(...uint8))
      self.postMessage({ id, result: base64 })
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown worker error"
    self.postMessage({ id, error: message })
  }
}


