import { scrypt } from "scrypt-js"
import CryptoJS from "crypto-js"

/**
 * Web Worker for heavy cryptographic operations.
 * Offloads scrypt and PBKDF2 from the main thread to prevent UI freezing.
 */

self.onmessage = async (event: MessageEvent) => {
  const { type, payload, id } = event.data

  try {
    if (type === "SCRYPT") {
      const { password, salt, N, r, p, dkLen } = payload
      // password and salt should be Uint8Array
      const result = await scrypt(new Uint8Array(password), new Uint8Array(salt), N, r, p, dkLen)
      self.postMessage({ id, result: Array.from(result) })
    } else if (type === "PBKDF2") {
      const { value, salt, keySize, iterations } = payload
      const hash = CryptoJS.PBKDF2(value, salt, {
        keySize: keySize / 32,
        iterations: iterations,
        hasher: CryptoJS.algo.SHA256,
      })
      self.postMessage({ id, result: hash.toString(CryptoJS.enc.Hex) })
    } else if (type === "HMAC_SHA256") {
      const { json, key } = payload
      const signature = CryptoJS.HmacSHA256(json, key)
      self.postMessage({ id, result: signature.toString(CryptoJS.enc.Base64) })
    }
  } catch (error: any) {
    self.postMessage({ id, error: error?.message || "Unknown worker error" })
  }
}
