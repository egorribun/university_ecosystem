/**
 * Crypto Worker - Offload heavy crypto operations to Web Worker
 *
 * Provides async crypto operations that don't block the main thread.
 */

import { scrypt } from "@noble/hashes/scrypt"
import { pbkdf2 } from "@noble/hashes/pbkdf2"
import { sha256 } from "@noble/hashes/sha2"
import { hmac } from "@noble/hashes/hmac"

interface Pbkdf2Params {
  value: string
  salt: string
  keySize: number
  iterations: number
}

interface ScryptParams {
  password: Uint8Array
  salt: Uint8Array
  N: number
  r: number
  p: number
  dkLen: number
}

interface HmacSha256Params {
  json: string
  key: string
}

const utf8 = new TextEncoder()

const bytesToHex = (bytes: Uint8Array): string =>
  Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")

export const cryptoWorker = {
  /**
   * PBKDF2 key derivation
   */
  async pbkdf2({ value, salt, keySize, iterations }: Pbkdf2Params): Promise<string> {
    const passwordBytes = utf8.encode(value)
    const saltBytes = utf8.encode(salt)
    const keyBytes = keySize / 8
    // pbkdf2 from noble-hashes uses hash function directly
    const derived = pbkdf2(sha256, passwordBytes, saltBytes, { c: iterations, dkLen: keyBytes })
    return bytesToHex(new Uint8Array(derived))
  },

  /**
   * Scrypt key derivation
   */
  async scrypt({ password, salt, N, r, p, dkLen }: ScryptParams): Promise<Uint8Array> {
    return scrypt(password, salt, { N, r, p, dkLen })
  },

  /**
   * HMAC-SHA256 signing
   */
  async hmacSha256({ json, key }: HmacSha256Params): Promise<string> {
    const keyBytes = utf8.encode(key)
    const dataBytes = utf8.encode(json)
    const signature = hmac(sha256, keyBytes, dataBytes)
    return bytesToHex(signature)
  },
}




